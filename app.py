"""Ponto de entrada da aplicação FastAPI. As rotas ficam finas — validação,
limite de chamadas e registro de custo/tempo vivem em módulos separados
(validacao.py, limitador.py, custos.py), e o prompt pedagógico fica em
prompts/pedagogico.txt, fora do código de integração com a API.
"""

import base64
import logging
import os
import time

# load_dotenv() precisa rodar ANTES de importar config (ou qualquer módulo
# que leia variáveis de ambiente no carregamento) — caso contrário, valores
# definidos em .env são ignorados silenciosamente na primeira importação.
from dotenv import load_dotenv

load_dotenv()

import anthropic
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import custos
import limitador
import validacao
from config import (
    BASE_DIR,
    ENABLE_PAID_API_CALLS,
    MAX_TOKENS_RESPOSTA,
    MODEL,
    PROMPT_PEDAGOGICO_PATH,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("poc-estudos-ia")

SYSTEM_PROMPT = PROMPT_PEDAGOGICO_PATH.read_text(encoding="utf-8")

app = FastAPI()


@app.exception_handler(Exception)
async def manipulador_erro_generico(request: Request, exc: Exception):
    # Loga o erro completo só no servidor (nunca a imagem, a explicação ou a
    # chave de API — não aparecem nesses objetos). Ao cliente, só uma
    # mensagem genérica, sem stack trace nem detalhes internos.
    logger.exception("Erro não tratado em %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno no servidor. Consulte os logs locais do uvicorn."},
    )


@app.get("/")
async def raiz():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.post("/explicar")
async def explicar(imagem: UploadFile = File(...)):
    conteudo = await imagem.read()

    try:
        validacao.validar(conteudo, imagem.content_type)
    except validacao.ImagemInvalida as erro:
        raise HTTPException(status_code=400, detail=str(erro))

    # Trava de segurança: nenhuma chamada real (paga) à Anthropic acontece
    # enquanto ENABLE_PAID_API_CALLS não for "true" no .env. Este bloco roda
    # antes de qualquer referência ao SDK — não há caminho de código que
    # alcance `anthropic.Anthropic()` com a trava desativada.
    if not ENABLE_PAID_API_CALLS:
        raise HTTPException(
            status_code=403,
            detail=(
                "Chamadas pagas à API da Anthropic estão desabilitadas "
                "(ENABLE_PAID_API_CALLS=false no .env). Esta é uma trava de "
                "segurança deliberada — defina ENABLE_PAID_API_CALLS=true "
                "manualmente no .env e reinicie o servidor para autorizar "
                "chamadas reais."
            ),
        )

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY não configurada. Edite o arquivo .env e reinicie o servidor.",
        )

    try:
        limitador.verificar_e_incrementar()
    except limitador.LimiteDeChamadasAtingido as erro:
        raise HTTPException(status_code=429, detail=str(erro))

    imagem_base64 = base64.b64encode(conteudo).decode("utf-8")

    inicio = time.monotonic()
    try:
        client = anthropic.Anthropic()
        resposta = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS_RESPOSTA,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": imagem.content_type,
                                "data": imagem_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Aqui está a foto do meu exercício escolar. Pode me ajudar?",
                        },
                    ],
                }
            ],
        )
    except anthropic.AuthenticationError:
        raise HTTPException(
            status_code=500,
            detail="Chave de API inválida. Verifique a ANTHROPIC_API_KEY no .env.",
        )
    except anthropic.RateLimitError:
        raise HTTPException(
            status_code=429,
            detail="Limite de requisições da API da Anthropic atingido. Tente novamente em breve.",
        )
    except anthropic.APIConnectionError:
        raise HTTPException(status_code=502, detail="Falha de conexão com a API da Anthropic.")
    except anthropic.APIStatusError:
        logger.exception("Erro da API da Anthropic")
        raise HTTPException(status_code=502, detail="A API da Anthropic retornou um erro.")

    tempo_resposta_s = time.monotonic() - inicio

    explicacao = "".join(bloco.text for bloco in resposta.content if bloco.type == "text")

    custo_usd = custos.registrar(
        MODEL, resposta.usage.input_tokens, resposta.usage.output_tokens, tempo_resposta_s
    )

    return JSONResponse(
        {
            "explicacao": explicacao,
            "modelo": MODEL,
            "input_tokens": resposta.usage.input_tokens,
            "output_tokens": resposta.usage.output_tokens,
            "tempo_resposta_s": round(tempo_resposta_s, 3),
            "custo_usd_estimado": round(custo_usd, 6),
            "chamadas_restantes": limitador.chamadas_restantes(),
        }
    )


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
