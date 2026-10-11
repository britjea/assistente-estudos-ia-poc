"""Testes do schema Pydantic (schemas.py) — sem rede, sem HTTP, sem import
de `anthropic`. Não usa nenhuma das fixtures de mock de test_app.py (não
são autouse fora do próprio módulo, e esta suíte não precisa delas de
qualquer forma, já que nunca toca o SDK da Anthropic).
"""

import json
from pathlib import Path

import pydantic
import pytest

from schemas import Dica, MaterialEducacional, QuestaoSimulado

EXEMPLO_JSON = Path(__file__).parent / "materiais" / "geometria-7-ano.json"


def test_material_de_exemplo_carrega_corretamente():
    dados = json.loads(EXEMPLO_JSON.read_text(encoding="utf-8"))
    material = MaterialEducacional.model_validate(dados)
    assert material.id == "geometria-7-ano"
    assert len(material.capitulos) == 2
    assert len(material.exercicios) == 4
    assert len(material.quiz) == 5
    assert len(material.simulado) == 4
    assert len(material.dicas) == 3
    assert len(material.videos) == 3


def test_questao_simulado_explicacao_e_opcional():
    # Sem explicacao — continua válido (campo opcional, aditivo).
    questao = QuestaoSimulado(id="s1", pergunta="...", opcoes=["a", "b"], indice_correto=0)
    assert questao.explicacao is None

    questao_com_explicacao = QuestaoSimulado(
        id="s2", pergunta="...", opcoes=["a", "b"], indice_correto=0, explicacao="porque sim"
    )
    assert questao_com_explicacao.explicacao == "porque sim"


def test_dica_checklist_exige_itens_e_proibe_texto():
    with pytest.raises(pydantic.ValidationError):
        Dica(id="d1", titulo="T", checklist=True)  # sem itens

    with pytest.raises(pydantic.ValidationError):
        Dica(id="d1", titulo="T", checklist=True, itens=["a"], texto="não deveria ter")


def test_dica_nao_checklist_exige_exatamente_texto_ou_itens():
    with pytest.raises(pydantic.ValidationError):
        Dica(id="d1", titulo="T")  # nem texto nem itens

    with pytest.raises(pydantic.ValidationError):
        Dica(id="d1", titulo="T", texto="a", itens=["b"])  # os dois ao mesmo tempo

    # Um dos dois, sozinho, é válido.
    assert Dica(id="d1", titulo="T", texto="a").texto == "a"
    assert Dica(id="d1", titulo="T", itens=["a"]).itens == ["a"]


def test_bloco_resumo_com_tipo_desconhecido_e_rejeitado():
    with pytest.raises(pydantic.ValidationError):
        MaterialEducacional.model_validate(
            {
                "id": "x",
                "metadados": {"titulo": "X", "disciplina": "X", "ano_serie": "X"},
                "capitulos": [
                    {
                        "id": "c1",
                        "titulo": "Cap 1",
                        "ordem": 1,
                        "secoes": [
                            {
                                "id": "s1",
                                "titulo": "Sec 1",
                                "blocos": [{"tipo": "tipo-que-nao-existe"}],
                            }
                        ],
                    }
                ],
            }
        )


def test_exercicio_com_tipo_resposta_desconhecido_e_rejeitado():
    with pytest.raises(pydantic.ValidationError):
        MaterialEducacional.model_validate(
            {
                "id": "x",
                "metadados": {"titulo": "X", "disciplina": "X", "ano_serie": "X"},
                "exercicios": [
                    {
                        "id": "e1",
                        "numero": 1,
                        "enunciado": "...",
                        "resposta": {"tipo_resposta": "nao-existe", "valor_esperado": 1},
                    }
                ],
            }
        )


def test_indice_correto_fora_do_range_e_rejeitado_na_autoria():
    with pytest.raises(pydantic.ValidationError):
        MaterialEducacional.model_validate(
            {
                "id": "x",
                "metadados": {"titulo": "X", "disciplina": "X", "ano_serie": "X"},
                "quiz": [
                    {
                        "id": "q1",
                        "categoria": "x",
                        "pergunta": "...",
                        "opcoes": ["a", "b"],
                        "indice_correto": 5,
                        "explicacao": "...",
                    }
                ],
            }
        )


def test_bloco_tabela_com_linha_de_tamanho_errado_e_rejeitada():
    with pytest.raises(pydantic.ValidationError):
        MaterialEducacional.model_validate(
            {
                "id": "x",
                "metadados": {"titulo": "X", "disciplina": "X", "ano_serie": "X"},
                "capitulos": [
                    {
                        "id": "c1",
                        "titulo": "Cap 1",
                        "ordem": 1,
                        "secoes": [
                            {
                                "id": "s1",
                                "titulo": "Sec 1",
                                "blocos": [
                                    {
                                        "tipo": "tabela",
                                        "colunas": ["A", "B"],
                                        "linhas": [["só um valor"]],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )


def test_bloco_destaque_exige_exatamente_texto_ou_itens():
    base = {
        "id": "x",
        "metadados": {"titulo": "X", "disciplina": "X", "ano_serie": "X"},
        "capitulos": [
            {
                "id": "c1",
                "titulo": "Cap 1",
                "ordem": 1,
                "secoes": [{"id": "s1", "titulo": "Sec 1", "blocos": [{"tipo": "destaque", "tom": "azul", "titulo": "T"}]}],
            }
        ],
    }
    with pytest.raises(pydantic.ValidationError):
        MaterialEducacional.model_validate(base)  # nem texto nem itens

    base["capitulos"][0]["secoes"][0]["blocos"][0]["texto"] = "a"
    base["capitulos"][0]["secoes"][0]["blocos"][0]["itens"] = ["b"]
    with pytest.raises(pydantic.ValidationError):
        MaterialEducacional.model_validate(base)  # os dois ao mesmo tempo


def test_schema_version_diferente_de_1_e_rejeitado():
    with pytest.raises(pydantic.ValidationError):
        MaterialEducacional.model_validate(
            {
                "schema_version": 2,
                "id": "x",
                "metadados": {"titulo": "X", "disciplina": "X", "ano_serie": "X"},
            }
        )
