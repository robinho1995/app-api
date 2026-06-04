# MBA DevOps + SRE com IA — Aplicação de Referência

Aplicação FastAPI usada como fio condutor em todos os módulos do curso.

## SLOs Definidos

| SLI | SLO | Error Budget |
|---|---|---|
| Availability | 99.9% | 43.2 min/mês |
| Latency p99 | < 500ms | — |
| Latency p95 | < 200ms | — |
| Error Rate | < 0.1% | — |

## Endpoints

- `GET /health` — Health check
- `GET /ready` — Readiness check (dependências)
- `GET /api/v1/items` — Lista itens (paginado)
- `GET /api/v1/items/{id}` — Detalhe de item
- `POST /api/v1/items` — Cria item
- `DELETE /api/v1/items/{id}` — Remove item

## Stack

- **Runtime:** Python 3.11+ / FastAPI / Uvicorn
- **Database:** PostgreSQL 16
- **Cache:** Redis 7
- **ORM:** SQLAlchemy 2.0 (async)
- **Migrations:** Alembic

## Quick Start

```bash
# Dependencies
pip install -r requirements.txt

# Run with Docker Compose (Postgres + Redis)
docker compose up -d

# Run migrations
alembic upgrade head

# Run the app
uvicorn app.main:app --reload --port 8000

# Test
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/items
```

## Estrutura

```
app/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app, middleware, lifespan
│   ├── config.py        # Settings (env vars)
│   ├── database.py      # SQLAlchemy async session
│   ├── models.py         # SQLAlchemy models
│   ├── schemas.py       # Pydantic schemas
│   ├── crud.py           # CRUD operations
│   └── routers/
│       ├── __init__.py
│       ├── health.py    # /health, /ready
│       └── items.py     # /api/v1/items
├── alembic/
│   └── versions/
├── tests/
│   ├── __init__.py
│   └── test_items.py
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
└── README.md
```

## Nota para o Curso

Esta aplicação é o **fio condutor** do curso. Cada módulo adiciona uma camada sobre ela:

| Módulo | O que é adicionado ao repositório |
|--------|-------------------------------------|
| **Módulo 1** | Dockerfile, Kubernetes manifests, docker-compose de produção, runbooks, design docs, skills |
| **Módulo 2** | CI/CD pipeline (GitHub Actions), security agent, prompt versioning |
| **Módulo 3** | OpenTelemetry instrumentation, SLI/SLO definitions, MCP servers config, Docker Compose de observabilidade (Prometheus + Grafana + LangFuse) |
| **Módulo 4** | Troubleshooting agent, RAG index sobre runbooks, ChatOps integration |
| **Módulo 5** | Webhook receptor (`/webhook/incident`), agente orquestrador (`operational_agent.py`), kill switch, audit log, modos copilot/semi-autônomo |

**O Módulo 5 NÃO começa do zero** — ele integra tudo que foi construído nos módulos anteriores. A aplicação FastAPI, os manifests, os runbooks, a instrumentação OTel e os MCP servers já existem. O que o Módulo 5 adiciona é a camada orquestradora que conecta tudo em um agente operacional end-to-end.

Tudo isso é gerado via prompt e construído progressivamente ao longo do curso.