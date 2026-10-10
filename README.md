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

Um limitador local independente (`LIMITE_CHAMADAS` no `.env`, padrão 5) também bloqueia novas chamadas depois desse número de chamadas, mesmo com a trava acima ligada. Para zerar a contagem, apague o arquivo `contador_chamadas.json` (gerado automaticamente na primeira chamada).

### Autorização de uso único para UMA chamada real

Além da trava `ENABLE_PAID_API_CALLS` e do limitador geral acima, existe um **terceiro mecanismo, independente dos outros dois**: uma autorização explícita e de uso único, para permitir no máximo uma chamada real por vez. As três proteções são cumulativas — uma chamada só acontece se **todas** permitirem.

- Persistida em `autorizacao_chamada_real.json` (git-ignorado), **nunca** contém a chave de API.
- Saldo **zero por padrão** (arquivo ausente = 0 autorizações).
- Consumida **atomicamente** (lock de arquivo via `fcntl.flock`) imediatamente antes de qualquer tentativa de chamada ao SDK — duas requisições concorrentes não conseguem gastar a mesma autorização.
- A autorização é gasta **antes** da chamada acontecer. Se a chamada falhar (erro de rede, erro da API, o processo cair no meio do caminho) ou o servidor for reiniciado, **a autorização não volta sozinha** — é preciso reautorizar manualmente editando o arquivo de novo.
- O cliente do SDK é criado com `max_retries=0`, para que uma falha não dispare retries automáticos internos do SDK (que, por padrão, tentaria novamente em erros como 429/5xx — gerando requisições HTTP reais adicionais por trás de uma única autorização).
- O cliente do SDK também é criado com `timeout=60.0` (segundos), explícito — o padrão do SDK, se omitido, é 10 minutos. 60s dá folga generosa sobre o tempo de resposta observado em testes anteriores (~3s) sem deixar a requisição presa indefinidamente.

**Para autorizar exatamente UMA chamada real:**

1. Confirme (ou crie) o arquivo `autorizacao_chamada_real.json` na raiz do projeto com:
   ```json
   {"chamadas_restantes": 1}
   ```
2. Mude `ENABLE_PAID_API_CALLS=false` para `true` no `.env`.
3. Reinicie o servidor (mudanças em `.env` não são pegas pelo `--reload`).
4. Envie **uma** imagem — essa é a única chamada autorizada. Uma segunda tentativa, mesmo imediatamente em seguida, será bloqueada com `403`.

**Para verificar o consumo e o custo depois:**
- `cat autorizacao_chamada_real.json` → `chamadas_restantes` deve estar em `0`, e `ultima_consumida_em_utc` mostra quando foi consumida.
- `cat custos.csv` → a última linha mostra o modelo, tokens de entrada/saída, tempo de resposta e custo real estimado em USD daquela chamada específica.

**Para autorizar uma nova chamada no futuro**, repita o passo 1 (edite `autorizacao_chamada_real.json` de novo com `chamadas_restantes: 1`) — nunca é reposto automaticamente.

## Estrutura do projeto

```
poc-estudos-ia/
├── app.py                   # Rotas FastAPI (fino — delega para os módulos abaixo)
├── config.py                 # Configuração central: modelo, preços, limites
├── validacao.py               # Valida tipo, tamanho e conteúdo real da imagem
├── limitador.py                # Limite geral local de chamadas (persistido em JSON)
├── autorizacao.py               # Autorização de uso único para 1 chamada real (lock de arquivo)
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
pytest -v
```

