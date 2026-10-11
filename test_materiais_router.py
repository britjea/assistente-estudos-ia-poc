"""Testes HTTP das rotas de materiais (routers/materiais.py) — sem rede,
sem `anthropic`. Reusa o app completo (import app as app_module), mas não
usa nenhuma das fixtures de mock do SDK de test_app.py: esta suíte nunca
toca o SDK da Anthropic, então elas não fazem falta.
"""

import json

from fastapi.testclient import TestClient

import app as app_module
import materiais_loader

client = TestClient(app_module.app)


# --- GET /api/materiais/{id} — o payload público nunca vaza gabarito -------


def test_get_material_retorna_200_e_estrutura_esperada():
    resp = client.get("/api/materiais/geometria-7-ano")
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["id"] == "geometria-7-ano"
    assert len(corpo["capitulos"]) == 2
    assert len(corpo["exercicios"]) == 4
    assert len(corpo["quiz"]) == 5
    assert len(corpo["simulado"]) == 4
    assert len(corpo["dicas"]) == 3
    assert len(corpo["videos"]) == 3


def test_get_material_nunca_inclui_gabarito_de_exercicios_quiz_ou_simulado():
    resp = client.get("/api/materiais/geometria-7-ano")
    corpo_como_texto = json.dumps(resp.json())

    # Nenhuma explicação de exercício, quiz ou simulado deve vazar antes da
    # correção (dicas/vídeos não têm campo "explicacao", então essa busca
    # continua válida para o payload inteiro).
    assert "explicacao" not in corpo_como_texto

    # Nenhum exercício carrega o campo "resposta" (valor esperado/tolerância).
    for ex in resp.json()["exercicios"]:
        assert "resposta" not in ex
        assert "valor_esperado" not in json.dumps(ex)

    # Nenhuma questão de quiz carrega o índice correto.
    for q in resp.json()["quiz"]:
        assert "indice_correto" not in q

    # Nenhuma questão de simulado carrega o índice correto — só é revelado
    # depois de POST .../simulado/corrigir.
    for s in resp.json()["simulado"]:
        assert "indice_correto" not in s


def test_get_material_inclui_dicas_e_videos_sem_restricao():
    """Dicas e vídeos não têm gabarito — são incluídos tal como estão."""
    resp = client.get("/api/materiais/geometria-7-ano")
    corpo = resp.json()
    assert corpo["dicas"][0]["titulo"]
    assert corpo["videos"][0]["youtube_id"]


def test_get_material_inexistente_retorna_404():
    resp = client.get("/api/materiais/nao-existe")
    assert resp.status_code == 404


def test_get_pagina_material_serve_html():
    resp = client.get("/materiais/geometria-7-ano")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


# --- Path traversal — defesa testada diretamente no loader -----------------


def test_loader_rejeita_ids_com_travessia_de_diretorio():
    for id_malicioso in ["..", "../../etc/passwd", "../config", "./../.env", ""]:
        try:
            materiais_loader.load_material(id_malicioso)
            assert False, f"deveria ter levantado MaterialNaoEncontrado para {id_malicioso!r}"
        except materiais_loader.MaterialNaoEncontrado:
            pass  # esperado


def test_get_material_com_id_pontilhado_retorna_404_nao_500():
    resp = client.get("/api/materiais/..")
    assert resp.status_code == 404


# --- POST .../corrigir -------------------------------------------------


