"""Validação de imagens enviadas pelo usuário: tipo declarado, tamanho e
conteúdo real do arquivo. Não confiamos apenas no Content-Type enviado pelo
navegador — ele pode ser incorreto ou forjado — então confirmamos com a
biblioteca de imagem que os bytes realmente correspondem ao formato alegado.
"""

import io

from PIL import Image, UnidentifiedImageError

from config import TAMANHO_MAXIMO_BYTES, TIPOS_PERMITIDOS

MIME_PARA_FORMATO_PIL = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
}


class ImagemInvalida(Exception):
    pass


def validar(conteudo: bytes, content_type_declarado: str) -> None:
    if content_type_declarado not in TIPOS_PERMITIDOS:
        raise ImagemInvalida(
            f"Tipo de arquivo não suportado: {content_type_declarado}. "
            f"Envie uma imagem JPEG ou PNG."
        )

    if len(conteudo) == 0:
        raise ImagemInvalida("Arquivo de imagem vazio.")

    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        limite_mb = TAMANHO_MAXIMO_BYTES / (1024 * 1024)
        raise ImagemInvalida(f"Imagem maior que {limite_mb:.0f} MB.")

    formato_esperado = MIME_PARA_FORMATO_PIL[content_type_declarado]
    try:
        with Image.open(io.BytesIO(conteudo)) as img:
            img.verify()
        # verify() invalida o objeto da imagem; reabrir para checar o formato real.
        with Image.open(io.BytesIO(conteudo)) as img:
            formato_real = img.format
    except UnidentifiedImageError:
        raise ImagemInvalida(
            "O arquivo enviado não é uma imagem válida (conteúdo não reconhecido)."
        )

    if formato_real != formato_esperado:
        raise ImagemInvalida(
            f"O conteúdo do arquivo parece ser {formato_real}, mas foi "
            f"declarado como {content_type_declarado}. Envie um arquivo "
            f"JPEG ou PNG genuíno."
        )