Cobertura (`test_app.py`, nível do endpoint HTTP):
- Rejeita tipo de arquivo não permitido, arquivo vazio, conteúdo forjado (Content-Type mentiroso) e imagem maior que 5 MB — e confirma, em cada caso, que o mock do SDK **nunca foi chamado** (`assert_not_called()`).
- Confirma que `ENABLE_PAID_API_CALLS=false` bloqueia com `403` mesmo com uma imagem válida, antes de tocar o SDK.
- Confirma que a configuração real do projeto (lida do `.env`) é `ENABLE_PAID_API_CALLS=False` por padrão.
- Testa o limitador geral isoladamente (sem HTTP, sem rede) e via o endpoint (confirma `429` antes do SDK).
- Confirma que, com zero autorizações de chamada real (o padrão), o endpoint bloqueia com `403` mesmo com tudo mais liberado.
- Confirma que, com exatamente 1 autorização concedida, a primeira chamada passa (mockada) e a segunda — imediatamente em seguida — é bloqueada; o mock do SDK só é "chamado" uma única vez no total.
- Confirma que o cliente do SDK é instanciado com `max_retries=0` e `timeout=60.0`.
- Um teste de fluxo completo com o SDK inteiramente substituído por `unittest.mock.MagicMock` (resposta simulada), provando que a integração (parsing, custo, contagem) funciona sem nenhum byte trafegar pela rede.

Cobertura (`test_autorizacao.py`, nível do módulo de autorização):
- Padrão é zero autorizações; consumir uma concedida funciona; a segunda tentativa após consumir é bloqueada.
- **Simula reinício da aplicação** (recarrega o módulo Python do zero via `importlib.reload`) e confirma que o saldo consumido continua em 0 — não existe nenhum contador em memória que sobrevive ou reseta entre reinícios, só o arquivo em disco.
- Confirma que uma falha simulada após consumir a autorização não a repõe.
- **Testa concorrência de verdade**: duas threads tentando consumir a mesma autorização simultaneamente (via `threading.Barrier`) — confirma que exatamente uma tem sucesso e a outra é bloqueada, graças ao lock de arquivo (`fcntl.flock`).

Isolamento: cada teste usa arquivos temporários (`tmp_path` do pytest) para o contador de chamadas, o CSV de custos e o arquivo de autorização — a suíte nunca lê nem escreve `contador_chamadas.json`, `custos.csv` ou `autorizacao_chamada_real.json` reais do projeto.

### Testes manuais locais (sem custo)

1. **Servidor sobe e serve a página**: `curl http://127.0.0.1:8000/` → deve responder `200`.
2. **Rejeita tipo de arquivo não permitido**: enviar um `.txt` para `POST /explicar` → `400`.
3. **Rejeita conteúdo forjado**: enviar um arquivo de texto renomeado para `.png` → `400` ("não é uma imagem válida"), graças à validação real via Pillow.
4. **Rejeita imagem maior que 5 MB** → `400`, antes de qualquer chamada à API.
5. **Trava ativa por padrão**: com `ENABLE_PAID_API_CALLS=false` (padrão), enviar uma imagem válida → `403`, sem custo.

### Teste end-to-end com chamada real (gera custo — exige autorização manual explícita)

Só depois de seguir os 3 passos da seção "Autorização de uso único" acima (`autorizacao_chamada_real.json` com `chamadas_restantes: 1`, `ENABLE_PAID_API_CALLS=true`, servidor reiniciado):

```bash
curl -X POST http://127.0.0.1:8000/explicar -F "imagem=@test_images/exemplo_matematica.png;type=image/png"
```

Confere: a explicação segue o prompt pedagógico (etapas, sem só a resposta final, termina com uma pergunta), e uma nova linha aparece em `custos.csv`.

## Limitações e escopo

- POC local, sem autenticação, sem banco de dados, sem persistência de conversas — não representa a arquitetura final do produto comercial.
- O limitador de chamadas e o log de custo são mecanismos locais e simples (arquivo JSON/CSV), não substituem controle de orçamento em produção.
- Nenhuma imagem, explicação ou chave de API é gravada em log — apenas metadados (modelo, contagem de tokens, tempo, custo estimado).
- Use apenas imagens de teste sintéticas ou genéricas — nunca fotos reais de crianças identificáveis.
