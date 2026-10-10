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
from schemas import material_para_publico

BASE_DIR = Path(__file__).resolve().parent.parent

router = APIRouter()


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
    try:
        material = materiais_loader.load_material(material_id)
    except materiais_loader.MaterialNaoEncontrado:
        raise HTTPException(status_code=404, detail="Material não encontrado.")
    except materiais_loader.MaterialInvalido as erro:
        raise HTTPException(status_code=500, detail="Material inválido. Consulte os logs locais.")

    return material_para_publico(material)


@router.post("/api/materiais/{material_id}/corrigir")
async def corrigir(material_id: str, corpo: CorrigirRequest = Body(discriminator="tipo")):
    try:
        material = materiais_loader.load_material(material_id)
    except materiais_loader.MaterialNaoEncontrado:
        raise HTTPException(status_code=404, detail="Material não encontrado.")
    except materiais_loader.MaterialInvalido:
        raise HTTPException(status_code=500, detail="Material inválido. Consulte os logs locais.")

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
