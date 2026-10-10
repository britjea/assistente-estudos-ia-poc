"""Autorização explícita e de uso único para chamadas reais à API.

Este mecanismo é INDEPENDENTE do limitador geral (limitador.py) e da trava
global ENABLE_PAID_API_CALLS (config.py). As três proteções são cumulativas
— uma chamada real só acontece se TODAS permitirem.

Modelo de uso:
1. O operador edita manualmente o arquivo AUTORIZACAO_CHAMADA_REAL_JSON e
   define "chamadas_restantes": 1 — nunca via variável de ambiente com a
   chave de API, nunca via código. O valor padrão (arquivo ausente) é 0.
2. `consumir_uma_autorizacao()` deve ser chamada IMEDIATAMENTE ANTES de
   qualquer tentativa de chamada ao SDK. Ela verifica e decrementa o saldo
   de forma atômica (lock exclusivo de arquivo via fcntl.flock), para que
   duas requisições concorrentes nunca consumam a mesma autorização.
3. A autorização é gasta nesse momento — ANTES da chamada de fato acontecer.
   Se a chamada falhar depois (erro de rede, erro da API, o processo cair no
   meio do caminho), a autorização já foi consumida e NÃO volta sozinha.
   Reautorizar exige editar o arquivo manualmente de novo.
4. Como o estado vive inteiramente no arquivo (nenhum contador em memória
   no processo), reiniciar a aplicação não repõe autorizações consumidas.

Requer um sistema operacional POSIX (fcntl.flock) — adequado para este
experimento local em Linux/macOS.
"""

import fcntl
import json
from datetime import datetime, timezone

from config import AUTORIZACAO_CHAMADA_REAL_JSON


class AutorizacaoNaoConcedida(Exception):
    pass


def _estado_padrao() -> dict:
    return {"chamadas_restantes": 0, "ultima_consumida_em_utc": None}


def _ler_estado_sem_lock(caminho) -> dict:
    if not caminho.exists():
        return _estado_padrao()
    try:
        dados = json.loads(caminho.read_text())
        return {
            "chamadas_restantes": int(dados.get("chamadas_restantes", 0)),
            "ultima_consumida_em_utc": dados.get("ultima_consumida_em_utc"),
        }
    except (json.JSONDecodeError, ValueError):
        return _estado_padrao()


def consultar_autorizacoes_restantes() -> int:
    """Leitura simples, sem lock — só para exibição/diagnóstico. A decisão
    de permitir ou não uma chamada real é sempre feita por
    consumir_uma_autorizacao(), que relê o arquivo sob lock."""
    return max(0, _ler_estado_sem_lock(AUTORIZACAO_CHAMADA_REAL_JSON)["chamadas_restantes"])


def consumir_uma_autorizacao() -> None:
    """Consome atomicamente uma autorização de chamada real, se houver
    saldo disponível. Levanta AutorizacaoNaoConcedida caso contrário.

    Usa fcntl.flock (lock exclusivo) para garantir atomicidade mesmo com
    requisições concorrentes — seja no mesmo processo (ex.: duas corrotinas
    asyncio) ou em processos diferentes. O arquivo inteiro é lido, checado e
    reescrito dentro da seção crítica protegida pelo lock.
    """
    AUTORIZACAO_CHAMADA_REAL_JSON.parent.mkdir(parents=True, exist_ok=True)

    # "a+" cria o arquivo se não existir, sem truncar um já existente.
    with open(AUTORIZACAO_CHAMADA_REAL_JSON, "a+") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.seek(0)
            conteudo = f.read()
            if conteudo.strip():
                try:
                    dados = json.loads(conteudo)
                except json.JSONDecodeError:
                    dados = _estado_padrao()
            else:
                dados = _estado_padrao()

            restantes = int(dados.get("chamadas_restantes", 0))

            if restantes <= 0:
                raise AutorizacaoNaoConcedida(
                    "Nenhuma autorização de chamada real disponível "
                    "(chamadas_restantes=0). Edite manualmente o arquivo "
                    f"'{AUTORIZACAO_CHAMADA_REAL_JSON.name}' e defina "
                    "'chamadas_restantes' para autorizar uma nova chamada — "
                    "autorizações não são repostas automaticamente."
                )

            dados["chamadas_restantes"] = restantes - 1
            dados["ultima_consumida_em_utc"] = datetime.now(timezone.utc).isoformat()

            f.seek(0)
            f.truncate()
            f.write(json.dumps(dados, indent=2))
            f.flush()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
