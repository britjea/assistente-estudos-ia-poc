"""Testes automatizados — NENHUM destes testes faz uma chamada de rede real.

Garantias de isolamento:
- O SDK da Anthropic (`anthropic.Anthropic`) é sempre substituído por um
  `unittest.mock.MagicMock` antes de qualquer teste que passe pela trava
  ENABLE_PAID_API_CALLS=true — um MagicMock não executa código de rede, então
  é estruturalmente impossível esses testes tocarem a API real.
- A trava `ENABLE_PAID_API_CALLS` é manipulada via `monkeypatch.setattr` no
  objeto `app` já importado, nunca escrevendo no arquivo `.env` real.
- O arquivo `contador_chamadas.json` do limitador é redirecionado para um
  arquivo temporário por teste (`monkeypatch` + `tmp_path`), para nunca ler
  ou sobrescrever o contador real do projeto.
- Nenhum teste aqui assume ou requer ANTHROPIC_API_KEY real — quando
  necessário, usamos um valor falso só para passar a checagem de "chave
  configurada" (a chave falsa nunca é usada para uma chamada de verdade,
  porque o SDK está mockado).

Rodar com: ../venv/bin/pytest test_app.py -v
"""

import io
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import app as app_module
import custos
import limitador

client = TestClient(app_module.app)


