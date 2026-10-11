"""Rotas de materiais educacionais. Rotas finas: carregam o material,
delegam para correcao.py, e formatam a resposta — nenhuma lógica de
correção nem acesso a arquivo mora aqui.

Zero import de `anthropic`, `config.ENABLE_PAID_API_CALLS`, `limitador`,
`autorizacao` ou `custos` — esta funcionalidade nunca toca a API da
Anthropic nem as travas de custo do projeto.
"""

from pathlib import Path
from typing import Literal, Union

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

import correcao
import materiais_loader
from schemas import MaterialEducacional, material_para_gabarito, material_para_publico

BASE_DIR = Path(__file__).resolve().parent.parent

router = APIRouter()


def _carregar_ou_404(material_id: str) -> MaterialEducacional:
    try:
        return materiais_loader.load_material(material_id)
    except materiais_loader.MaterialNaoEncontrado:
        raise HTTPException(status_code=404, detail="Material não encontrado.")
    except materiais_loader.MaterialInvalido:
        raise HTTPException(status_code=500, detail="Material inválido. Consulte os logs locais.")


# --------------------------------------------------------------------------
# Corpo da requisição de correção — união discriminada em "tipo"
# --------------------------------------------------------------------------


class CorrigirExercicioRequest(BaseModel):
    tipo: Literal["exercicio"]
    item_id: str
    resposta: dict[str, float]


class CorrigirQuizRequest(BaseModel):
    tipo: Literal["quiz"]
    item_id: str
    resposta: int


CorrigirRequest = Union[CorrigirExercicioRequest, CorrigirQuizRequest]


# --------------------------------------------------------------------------
# Rotas
# --------------------------------------------------------------------------


@router.get("/materiais/{material_id}")
async def pagina_material(material_id: str):
    # material_id não é usado aqui — a página lê o id da própria URL no
    # navegador e busca /api/materiais/{id}. Isso só serve o HTML genérico,
    # igual ao padrão de GET / servindo static/index.html.
    return FileResponse(BASE_DIR / "static" / "material.html")


@router.get("/api/materiais/{material_id}")
async def obter_material(material_id: str):
    material = _carregar_ou_404(material_id)
    return material_para_publico(material)


@router.get("/api/materiais/{material_id}/gabarito")
async def obter_gabarito(material_id: str):
    """Lê o material COMPLETO (não o público) e revela exercícios, quiz e
    simulado com resposta e explicação — uma consulta, não uma correção.
    Não exige nenhuma submissão prévia."""
    material = _carregar_ou_404(material_id)
    return material_para_gabarito(material)


@router.post("/api/materiais/{material_id}/corrigir")
async def corrigir(material_id: str, corpo: CorrigirRequest = Body(discriminator="tipo")):
    material = _carregar_ou_404(material_id)

    if corpo.tipo == "exercicio":
        exercicio = next((e for e in material.exercicios if e.id == corpo.item_id), None)
        if exercicio is None:
            raise HTTPException(status_code=404, detail="Exercício não encontrado.")
        veredicto = correcao.corrigir_exercicio(exercicio, corpo.resposta)
        return {
            "correto": veredicto.correto,
            "detalhes_por_campo": veredicto.detalhes_por_campo,
            "explicacao": veredicto.explicacao,
        }

    questao = next((q for q in material.quiz if q.id == corpo.item_id), None)
    if questao is None:
        raise HTTPException(status_code=404, detail="Questão não encontrada.")
    veredicto = correcao.corrigir_quiz(questao, corpo.resposta)
    return {"correto": veredicto.correto, "explicacao": veredicto.explicacao}


class CorrigirSimuladoRequest(BaseModel):
    respostas: dict[str, int]  # item_id -> índice escolhido


@router.post("/api/materiais/{material_id}/simulado/corrigir")
async def corrigir_simulado(material_id: str, corpo: CorrigirSimuladoRequest):
    """Correção em lote: diferente de /corrigir (um item por vez), revela o
    índice correto de TODAS as questões do simulado de uma vez, junto com a
    nota agregada — é exatamente o que "corrigir o simulado inteiro"
    significa, não um vazamento."""
    material = _carregar_ou_404(material_id)
    veredicto = correcao.corrigir_simulado(material.simulado, corpo.respostas)
    return {
        "nota": veredicto.nota,
        "total": veredicto.total,
        "percentual": veredicto.percentual,
        "por_questao": veredicto.por_questao,
    }
