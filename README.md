# Assistente de Estudos — POC (Experimento 1)

Prova de conceito **local** para validar o fluxo: foto de um exercício escolar → IA de visão (Claude) → explicação pedagógica em etapas. Não é o produto comercial — veja [Limitações](#limitações-e-escopo) abaixo.

## Requisitos

- Python 3.11+
- Uma chave de API da Anthropic (gerada em [console.anthropic.com](https://console.anthropic.com))

## Instalação

```bash
cd poc-estudos-ia
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
pip install -r requirements.txt
cp .env.example .env
```

Edite o `.env` e preencha `ANTHROPIC_API_KEY` com sua chave real. Nunca commite esse arquivo (já está no `.gitignore`).

## Execução

```bash
uvicorn app:app --reload
```

Por padrão o uvicorn liga em `127.0.0.1:8000` (não exposto para a rede). Abra **http://127.0.0.1:8000** no navegador, selecione uma imagem JPEG ou PNG (até 5 MB) e envie.

### Trava de segurança: `ENABLE_PAID_API_CALLS`

**Por padrão, nenhuma chamada real (paga) à API da Anthropic é feita.** O backend bloqueia a requisição com `403` *antes* de instanciar o SDK, enquanto `ENABLE_PAID_API_CALLS=false` no `.env` (o padrão). Isso existe para que rodar o servidor, testar a validação de arquivos, ou rodar a suíte automatizada nunca gere custo por acidente.

**Para autorizar uma chamada real, manualmente:**
1. Edite o `.env` e mude `ENABLE_PAID_API_CALLS=false` para `ENABLE_PAID_API_CALLS=true`.
2. Reinicie o servidor (`uvicorn app:app --reload` já recarrega sozinho ao detectar mudança em arquivos `.py`, mas mudanças no `.env` exigem reiniciar o processo manualmente).
3. Envie uma imagem — essa chamada específica vai gerar custo real (também limitada pelo `LIMITE_CHAMADAS`, padrão 5, independente da trava acima).
4. Depois do teste, recomendo voltar `ENABLE_PAID_API_CALLS` para `false`.

Um limitador local independente (`LIMITE_CHAMADAS` no `.env`, padrão 5) também bloqueia novas chamadas depois desse número de chamadas, mesmo com a trava acima ligada. Para zerar a contagem, apague o arquivo `contador_chamadas.json` (gerado automaticamente na primeira chamada).

## Estrutura do projeto

```
poc-estudos-ia/
├── app.py                   # Rotas FastAPI (fino — delega para os módulos abaixo)
├── config.py                 # Configuração central: modelo, preços, limites
├── validacao.py               # Valida tipo, tamanho e conteúdo real da imagem
├── limitador.py                # Limite local de chamadas pagas (persistido em JSON)
├── custos.py                   # Calcula e registra custo/tokens/tempo em CSV
├── prompts/
│   └── pedagogico.txt          # Prompt do sistema, separado do código
├── static/
│   └── index.html              # Formulário de upload + JS vanilla
├── test_images/
│   ├── exemplo_matematica.png  # Imagem de teste sintética (gerada por script)
│   └── gerar_exemplo.py
├── requirements.txt
├── requirements-dev.txt         # Só para rodar os testes (pytest, httpx)
├── test_app.py                  # Testes automatizados, 100% mockados — sem rede
├── .env.example
├── .gitignore
└── custos.csv                  # Gerado em runtime (git-ignorado) — não contém imagens nem texto
```

## Testes

### Testes automatizados (sem custo — SDK da Anthropic sempre mockado)

```bash
pip install -r requirements-dev.txt
pytest test_app.py -v
```

Cobertura:
- Rejeita tipo de arquivo não permitido, arquivo vazio, conteúdo forjado (Content-Type mentiroso) e imagem maior que 5 MB — e confirma, em cada caso, que o mock do SDK **nunca foi chamado** (`assert_not_called()`).
- Confirma que `ENABLE_PAID_API_CALLS=false` bloqueia com `403` mesmo com uma imagem válida, antes de tocar o SDK.
- Confirma que a configuração real do projeto (lida do `.env`) é `ENABLE_PAID_API_CALLS=False` por padrão.
- Testa o limitador de chamadas isoladamente (sem HTTP, sem rede) e via o endpoint (confirma `429` antes do SDK).
- Um teste de fluxo completo com o SDK inteiramente substituído por `unittest.mock.MagicMock` (resposta simulada), provando que a integração (parsing, custo, contagem) funciona sem nenhum byte trafegar pela rede.

Isolamento: cada teste usa arquivos temporários (`tmp_path` do pytest) para o contador de chamadas e o CSV de custos — a suíte nunca lê nem escreve `contador_chamadas.json` ou `custos.csv` reais do projeto.

### Testes manuais locais (sem custo)

1. **Servidor sobe e serve a página**: `curl http://127.0.0.1:8000/` → deve responder `200`.
2. **Rejeita tipo de arquivo não permitido**: enviar um `.txt` para `POST /explicar` → `400`.
3. **Rejeita conteúdo forjado**: enviar um arquivo de texto renomeado para `.png` → `400` ("não é uma imagem válida"), graças à validação real via Pillow.
4. **Rejeita imagem maior que 5 MB** → `400`, antes de qualquer chamada à API.
5. **Trava ativa por padrão**: com `ENABLE_PAID_API_CALLS=false` (padrão), enviar uma imagem válida → `403`, sem custo.

### Teste end-to-end com chamada real (gera custo — exige autorização manual explícita)

Só depois de mudar `ENABLE_PAID_API_CALLS=true` no `.env` deliberadamente (ver seção acima) e reiniciar o servidor:

```bash
curl -X POST http://127.0.0.1:8000/explicar -F "imagem=@test_images/exemplo_matematica.png;type=image/png"
```

Confere: a explicação segue o prompt pedagógico (etapas, sem só a resposta final, termina com uma pergunta), e uma nova linha aparece em `custos.csv`.

## Limitações e escopo

- POC local, sem autenticação, sem banco de dados, sem persistência de conversas — não representa a arquitetura final do produto comercial.
- O limitador de chamadas e o log de custo são mecanismos locais e simples (arquivo JSON/CSV), não substituem controle de orçamento em produção.
- Nenhuma imagem, explicação ou chave de API é gravada em log — apenas metadados (modelo, contagem de tokens, tempo, custo estimado).
- Use apenas imagens de teste sintéticas ou genéricas — nunca fotos reais de crianças identificáveis.
