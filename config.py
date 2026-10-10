"""Configuração central do experimento. Nenhum segredo vive aqui — a chave
de API é lida de variável de ambiente em tempo de execução (ver app.py).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-4-5")

# Preços por milhão de tokens (USD), input/output.
# Fonte: documentação oficial de preços da Anthropic (platform.claude.com/docs/en/pricing).
# Verificado em: 2026-10-10. Reconfirme antes de usar para projeções de custo reais —
# preços promocionais têm data de expiração.
PRECOS_POR_MILHAO = {
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (2.00, 10.00),  # preço promocional vigente até 2026-08-31 (depois volta a 3.00/15.00)
}

TIPOS_PERMITIDOS = {"image/jpeg", "image/png"}
TAMANHO_MAXIMO_BYTES = 5 * 1024 * 1024  # 5 MB

MAX_TOKENS_RESPOSTA = 1024

LIMITE_CHAMADAS_PADRAO = 5
LIMITE_CHAMADAS = int(os.environ.get("LIMITE_CHAMADAS", LIMITE_CHAMADAS_PADRAO))

# Trava de segurança: enquanto estiver "false" (padrão), o backend bloqueia
# QUALQUER chamada real (paga) à API da Anthropic antes de invocar o SDK —
# ver o guard clause em app.py, que roda antes de `anthropic.Anthropic()` ser
# sequer instanciado. Só deve ser definida como "true" manualmente no .env,
# por decisão explícita de quem está rodando o experimento.
ENABLE_PAID_API_CALLS = os.environ.get("ENABLE_PAID_API_CALLS", "false").strip().lower() == "true"

CUSTOS_CSV = BASE_DIR / "custos.csv"
CONTADOR_CHAMADAS_JSON = BASE_DIR / "contador_chamadas.json"
PROMPT_PEDAGOGICO_PATH = BASE_DIR / "prompts" / "pedagogico.txt"

# Autorização de uso único para chamadas reais — mecanismo independente do
# LIMITE_CHAMADAS acima e da trava ENABLE_PAID_API_CALLS. Nunca contém a
# chave de API; é editado manualmente pelo operador (ver autorizacao.py).
# Zero autorizações concedidas por padrão.
AUTORIZACAO_CHAMADA_REAL_JSON = BASE_DIR / "autorizacao_chamada_real.json"
