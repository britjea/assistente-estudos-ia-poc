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


def test_get_material_nunca_inclui_gabarito_de_exercicios_ou_quiz():
    resp = client.get("/api/materiais/geometria-7-ano")
    corpo_como_texto = json.dumps(resp.json())

    # Nenhuma explicação de exercício ou quiz deve vazar antes da correção.
    assert "explicacao" not in corpo_como_texto

    # Nenhum exercício carrega o campo "resposta" (valor esperado/tolerância).
    for ex in resp.json()["exercicios"]:
        assert "resposta" not in ex
        assert "valor_esperado" not in json.dumps(ex)

    # Nenhuma questão de quiz carrega o índice correto.
    for q in resp.json()["quiz"]:
        assert "indice_correto" not in q


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
