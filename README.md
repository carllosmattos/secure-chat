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
| `LLM_PROVIDER` | `mock`, `bedrock` | `mock` |
| `DEV_AUTH_BYPASS` | Auth dev sem token | `true` |
| `SECURITY_PROFILE` | `pii-redact` ou `strict` | `pii-redact` |
| `BEDROCK_REGION` | Região AWS | `us-east-1` |
| `BEDROCK_MODEL_ID` | Modelo Claude no Bedrock | Opus |

Para produção: configure OIDC (`OIDC_ISSUER`, `OIDC_CLIENT_ID`), desative `DEV_AUTH_BYPASS`, use Redis para o cofre e `LLM_PROVIDER=bedrock`.

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
