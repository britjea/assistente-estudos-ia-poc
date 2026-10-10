"""Testes do mecanismo de autorização de uso único (autorizacao.py).

Nenhum destes testes toca rede ou o SDK da Anthropic — testam só a lógica
de consumo atômico e persistência em arquivo, isoladamente.

Rodar com: ../venv/bin/pytest test_autorizacao.py -v
"""

import importlib
import json
import threading

import pytest

import autorizacao


@pytest.fixture(autouse=True)
def isolar_arquivo(tmp_path, monkeypatch):
    caminho_temporario = tmp_path / "autorizacao_teste.json"
    monkeypatch.setattr(autorizacao, "AUTORIZACAO_CHAMADA_REAL_JSON", caminho_temporario)
    yield caminho_temporario


def test_padrao_e_zero_autorizacoes(isolar_arquivo):
    assert autorizacao.consultar_autorizacoes_restantes() == 0
    with pytest.raises(autorizacao.AutorizacaoNaoConcedida):
        autorizacao.consumir_uma_autorizacao()


def test_consome_a_autorizacao_concedida(isolar_arquivo):
    isolar_arquivo.write_text(json.dumps({"chamadas_restantes": 1}))

    autorizacao.consumir_uma_autorizacao()  # não deve levantar

    assert autorizacao.consultar_autorizacoes_restantes() == 0
    estado_final = json.loads(isolar_arquivo.read_text())
    assert estado_final["chamadas_restantes"] == 0
    assert estado_final["ultima_consumida_em_utc"] is not None


def test_segunda_tentativa_e_bloqueada_apos_a_primeira(isolar_arquivo):
    """O requisito central: autorizar 1, consumir 1, a segunda tentativa
    tem que falhar — nunca duas chamadas reais com uma autorização só."""
    isolar_arquivo.write_text(json.dumps({"chamadas_restantes": 1}))

    autorizacao.consumir_uma_autorizacao()  # primeira: sucesso

    with pytest.raises(autorizacao.AutorizacaoNaoConcedida):
        autorizacao.consumir_uma_autorizacao()  # segunda: deve falhar

    assert autorizacao.consultar_autorizacoes_restantes() == 0


def test_bloqueado_mesmo_apos_simular_reinicio_da_aplicacao(isolar_arquivo):
    """Consome a única autorização, depois recarrega o módulo inteiro (como
    se o processo Python tivesse sido reiniciado do zero) e confirma que o
    saldo continua em 0 — ou seja, não existe nenhum estado em memória que
    repõe a autorização; tudo vem do arquivo em disco."""
    isolar_arquivo.write_text(json.dumps({"chamadas_restantes": 1}))
    autorizacao.consumir_uma_autorizacao()
    assert autorizacao.consultar_autorizacoes_restantes() == 0

    # Simula reinício do processo: recarrega o módulo do zero. Como o
    # caminho do arquivo foi redefinido via monkeypatch (não pelo valor
    # importado de config), precisamos reaplicar o monkeypatch após reload —
    # isso é só uma particularidade do teste; o ponto é que o módulo
    # recarregado não traz nenhum contador em memória consigo.
    modulo_recarregado = importlib.reload(autorizacao)
    modulo_recarregado.AUTORIZACAO_CHAMADA_REAL_JSON = isolar_arquivo

    assert modulo_recarregado.consultar_autorizacoes_restantes() == 0
    with pytest.raises(modulo_recarregado.AutorizacaoNaoConcedida):
        modulo_recarregado.consumir_uma_autorizacao()

    # O arquivo em disco é a prova final: continua em 0, não voltou a 1.
    estado_em_disco = json.loads(isolar_arquivo.read_text())
    assert estado_em_disco["chamadas_restantes"] == 0


def test_falha_na_chamada_nao_repoe_a_autorizacao(isolar_arquivo):
    """Simula o cenário real: a autorização é consumida ANTES da tentativa
    de chamada (como acontece em app.py). Se a chamada falhar depois
    (aqui, simulado por uma exceção qualquer), a autorização já foi gasta
    e nada a repõe automaticamente."""
    isolar_arquivo.write_text(json.dumps({"chamadas_restantes": 1}))

    autorizacao.consumir_uma_autorizacao()
    try:
        raise RuntimeError("simulando uma falha de rede na chamada real")
    except RuntimeError:
        pass  # a chamada "falhou", mas a autorização já foi consumida antes

    assert autorizacao.consultar_autorizacoes_restantes() == 0
    with pytest.raises(autorizacao.AutorizacaoNaoConcedida):
        autorizacao.consumir_uma_autorizacao()


def test_duas_requisicoes_concorrentes_consomem_no_maximo_uma_autorizacao(isolar_arquivo):
    """Com exatamente 1 autorização disponível, dispara duas threads tentando
    consumi-la ao mesmo tempo. Graças ao lock exclusivo de arquivo
    (fcntl.flock), no máximo uma deve ter sucesso — nunca as duas."""
    isolar_arquivo.write_text(json.dumps({"chamadas_restantes": 1}))

    resultados = []
    barreira = threading.Barrier(2)

    def tentar_consumir():
        barreira.wait()  # maximiza a chance de colisão real entre as threads
        try:
            autorizacao.consumir_uma_autorizacao()
            resultados.append("sucesso")
        except autorizacao.AutorizacaoNaoConcedida:
            resultados.append("bloqueado")

    threads = [threading.Thread(target=tentar_consumir) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(resultados) == ["bloqueado", "sucesso"]
    assert autorizacao.consultar_autorizacoes_restantes() == 0