def test_corrigir_exercicio_resposta_certa():
    resp = client.post(
        "/api/materiais/geometria-7-ano/corrigir",
        json={"tipo": "exercicio", "item_id": "ex-1", "resposta": {"valor": 65}},
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["correto"] is True
    assert corpo["explicacao"]  # só aparece DEPOIS da submissão — isso é esperado e correto


def test_corrigir_exercicio_resposta_errada():
    resp = client.post(
        "/api/materiais/geometria-7-ano/corrigir",
        json={"tipo": "exercicio", "item_id": "ex-1", "resposta": {"valor": 1}},
    )
    assert resp.status_code == 200
    assert resp.json()["correto"] is False


def test_corrigir_exercicio_coordenadas():
    resp = client.post(
        "/api/materiais/geometria-7-ano/corrigir",
        json={"tipo": "exercicio", "item_id": "ex-3", "resposta": {"x": 20, "angulo": 70}},
    )
    assert resp.status_code == 200
    assert resp.json()["correto"] is True


def test_corrigir_exercicio_item_id_desconhecido_retorna_404():
    resp = client.post(
        "/api/materiais/geometria-7-ano/corrigir",
        json={"tipo": "exercicio", "item_id": "nao-existe", "resposta": {"valor": 1}},
    )
    assert resp.status_code == 404


def test_corrigir_quiz_resposta_certa():
    resp = client.post(
        "/api/materiais/geometria-7-ano/corrigir",
        json={"tipo": "quiz", "item_id": "q-1", "resposta": 2},
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["correto"] is True
    assert corpo["explicacao"]


def test_corrigir_quiz_indice_fora_do_range_retorna_200_nao_erro():
    resp = client.post(
        "/api/materiais/geometria-7-ano/corrigir",
        json={"tipo": "quiz", "item_id": "q-1", "resposta": 999},
    )
    assert resp.status_code == 200
    assert resp.json()["correto"] is False


def test_corrigir_material_inexistente_retorna_404():
    resp = client.post(
        "/api/materiais/nao-existe/corrigir",
        json={"tipo": "quiz", "item_id": "q-1", "resposta": 0},
    )
    assert resp.status_code == 404


# --- POST .../simulado/corrigir (correção em lote) --------------------------
# Gabarito real do material de exemplo: s-1→1, s-2→2, s-3→1, s-4→1.


def test_corrigir_simulado_com_respostas_mistas():
    resp = client.post(
        "/api/materiais/geometria-7-ano/simulado/corrigir",
        json={"respostas": {"s-1": 1, "s-2": 2, "s-3": 0, "s-4": 1}},
    )
    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["nota"] == 3
    assert corpo["total"] == 4
    assert corpo["percentual"] == 75.0
    assert corpo["por_questao"]["s-3"]["correto"] is False
    assert corpo["por_questao"]["s-3"]["indice_correto"] == 1


def test_corrigir_simulado_revela_indice_correto_de_todas_as_questoes():
    """Diferente de /corrigir (um item por vez), aqui revelar TODOS os
    índices corretos de uma vez é o comportamento esperado — é o que
    "corrigir o simulado inteiro" significa."""
    resp = client.post(
        "/api/materiais/geometria-7-ano/simulado/corrigir",
        json={"respostas": {}},
    )
    assert resp.status_code == 200
    por_questao = resp.json()["por_questao"]
    assert len(por_questao) == 4
    assert all("indice_correto" in v for v in por_questao.values())


def test_corrigir_simulado_questao_ausente_nao_quebra():
    resp = client.post(
        "/api/materiais/geometria-7-ano/simulado/corrigir",
        json={"respostas": {"s-1": 1}},  # s-2, s-3, s-4 ausentes
    )
    assert resp.status_code == 200
    assert resp.json()["nota"] == 1


def test_corrigir_simulado_material_inexistente_retorna_404():
    resp = client.post(
        "/api/materiais/nao-existe/simulado/corrigir",
        json={"respostas": {}},
    )
    assert resp.status_code == 404


# --- GET .../gabarito (view derivada, sem exigir submissão) -----------------


def test_gabarito_nao_exige_nenhuma_submissao_previa():
    resp = client.get("/api/materiais/geometria-7-ano/gabarito")
    assert resp.status_code == 200
    corpo = resp.json()
    assert len(corpo["exercicios"]) == 4
    assert len(corpo["quiz"]) == 5
    assert len(corpo["simulado"]) == 4


def test_gabarito_traz_resposta_e_explicacao():
    resp = client.get("/api/materiais/geometria-7-ano/gabarito")
    corpo = resp.json()
    ex1 = next(i for i in corpo["exercicios"] if i["identificador"] == "1")
    assert ex1["resposta_formatada"] == "65.0"
    assert ex1["explicacao"]


def test_gabarito_material_inexistente_retorna_404():
    resp = client.get("/api/materiais/nao-existe/gabarito")
    assert resp.status_code == 404
