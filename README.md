# Secure Chat — Fase 1 (MVP)

Chat corporativo com pipeline de detecção/redação de PII e bloqueio de credenciais **antes** de qualquer chamada ao LLM.

## Arquitetura

```
UI (Next.js) → FastAPI → Detector/Redactor → Cofre efêmero → LLM (Bedrock/Mock) → Re-hidratação → UI
```

- **Segredos** (JWT, Bearer, PEM, AWS keys, JDBC): bloqueio imediato
- **PII** (CPF, CNPJ, email, telefone, nome, etc.): redação reversível com placeholders `[CPF_1]`
- Valores reais ficam no cofre efêmero (memória cifrada); **nunca** vão ao LLM nem ao banco
- Audit log persiste apenas metadados (hash, contagens, latência)

## Estrutura

```
secure-chat/
  backend/                    # FastAPI
  frontend/                   # Next.js
  packages/security_patterns/ # Detector/redactor Python
  docker-compose.yml          # Postgres + Redis
```

## Pré-requisitos

- Python 3.11+
- Node.js 20+
- Docker (para Postgres/Redis)
- Tesseract OCR (opcional, para OCR de imagens)

## Início rápido

### 1. Infraestrutura

```bash
docker compose up -d
```

### 2. Pacote security_patterns

```bash
cd packages/security_patterns
pip install -e ".[dev]"
pytest
```

### 3. Backend

```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
pip install -e ../packages/security_patterns

cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Abra http://localhost:3000

## Configuração

| Variável | Descrição | Default |
|----------|-----------|---------|
| `LLM_PROVIDER` | `mock`, `bedrock`, `ollama`, `openai` | `mock` |
| `LLM_REQUEST_TIMEOUT` | Timeout (s) das chamadas ao LLM | `120` |
| `DEV_AUTH_BYPASS` | Auth dev sem token | `true` |
| `SECURITY_PROFILE` | `pii-redact` ou `strict` | `pii-redact` |
| `OLLAMA_BASE_URL` | URL do servidor Ollama | `http://localhost:11434` |
| `OLLAMA_MODEL` | Modelo carregado no Ollama | `llama3` |
| `OPENAI_BASE_URL` | Endpoint OpenAI-compatível | `https://api.openai.com/v1` |
| `OPENAI_API_KEY` | Chave do provedor (se exigir) | — |
| `OPENAI_MODEL` | Nome do modelo | `gpt-4o-mini` |
| `BEDROCK_REGION` | Região AWS | `us-east-1` |
| `BEDROCK_MODEL_ID` | Modelo Claude no Bedrock | Opus |

Para produção: configure OIDC (`OIDC_ISSUER`, `OIDC_CLIENT_ID`), desative `DEV_AUTH_BYPASS`, use Redis para o cofre e um `LLM_PROVIDER` real.

## Trocar de LLM (qualquer modelo)

A camada de LLM é plugável via um registry em `backend/app/llm/provider.py`. Basta mudar o `.env`:

### Ollama (local — o que você baixou)

```bash
ollama pull llama3        # ou mistral, qwen, phi3, gemma...
ollama serve              # sobe em http://localhost:11434
```

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3
```

### Qualquer endpoint OpenAI-compatível (Groq, OpenRouter, Together, vLLM, LM Studio, OpenAI...)

```env
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=llama-3.3-70b-versatile
OPENAI_API_KEY=gsk_...
```

### Modo `auto` (trocar + balancear + failover)

```env
LLM_PROVIDER=auto
LLM_AUTO_PROVIDERS=ollama,openai,bedrock   # candidatos em ordem de prioridade
LLM_AUTO_STRATEGY=failover                 # failover | round_robin | random
```

- **failover**: tenta os backends na ordem; se um falhar **antes do 1º token**, cai pro próximo.
- **round_robin**: alterna o backend inicial a cada requisição (balanceamento de carga).
- **random**: sorteia o backend inicial a cada requisição.

Em qualquer estratégia, um backend que erra antes de emitir tokens nunca quebra a requisição — o próximo candidato assume.

### Trocar de modelo por requisição (sem reiniciar)

O endpoint de envio aceita `provider` e `model` opcionais (multipart form):

```bash
curl -X POST http://localhost:8000/api/sessions/<id>/messages \
  -F "content=Explique o teorema de Bayes" \
  -F "provider=ollama" \
  -F "model=mistral"
```

Liste os backends disponíveis e a estratégia ativa:

```bash
curl http://localhost:8000/api/llm/providers
```

### Adicionar um backend novo no código

Implemente `LLMProvider` (métodos `stream_completion` e `model_name`) e registre uma linha em `PROVIDER_REGISTRY`:

```python
PROVIDER_REGISTRY = {
    "mock": MockLLMProvider,
    "bedrock": BedrockLLMProvider,
    "ollama": OllamaLLMProvider,
    "openai": OpenAICompatLLMProvider,
    "meu-llm": MeuLLMProvider,  # <- novo
}
```

Todo o pipeline de segurança (redação de PII / bloqueio de segredos) roda **antes** de chegar no provider, então qualquer LLM herda as mesmas garantias.

## API

| Endpoint | Descrição |
|----------|-----------|
| `POST /api/auth/dev-login` | Login dev (gera JWT) |
| `GET /api/sessions` | Lista sessões |
| `POST /api/sessions` | Cria sessão |
| `GET /api/sessions/{id}/messages` | Histórico |
| `POST /api/sessions/{id}/messages` | Envia mensagem (SSE streaming) |
| `GET /health` | Health check |

## Testes de segurança

- Envie um CPF: deve ser redigido (`[CPF_1]`) e re-hidratado na resposta
- Envie `Bearer sk-...`: deve bloquear com aviso
- Anexe arquivo `.pem`: bloqueio imediato
- PDF/DOCX/TXT: texto extraído e escaneado

## Fora de escopo (fase 1)

- Editor de código / modos Agent e Plan
- RAG semântico
- Integração com Cursor IDE
