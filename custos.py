"""Registro local de custo estimado por chamada, em CSV simples (sem banco
de dados). Serve para comparar a estimativa teórica de custo com o gasto
real medido durante os testes — nunca registra o conteúdo da imagem, o
texto da explicação, nem a chave de API.
"""

import csv
from datetime import datetime, timezone

from config import CUSTOS_CSV, PRECOS_POR_MILHAO


def calcular_custo_usd(modelo: str, input_tokens: int, output_tokens: int) -> float:
    preco_input, preco_output = PRECOS_POR_MILHAO.get(modelo, (0.0, 0.0))
    return (input_tokens * preco_input + output_tokens * preco_output) / 1_000_000


def registrar(
    modelo: str,
    input_tokens: int,
    output_tokens: int,
    tempo_resposta_s: float,
) -> float:
    custo_usd = calcular_custo_usd(modelo, input_tokens, output_tokens)

    arquivo_novo = not CUSTOS_CSV.exists()
    with open(CUSTOS_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if arquivo_novo:
            writer.writerow(
                [
                    "timestamp_utc",
                    "modelo",
                    "input_tokens",
                    "output_tokens",
                    "tempo_resposta_s",
                    "custo_usd",
                ]
            )
        writer.writerow(
            [
                datetime.now(timezone.utc).isoformat(),
                modelo,
                input_tokens,
                output_tokens,
                f"{tempo_resposta_s:.3f}",
                f"{custo_usd:.6f}",
            ]
        )
    return custo_usd
