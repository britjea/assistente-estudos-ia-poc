"""Testes de correcao.py — funções puras, sem rede, sem HTTP, sem import de
`anthropic`. Não usa nenhuma fixture de test_app.py.
"""

from correcao import corrigir_exercicio, corrigir_quiz, corrigir_simulado
from schemas import (
    Exercicio,
    QuestaoQuiz,
    QuestaoSimulado,
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


# --- Simulado (correção em lote) --------------------------------------------


def _questoes_simulado():
    return [
        QuestaoSimulado(id="s1", pergunta="...", opcoes=["a", "b"], indice_correto=0),
        QuestaoSimulado(id="s2", pergunta="...", opcoes=["a", "b", "c"], indice_correto=2),
        QuestaoSimulado(id="s3", pergunta="...", opcoes=["a", "b"], indice_correto=1),
    ]


def test_simulado_todas_corretas():
    veredicto = corrigir_simulado(_questoes_simulado(), {"s1": 0, "s2": 2, "s3": 1})
    assert veredicto.nota == 3
    assert veredicto.total == 3
    assert veredicto.percentual == 100.0
    assert all(v["correto"] for v in veredicto.por_questao.values())


def test_simulado_todas_erradas():
    veredicto = corrigir_simulado(_questoes_simulado(), {"s1": 1, "s2": 0, "s3": 0})
    assert veredicto.nota == 0
    assert veredicto.percentual == 0.0


def test_simulado_parcialmente_correto():
    veredicto = corrigir_simulado(_questoes_simulado(), {"s1": 0, "s2": 0, "s3": 1})
    assert veredicto.nota == 2
    assert veredicto.total == 3
    assert veredicto.percentual == round(2 / 3 * 100, 1)
    assert veredicto.por_questao["s1"]["correto"] is True
    assert veredicto.por_questao["s2"]["correto"] is False
    assert veredicto.por_questao["s3"]["correto"] is True


def test_simulado_revela_indice_correto_de_todas_as_questoes():
    veredicto = corrigir_simulado(_questoes_simulado(), {})
    assert veredicto.por_questao["s1"]["indice_correto"] == 0
    assert veredicto.por_questao["s2"]["indice_correto"] == 2
    assert veredicto.por_questao["s3"]["indice_correto"] == 1


def test_simulado_questao_ausente_das_respostas_conta_como_errada():
    """Aluno pulou uma questão — não deve levantar exceção."""
    veredicto = corrigir_simulado(_questoes_simulado(), {"s1": 0, "s3": 1})  # s2 ausente
    assert veredicto.nota == 2
    assert veredicto.total == 3
    assert veredicto.por_questao["s2"]["correto"] is False
