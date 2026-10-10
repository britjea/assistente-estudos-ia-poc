"""Limitador local de chamadas à API paga. Protege contra gasto acidental
durante os testes da POC: depois de LIMITE_CHAMADAS chamadas bem-sucedidas
(configurável via variável de ambiente LIMITE_CHAMADAS, padrão 5), novas
tentativas são bloqueadas antes de qualquer chamada à Anthropic.

O contador é persistido em um arquivo JSON simples (sem banco de dados),
para sobreviver a reinícios do servidor durante os testes.
"""

import json
from datetime import datetime, timezone

from config import CONTADOR_CHAMADAS_JSON, LIMITE_CHAMADAS


class LimiteDeChamadasAtingido(Exception):
    pass


def _ler_contador() -> int:
    if not CONTADOR_CHAMADAS_JSON.exists():
        return 0
    try:
        dados = json.loads(CONTADOR_CHAMADAS_JSON.read_text())
        return int(dados.get("chamadas_realizadas", 0))
    except (json.JSONDecodeError, ValueError):
        return 0


def _salvar_contador(valor: int) -> None:
    CONTADOR_CHAMADAS_JSON.write_text(
        json.dumps(
            {
                "chamadas_realizadas": valor,
                "limite": LIMITE_CHAMADAS,
                "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
    )


def chamadas_restantes() -> int:
    return max(0, LIMITE_CHAMADAS - _ler_contador())


def verificar_e_incrementar() -> None:
    """Levanta LimiteDeChamadasAtingido se o limite já foi atingido.
    Caso contrário, incrementa o contador em 1 — deve ser chamado
    imediatamente antes de uma chamada real (paga) à API."""
    atual = _ler_contador()
    if atual >= LIMITE_CHAMADAS:
        raise LimiteDeChamadasAtingido(
            f"Limite local de {LIMITE_CHAMADAS} chamadas à API atingido. "
            f"Para continuar testando, apague o arquivo "
            f"'{CONTADOR_CHAMADAS_JSON.name}' ou aumente LIMITE_CHAMADAS no .env."
        )
    _salvar_contador(atual + 1)
