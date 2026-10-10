"""Testes de correcao.py — funções puras, sem rede, sem HTTP, sem import de
`anthropic`. Não usa nenhuma fixture de test_app.py.
"""

from correcao import corrigir_exercicio, corrigir_quiz
from schemas import (
    Exercicio,
    QuestaoQuiz,
    RespostaCoordenadas,
    RespostaNumerica,
    RespostaNumericaComId,
    CampoCoordenada,
)


def _exercicio_numerico(valor_esperado=65.0, tolerancia=0.0):
    return Exercicio(
        id="e1",
        numero=1,
        enunciado="...",
        resposta=RespostaNumerica(
            tipo_resposta="num", valor_esperado=valor_esperado, tolerancia=tolerancia
        ),
        explicacao="a explicação",
    )


def test_exercicio_numerico_acerto_exato():
    ex = _exercicio_numerico(valor_esperado=65.0)
    veredicto = corrigir_exercicio(ex, {"valor": 65.0})
    assert veredicto.correto is True
    assert veredicto.explicacao == "a explicação"


def test_exercicio_numerico_errado():
    ex = _exercicio_numerico(valor_esperado=65.0)
    veredicto = corrigir_exercicio(ex, {"valor": 70.0})
    assert veredicto.correto is False


def test_exercicio_numerico_na_borda_da_tolerancia_e_correto():
    ex = _exercicio_numerico(valor_esperado=65.0, tolerancia=0.5)
    veredicto = corrigir_exercicio(ex, {"valor": 65.5})
    assert veredicto.correto is True  # inclusivo


def test_exercicio_numerico_passando_da_tolerancia_e_errado():
    ex = _exercicio_numerico(valor_esperado=65.0, tolerancia=0.5)
    veredicto = corrigir_exercicio(ex, {"valor": 65.51})
    assert veredicto.correto is False


def test_exercicio_numid():
    ex = Exercicio(
        id="e2",
        numero=2,
        enunciado="...",
        resposta=RespostaNumericaComId(
            tipo_resposta="numid", campo_id="e5x", valor_esperado=30.0, tolerancia=0.0
        ),
        explicacao="e5x = 30",
    )
    assert corrigir_exercicio(ex, {"e5x": 30.0}).correto is True
    assert corrigir_exercicio(ex, {"e5x": 29.0}).correto is False


def test_exercicio_coordenadas_ambos_corretos():
    ex = Exercicio(
        id="e3",
        numero=3,
        enunciado="...",
        resposta=RespostaCoordenadas(
            tipo_resposta="coord",
            campos=[
                CampoCoordenada(campo_id="x", rotulo="x =", valor_esperado=20, tolerancia=0),
                CampoCoordenada(campo_id="angulo", rotulo="Ângulo =", valor_esperado=70, tolerancia=0),
            ],
        ),
        explicacao="x=20, angulo=70",
    )
    veredicto = corrigir_exercicio(ex, {"x": 20, "angulo": 70})
    assert veredicto.correto is True
    assert veredicto.detalhes_por_campo == {"x": True, "angulo": True}


def test_exercicio_coordenadas_parcialmente_correto():
    ex = Exercicio(
        id="e3",
        numero=3,
        enunciado="...",
        resposta=RespostaCoordenadas(
            tipo_resposta="coord",
            campos=[
                CampoCoordenada(campo_id="x", rotulo="x =", valor_esperado=20, tolerancia=0),
                CampoCoordenada(campo_id="angulo", rotulo="Ângulo =", valor_esperado=70, tolerancia=0),
            ],
        ),
        explicacao="x=20, angulo=70",
    )
    veredicto = corrigir_exercicio(ex, {"x": 20, "angulo": 99})
    assert veredicto.correto is False  # precisa de ambos
    assert veredicto.detalhes_por_campo == {"x": True, "angulo": False}


def _questao_quiz():
    return QuestaoQuiz(
        id="q1",
        categoria="opv",
        pergunta="...",
        opcoes=["a", "b", "c", "d"],
        indice_correto=2,
        explicacao="a explicação do quiz",
    )


def test_quiz_indice_correto():
    veredicto = corrigir_quiz(_questao_quiz(), 2)
    assert veredicto.correto is True
    assert veredicto.explicacao == "a explicação do quiz"


def test_quiz_indice_errado():
    veredicto = corrigir_quiz(_questao_quiz(), 0)
    assert veredicto.correto is False


def test_quiz_indice_fora_do_range_nao_levanta_excecao():
    """Um índice 999 (bug no cliente, ou tentativa maliciosa) deve ser
    tratado como resposta errada — nunca como erro 500."""
    veredicto = corrigir_quiz(_questao_quiz(), 999)
    assert veredicto.correto is False

    veredicto_negativo = corrigir_quiz(_questao_quiz(), -1)
    assert veredicto_negativo.correto is False
