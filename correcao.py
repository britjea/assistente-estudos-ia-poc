"""Lógica de correção de exercícios e quiz — funções puras, sem nenhum
import de FastAPI/HTTP. Totalmente testável sem subir um servidor.

Separar isto da apresentação (routers/materiais.py) é o que permite que a
rota pública nunca precise conhecer a resposta certa: ela só recebe a
resposta do aluno e devolve um veredito, sem o material completo (com
gabarito) nunca passar pelo navegador antes da correção.
"""

from dataclasses import dataclass

from schemas import (
    Exercicio,
    QuestaoQuiz,
    RespostaCoordenadas,
    RespostaNumerica,
    RespostaNumericaComId,
)


class ItemNaoEncontrado(Exception):
    pass


@dataclass
class VeredictoExercicio:
    correto: bool
    detalhes_por_campo: dict[str, bool]
    explicacao: str | None


@dataclass
class VeredictoQuiz:
    correto: bool
    explicacao: str


def _dentro_da_tolerancia(enviado: float, esperado: float, tolerancia: float) -> bool:
    return abs(enviado - esperado) <= tolerancia


def corrigir_exercicio(
    exercicio: Exercicio, respostas: dict[str, float]
) -> VeredictoExercicio:
    """respostas: {campo_id: valor_enviado}. Para 'num'/'numid' é um dict de
    uma chave só; para 'coord', uma chave por campo."""
    resposta = exercicio.resposta

    if isinstance(resposta, RespostaNumerica):
        enviado = respostas.get("valor")
        ok = enviado is not None and _dentro_da_tolerancia(
            enviado, resposta.valor_esperado, resposta.tolerancia
        )
        return VeredictoExercicio(
            correto=ok,
            detalhes_por_campo={"valor": ok},
            explicacao=exercicio.explicacao,
        )

    if isinstance(resposta, RespostaNumericaComId):
        enviado = respostas.get(resposta.campo_id)
        ok = enviado is not None and _dentro_da_tolerancia(
            enviado, resposta.valor_esperado, resposta.tolerancia
        )
        return VeredictoExercicio(
            correto=ok,
            detalhes_por_campo={resposta.campo_id: ok},
            explicacao=exercicio.explicacao,
        )

    if isinstance(resposta, RespostaCoordenadas):
        detalhes: dict[str, bool] = {}
        for campo in resposta.campos:
            enviado = respostas.get(campo.campo_id)
            detalhes[campo.campo_id] = enviado is not None and _dentro_da_tolerancia(
                enviado, campo.valor_esperado, campo.tolerancia
            )
        return VeredictoExercicio(
            correto=all(detalhes.values()) and len(detalhes) > 0,
            detalhes_por_campo=detalhes,
            explicacao=exercicio.explicacao,
        )

    raise TypeError(f"tipo de resposta desconhecido: {type(resposta)!r}")


def corrigir_quiz(questao: QuestaoQuiz, indice_enviado: int) -> VeredictoQuiz:
    """Um índice fora do range [0, len(opcoes)) é tratado como resposta
    errada, não como erro — um cliente malicioso ou com bug mandando 999
    não deve derrubar a correção."""
    correto = 0 <= indice_enviado < len(questao.opcoes) and indice_enviado == questao.indice_correto
    return VeredictoQuiz(correto=correto, explicacao=questao.explicacao)
