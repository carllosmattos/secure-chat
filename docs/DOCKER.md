# Docker Compose quick start

## Before you start

Stop any **local** backend/frontend still running on ports **3000** and **8000** (old `uvicorn` / `npm run dev` processes). Otherwise Docker cannot bind those ports and the browser may hit the wrong backend.

## Setup

```bash
cp docker/postgres.env.example docker/postgres.env
cp docker/stack.env.example docker/stack.env
# Use the same password in both files (replace changeme)

cp backend/.env.example backend/.env
# Edit backend/.env (OpenRouter key, models, etc.)

docker compose up -d --build
```

Open http://localhost:3000

## Commands

```bash
docker compose ps
docker compose logs -f backend
docker compose down
docker compose up -d --build   # after code or .env changes
```

## Ports

| Service  | URL |
|----------|-----|
| Frontend | http://localhost:3000 |
| Backend  | http://localhost:8000 |
| Postgres | localhost:5433 |
| Redis    | localhost:6379 |

## Notes

- `backend/.env` supplies LLM keys and app settings.
- `docker/stack.env` overrides `DATABASE_URL` / `REDIS_URL` for the Docker network.
- Postgres uses `trust` auth on the internal network (local dev only).
