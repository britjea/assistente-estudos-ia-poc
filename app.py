import base64
import csv
import os
from datetime import datetime, timezone
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")

# Preço por milhão de tokens (USD), input/output. Verificar valores atuais
# antes de confiar neles para projeções de custo reais.
PRECOS_POR_MILHAO = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),  # preço promocional vigente até 2026-08-31
}

TIPOS_PERMITIDOS = {"image/jpeg", "image/png", "image/webp", "image/gif"}
TAMANHO_MAXIMO_BYTES = 10 * 1024 * 1024  # 10 MB

CUSTOS_CSV = Path(__file__).parent / "custos.csv"

SYSTEM_PROMPT = """\
Você é um professor particular paciente, ajudando um estudante do Ensino \
Fundamental a entender um exercício escolar a partir de uma foto.

Siga sempre estas regras:
1. Identifique qual é o exercício mostrado na imagem.
2. Explique, em linguagem simples, o que a questão está pedindo.
3. Guie o raciocínio em etapas curtas e fáceis de entender, usando exemplos \
quando ajudar.
4. NUNCA entregue apenas a resposta final sem explicar o caminho até ela.
5. Termine sempre com uma pergunta simples ou um pequeno desafio para o \
estudante verificar se entendeu.
6. Se a imagem estiver ilegível, cortada, embaçada ou girada a ponto de \
você não conseguir identificar o exercício com confiança, diga isso \
claramente e peça uma foto melhor — não tente adivinhar o conteúdo.
7. Se tiver incerteza sobre algum passo do raciocínio, diga isso \
explicitamente em vez de inventar uma explicação.

Use um tom acolhedor e encorajador, adequado para uma criança ou \
pré-adolescente.
"""

app = FastAPI()


def registrar_custo(modelo: str, input_tokens: int, output_tokens: int) -> float:
    preco_input, preco_output = PRECOS_POR_MILHAO.get(modelo, (0.0, 0.0))
    custo_usd = (input_tokens * preco_input + output_tokens * preco_output) / 1_000_000

    arquivo_novo = not CUSTOS_CSV.exists()
    with open(CUSTOS_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if arquivo_novo:
            writer.writerow(
                ["timestamp_utc", "modelo", "input_tokens", "output_tokens", "custo_usd"]
            )
        writer.writerow(
            [
                datetime.now(timezone.utc).isoformat(),
                modelo,
                input_tokens,
                output_tokens,
                f"{custo_usd:.6f}",
            ]
        )
    return custo_usd


@app.get("/")
async def raiz():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.post("/explicar")
async def explicar(imagem: UploadFile = File(...)):
    if imagem.content_type not in TIPOS_PERMITIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de arquivo não suportado: {imagem.content_type}. "
            f"Envie uma imagem JPEG, PNG, WEBP ou GIF.",
        )

    conteudo = await imagem.read()
    if len(conteudo) > TAMANHO_MAXIMO_BYTES:
        raise HTTPException(status_code=400, detail="Imagem maior que 10 MB.")

    imagem_base64 = base64.b64encode(conteudo).decode("utf-8")

    client = anthropic.Anthropic()

    try:
        resposta = client.messages.create(
            model=MODEL,
            max_tokens=1024,
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
            detail="Chave de API inválida ou não configurada (ANTHROPIC_API_KEY).",
        )
    except anthropic.RateLimitError:
        raise HTTPException(
            status_code=429, detail="Limite de requisições da API atingido. Tente novamente em breve."
        )
    except anthropic.APIConnectionError:
        raise HTTPException(status_code=502, detail="Falha de conexão com a API da Anthropic.")

    explicacao = "".join(
        bloco.text for bloco in resposta.content if bloco.type == "text"
    )

    custo_usd = registrar_custo(
        MODEL, resposta.usage.input_tokens, resposta.usage.output_tokens
    )

    return JSONResponse(
        {
            "explicacao": explicacao,
            "modelo": MODEL,
            "input_tokens": resposta.usage.input_tokens,
            "output_tokens": resposta.usage.output_tokens,
            "custo_usd_estimado": round(custo_usd, 6),
        }
    )


app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
