"""Carrega um material educacional de materiais/{id}.json, validando com
Pydantic. Falha alta: JSON ausente, malformado ou que não bate com o schema
levanta uma exceção clara — nunca degrada silenciosamente para uma página
pela metade.

Sem cache: cada chamada relê o arquivo do zero. Isso é deliberado — é uma
ferramenta local de uso didático, e ver uma edição de conteúdo refletir sem
precisar reiniciar o servidor importa mais do que a economia de uma leitura
de arquivo pequeno.
"""

import json
import re
from pathlib import Path

import pydantic

from config import BASE_DIR
from schemas import MaterialEducacional

MATERIAIS_DIR = BASE_DIR / "materiais"

# Whitelist estrita: minúsculas, dígitos, hífen. Isso sozinho já bloqueia
# "..", "/", bytes nulos e caminhos absolutos — nenhum desses caracteres
# está no conjunto permitido.
_ID_VALIDO = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class MaterialNaoEncontrado(Exception):
    pass


class MaterialInvalido(Exception):
    pass


def load_material(material_id: str) -> MaterialEducacional:
    if not _ID_VALIDO.fullmatch(material_id):
        raise MaterialNaoEncontrado(f"id de material inválido: {material_id!r}")

    caminho = (MATERIAIS_DIR / f"{material_id}.json").resolve()

    # Segunda camada de defesa (a regex acima já deveria ser suficiente
    # sozinha, mas path traversal é barato de checar duas vezes).
    if MATERIAIS_DIR.resolve() not in caminho.parents:
        raise MaterialNaoEncontrado(f"id de material inválido: {material_id!r}")

    if not caminho.is_file():
        raise MaterialNaoEncontrado(f"material não encontrado: {material_id!r}")

    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except json.JSONDecodeError as erro:
        raise MaterialInvalido(f"JSON malformado em {caminho.name}: {erro}")

    try:
        material = MaterialEducacional.model_validate(dados)
    except pydantic.ValidationError as erro:
        raise MaterialInvalido(f"schema inválido em {caminho.name}: {erro}")

    if material.id != material_id:
        raise MaterialInvalido(
            f"campo 'id' do JSON ({material.id!r}) não corresponde ao nome "
            f"do arquivo ({material_id!r})"
        )

    return material