def _png_valido_bytes() -> bytes:
    """Gera, em memória, uma imagem PNG pequena e genuína (sem precisar de
    arquivo em disco nem de chamada de rede)."""
    buffer = io.BytesIO()
    Image.new("RGB", (100, 100), color="white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def sdk_nunca_deve_ser_tocado():
    """Substitui anthropic.Anthropic por um Mock em TODOS os testes, por
    padrão. Um teste que precise de uma resposta simulada do SDK sobrescreve
    esse comportamento explicitamente (ver test_fluxo_feliz_com_sdk_mockado).
    Isso garante que, mesmo que algum teste tenha um bug e acabe alcançando
    o código de chamada ao SDK, o que será "chamado" é só um objeto em
    memória — nunca uma requisição de rede real.
    """
    with patch("anthropic.Anthropic") as mock_classe_anthropic:
        yield mock_classe_anthropic


@pytest.fixture(autouse=True)
def isolar_contador_de_chamadas(tmp_path, monkeypatch):
    """Redireciona o arquivo do limitador para um caminho temporário,
    exclusivo de cada teste — nunca lê nem escreve o contador real do
    projeto (contador_chamadas.json na raiz)."""
    caminho_temporario = tmp_path / "contador_chamadas_teste.json"
    monkeypatch.setattr(limitador, "CONTADOR_CHAMADAS_JSON", caminho_temporario)
    yield caminho_temporario


@pytest.fixture(autouse=True)
def isolar_csv_de_custos(tmp_path, monkeypatch):
    """Redireciona o CSV de custos para um caminho temporário — nunca
    escreve no custos.csv real do projeto, nem com dados simulados."""
    caminho_temporario = tmp_path / "custos_teste.csv"
    monkeypatch.setattr(custos, "CUSTOS_CSV", caminho_temporario)
    yield caminho_temporario


# --- Validação de arquivos (nunca deveriam alcançar o SDK) ------------------


def test_rejeita_tipo_de_arquivo_nao_permitido(sdk_nunca_deve_ser_tocado):
    resp = client.post(
        "/explicar",
        files={"imagem": ("arquivo.txt", b"nao sou uma imagem", "text/plain")},
    )
    assert resp.status_code == 400
    assert "não suportado" in resp.json()["detail"]
    sdk_nunca_deve_ser_tocado.assert_not_called()


def test_rejeita_arquivo_vazio(sdk_nunca_deve_ser_tocado):
    resp = client.post(
        "/explicar",
        files={"imagem": ("vazio.png", b"", "image/png")},
    )
    assert resp.status_code == 400
    assert "vazio" in resp.json()["detail"]
    sdk_nunca_deve_ser_tocado.assert_not_called()


def test_rejeita_conteudo_forjado_nao_e_imagem_de_verdade(sdk_nunca_deve_ser_tocado):
    """Content-Type declarado como image/png, mas os bytes não são um PNG
    real — a validação real via Pillow deve pegar isso, não só o header."""
    resp = client.post(
        "/explicar",
        files={"imagem": ("falso.png", b"isto e so texto, nao e um png", "image/png")},
    )
    assert resp.status_code == 400
    assert "não é uma imagem válida" in resp.json()["detail"]
    sdk_nunca_deve_ser_tocado.assert_not_called()


def test_rejeita_arquivo_maior_que_5mb(sdk_nunca_deve_ser_tocado):
    """Usa dados locais (bytes crus, sem imagem válida) maiores que 5 MB —
    a checagem de tamanho acontece ANTES da validação de conteúdo real,
    então nem precisamos de uma imagem válida gigante para este teste."""
    seis_mb_de_bytes = b"\x00" * (6 * 1024 * 1024)
    resp = client.post(
        "/explicar",
        files={"imagem": ("grande.png", seis_mb_de_bytes, "image/png")},
    )
    assert resp.status_code == 400
    assert "maior que 5 MB" in resp.json()["detail"]
    sdk_nunca_deve_ser_tocado.assert_not_called()


# --- Trava ENABLE_PAID_API_CALLS --------------------------------------------


def test_bloqueia_chamada_real_quando_trava_desativada(monkeypatch, sdk_nunca_deve_ser_tocado):
    """Mesmo com uma imagem perfeitamente válida, se ENABLE_PAID_API_CALLS
    for False (o padrão), o endpoint deve recusar ANTES de instanciar o SDK."""
    monkeypatch.setattr(app_module, "ENABLE_PAID_API_CALLS", False)

    resp = client.post(
        "/explicar",
        files={"imagem": ("exemplo.png", _png_valido_bytes(), "image/png")},
    )

    assert resp.status_code == 403
    assert "ENABLE_PAID_API_CALLS=false" in resp.json()["detail"]
    sdk_nunca_deve_ser_tocado.assert_not_called()


def test_configuracao_padrao_do_projeto_e_trava_desativada():
    """Confirma que o valor realmente carregado de config.py (a partir do
    .env do projeto) é False — ou seja, a trava está ativa por padrão no
    projeto real, não só nos testes."""
    import config

    assert config.ENABLE_PAID_API_CALLS is False


# --- Limitador de chamadas (sem rede) ---------------------------------------


def test_limitador_bloqueia_quando_limite_ja_atingido(isolar_contador_de_chamadas):
    import json

    isolar_contador_de_chamadas.write_text(
        json.dumps({"chamadas_realizadas": 5, "limite": 5})
    )

    with pytest.raises(limitador.LimiteDeChamadasAtingido):
        limitador.verificar_e_incrementar()


def test_limitador_permite_e_incrementa_quando_abaixo_do_limite(isolar_contador_de_chamadas):
    assert limitador.chamadas_restantes() == 5  # arquivo não existe ainda -> 0 usadas
    limitador.verificar_e_incrementar()
    assert limitador.chamadas_restantes() == 4


def test_endpoint_bloqueia_com_429_quando_limite_atingido_mesmo_com_trava_ligada(
    monkeypatch, isolar_contador_de_chamadas, sdk_nunca_deve_ser_tocado
):
    """Confirma que o limitador bloqueia (429) mesmo que ENABLE_PAID_API_CALLS
    esteja True — ou seja, as duas travas são independentes, e nenhuma delas
    sozinha é suficiente para alcançar o SDK."""
    import json

    monkeypatch.setattr(app_module, "ENABLE_PAID_API_CALLS", True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-falsa-so-para-o-teste")
    isolar_contador_de_chamadas.write_text(
        json.dumps({"chamadas_realizadas": 5, "limite": 5})
    )

    resp = client.post(
        "/explicar",
        files={"imagem": ("exemplo.png", _png_valido_bytes(), "image/png")},
    )

    assert resp.status_code == 429
    sdk_nunca_deve_ser_tocado.assert_not_called()


# --- Fluxo completo, com o SDK mockado (prova que a integração funciona, ---
# --- sem nenhuma chamada de rede real) --------------------------------------


def test_fluxo_feliz_com_sdk_mockado(monkeypatch, sdk_nunca_deve_ser_tocado):
    """Com a trava ligada deliberadamente SÓ DENTRO DESTE TESTE (não altera
    o .env real) e o SDK inteiro substituído por um MagicMock, confirmamos
    que o código de integração (parsing da resposta, cálculo de custo,
    contagem de chamadas restantes) funciona corretamente — sem que
    nenhum byte trafegue pela rede."""
    monkeypatch.setattr(app_module, "ENABLE_PAID_API_CALLS", True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "chave-falsa-so-para-o-teste")

    resposta_simulada = MagicMock()
    resposta_simulada.content = [MagicMock(type="text", text="Explicação simulada, sem custo real.")]
    resposta_simulada.usage = MagicMock(input_tokens=100, output_tokens=50)

    instancia_mock = sdk_nunca_deve_ser_tocado.return_value
    instancia_mock.messages.create.return_value = resposta_simulada

    resp = client.post(
        "/explicar",
        files={"imagem": ("exemplo.png", _png_valido_bytes(), "image/png")},
    )

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["explicacao"] == "Explicação simulada, sem custo real."
    assert corpo["input_tokens"] == 100
    assert corpo["output_tokens"] == 50
    assert corpo["chamadas_restantes"] == 4

    # Prova de que a "chamada" foi inteiramente ao mock, uma única vez.
    instancia_mock.messages.create.assert_called_once()
    assert instancia_mock.messages.create.call_args.kwargs["model"] == app_module.MODEL
