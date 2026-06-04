# Design Document — app-api

| Campo | Valor |
|---|---|
| **Serviço** | app-api |
| **Owners** | Time SRE |
| **Status** | Em desenvolvimento |
| **Versão** | 1.0.0 |
| **Data** | 2026-05-25 |

### Links

| Recurso | URL |
|---|---|
| Repositório | [GitHub — app-api](https://github.com/org/app-api) |
| Dashboard Grafana | [Grafana — app-api](http://grafana.local/d/app-api) |
| Runbook | [runbooks/api-runbook.md](../runbooks/api-runbook.md) |
| CI/CD | [GitHub Actions](https://github.com/org/app-api/actions) |

---

## 1. Visão Geral

**app-api** é uma API REST em Python 3.11 com FastAPI que expõe endpoints de CRUD para itens (`/api/v1/items`), health check (`/health`) e métricas Prometheus (`/metrics`). Utiliza PostgreSQL 15 como banco de dados principal via SQLAlchemy Async com driver `asyncpg` e Redis 7 como cache de responses e sessões. A observabilidade é garantida por OpenTelemetry SDK exportando traces e métricas via OTLP para um Collector, que alimenta Prometheus e Grafana. Traces de LLM são enviados ao LangFuse para auditoria. O backend LLM é LM Studio executando Qwen ou Gemma localmente.

**Propósito:** Prover uma API REST de alta disponibilidade e baixa latência para gerenciamento de itens, com observabilidade completa e capacidade de auto-scaling.

**SLOs de produção:**

| SLO | Target |
|---|---|
| Disponibilidade | ≥ 99.9% |
| Latência p99 | < 500ms |
| Latência p95 | < 200ms |
| Error rate | < 0.1% |

---

## 2. Arquitetura

### Diagrama de Componentes

```
                        ┌─────────────────────────────────────────────────┐
                        │              Kubernetes (k3d)                    │
                        │                                                 │
  Request ──────────►  │  ┌──────────┐                                  │
                      │  │ app-api   │─────┐                             │
  :8000               │  │ (FastAPI) │     │                             │
                      │  └──────────┘     │                             │
                      │       │           │                             │
                      │       │           ▼                             │
                      │       │    ┌──────────────┐                     │
                      │       │    │  Redis 7      │                     │
                      │       │    │  (cache/sess) │                     │
                      │       │    └──────────────┘                     │
                      │       │                                         │
                      │       ▼                                         │
                      │  ┌──────────────┐                               │
                      │  │ PostgreSQL 15│                               │
                      │  │ (dados)      │                               │
                      │  └──────────────┘                               │
                      │                                                 │
                      │  ┌──────────────┐     ┌─────────────────┐      │
                      │  │ OTel         │────►│ Prometheus      │      │
                      │  │ Collector   │     └────────┬────────┘      │
                      │  └──────┬───────┘              │               │
                      │         │                       ▼               │
                      │         │              ┌────────────────┐       │
                      │         │              │ Grafana         │       │
                      │         │              └────────────────┘       │
                      │         │                                       │
                      │         ▼                                       │
                      │  ┌──────────────┐                               │
                      │  │ LangFuse     │  (traces LLM)                 │
                      │  └──────────────┘                               │
                      │                                                 │
  ┌──────────────┐    │                                                 │
  │ LM Studio    │◄───│── app-api (LLM calls para agents)              │
  │ Qwen/Gemma   │    │                                                 │
  └──────────────┘    └─────────────────────────────────────────────────┘
```

### Fluxo de Dados — Request

```
Client
  │
  ▼
FastAPI (app-api) ─── :8000
  │
  ├── GET /health ──► 200 OK (sem dependência)
  │
  ├── GET /api/v1/items
  │     │
  │     ├── Cache HIT ──► Redis ──► Response (p95 < 200ms)
  │     │
  │     └── Cache MISS ──► PostgreSQL (asyncpg) ──► Cache no Redis ──► Response
  │
  ├── POST /api/v1/items ──► PostgreSQL (asyncpg) ──► Invalidate Redis ──► Response
  │
  └── GET /metrics ──► Prometheus exposition (sem dependência)
```

### Fluxo de Métricas e Observabilidade

```
app-api (FastAPI)
  │
  │ OTLP (gRPC :4317)
  ▼
OTel Collector
  │
  ├── PromQL metrics ──► Prometheus ──► Grafana (dashboards + alertas)
  │
  └── OTLP traces ──► LangFuse (LLM traces)

app-api (embedded)
  └── GET /metrics ──► Prometheus (scrape direto)
```

---

## 3. Dependências

| Dependência | Versão | Localização | SLA | Impacto se indisponível |
|---|---|---|---|---|
| **PostgreSQL** | 15-alpine | StatefulSet `postgresql` no namespace `demo-app-mba`, service `postgresql-svc:5432` | 99.9% | **Crítico** —Todas as operações de CRUD falham com 500/503. Viola SLO de disponibilidade ≥ 99.9%. |
| **Redis** | 7-alpine | StatefulSet `redis` no namespace `demo-app-mba`, service `redis-svc:6379` | 99.9% | **Alto** — Cache misses em todas as leituras, latência aumenta significativamente. Pode violar SLO p99 < 500ms sob carga. O app deve funcionar em modo degradado (fallback direto ao PostgreSQL). |
| **OTel Collector** | latest | Pod no cluster, service `otel-collector:4317` | best-effort | **Baixo** — Métricas e traces param de ser exportados, mas a aplicação funciona normalmente. Slack no Grafana, perda de visibilidade. |
| **LM Studio** | local | Host local, modelo Qwen ou Gemma | best-effort | **Baixo** — Funcionalidade de agentes LLM fica indisponível, mas CRUD e health check funcionam normalmente. |

### Estratégias de Resiliência

| Dependência | Estratégia | Detalhe |
|---|---|---|
| PostgreSQL | Connection pooling + retry | SQLAlchemy Async com pool size=10, max_overflow=20, pool_recycle=1800, retry com backoff 3x |
| Redis | Fallback graceful | Se Redis indisponível, bypass de cache e leitura direta do PostgreSQL. Timeout de conexão: 2s. |
| OTel Collector | Non-blocking export | Export OTLP assíncrono. Falha no collector não bloqueia requests. |
| LM Studio | Timeout + circuit breaker | Timeout de 30s por request LLM. Circuit breaker abre após 5 falhas consecutivas. |

---

## 4. SLOs com Targets

| SLO | SLI | Target | Error Budget | Janela |
|---|---|---|---|---|
| Disponibilidade | `1 - (5xx_requests / total_requests)` | ≥ 99.9% | 43.2 min/mês (0.1% × 43200 min) | 30 dias |
| Latência p99 | `histogram_quantile(0.99, request_duration)` | < 500ms | — | 5 min |
| Latência p95 | `histogram_quantile(0.95, request_duration)` | < 200ms | — | 5 min |
| Error rate | `5xx_requests / total_requests` | < 0.1% | 43.2 min/mês | 5 min |

### Derivação do Error Budget

```
Disponibilidade target = 99.9%
Downtime aceitável = (1 - 0.999) × 43200 min/mês = 43.2 min/mês

Error rate target = 0.1% (equivalente a 99.9% disponibilidade)
Error budget mensal = 43.2 min/mês

Burn rate fast (14.4x):
  - Consome error budget 14.4x mais rápido que o normal
  - Detecta 2% do error budget consumido em 5 min
  - Alerta imediato (P1)

Burn rate slow (6x):
  - Consome error budget 6x mais rápido que o normal
  - Detecta 1% do error budget consumido em 30 min
  - Alerta warning (P2)
```

### Burn Rate Thresholds

| Tipo | Burn Rate | Janela | Budget Consumido | Ação |
|---|---|---|---|---|
| Fast burn | 14.4x | 5 min | ~1.2% do budget mensal | Alerta P1 — escalar imediatamente |
| Slow burn | 6x | 30 min | ~3% do budget mensal | Alerta P2 — escalar em 15min |

---

## 5. Alertas Configurados

| # | Nome | Condição | Severidade | SLO Relacionado | Runbook Ação |
|---|---|---|---|---|---|
| 1 | AppApiErrorRateWarning | `error_rate > 0.05%` por 5min | WARNING | Disponibilidade ≥ 99.9% | Investigar, monitorar por 30min |
| 2 | AppApiErrorRateCritical | `error_rate > 0.1%` por 5min | CRITICAL | Disponibilidade ≥ 99.9% | Rollback ou mitigação imediata |
| 3 | AppApiLatencyP99Warning | `p99 > 400ms` por 10min | WARNING | p99 < 500ms | Scale up, investigar DB/cache |
| 4 | AppApiLatencyP99Critical | `p99 > 500ms` por 5min | CRITICAL | p99 < 500ms | Scale up ou rollback imediato |
| 5 | AppApiPodRestarts | `pod_restart_count > 2` em 10min | WARNING | Disponibilidade ≥ 99.9% | Verificar logs, OOMKilled, CrashLoop |
| 6 | AppApiHPAMaxReplicas | `hpa_replicas == hpa_max_replicas` | WARNING | Latência p99 < 500ms | Investigar carga, aumentar maxReplicas ou otimizar |

### Regras PromQL

```promql
# Alerta 1: Error rate WARNING (> 0.05% por 5min)
(
  1 - (
    sum(rate(http_server_request_duration_seconds_count{job="app-api",code!~"5.."}[5m]))
    /
    sum(rate(http_server_request_duration_seconds_count{job="app-api"}[5m]))
  )
) > 0.0005

# Alerta 2: Error rate CRITICAL (> 0.1% por 5min — fast burn 14.4x)
(
  1 - (
    sum(rate(http_server_request_duration_seconds_count{job="app-api",code!~"5.."}[5m]))
    /
    sum(rate(http_server_request_duration_seconds_count{job="app-api"}[5m]))
  )
) > 0.001 * 14.4 / 14.4

# Alerta 3: Latência p99 WARNING (> 400ms por 10min)
histogram_quantile(0.99, sum(rate(http_server_request_duration_seconds_bucket{job="app-api"}[10m])) by (le)) > 0.4

# Alerta 4: Latência p99 CRITICAL (> 500ms por 5min — SLO violado)
histogram_quantile(0.99, sum(rate(http_server_request_duration_seconds_bucket{job="app-api"}[5m])) by (le)) > 0.5

# Alerta 5: Pod restarts > 2 em 10min
sum(increase(kube_pod_container_status_restarts_total{pod=~"app-api-deployment-.*"}[10m])) > 2

# Alerta 6: HPA at max replicas
kube_hpa_status_current_replicas{hpa="app-api-hpa"} == kube_hpa_spec_max_replicas{hpa="app-api-hpa"}
```

---

## 6. Procedimentos de Deploy e Rollback

### Pipeline de Deploy

```
git push origin main
       │
       ▼
GitHub Actions
       │
       ├── Checkout código
       ├── Lint + Type check (ruff, mypy)
       ├── Testes unitários + integração
       │
       ▼
Build Docker (Dockerfile multistage)
       │
       ├── Stage builder: python:3.11-slim + pip install
       ├── Stage runtime: python:3.11-slim + virtualenv + app/
       │
       ▼
Push imagem → registry (app-api:latest + app-api:sha-{commit})
       │
       ▼
Deploy Kubernetes
       │
       ├── kubectl apply -f k8s/namespace.yaml
       ├── kubectl apply -f k8s/configmap.yaml
       ├── kubectl apply -f k8s/secret.yaml
       ├── kubectl apply -f k8s/postgresql-statefulset.yaml
       ├── kubectl apply -f k8s/redis-statefulset.yaml
       ├── Aguardar PostgreSQL e Redis ready
       ├── kubectl apply -f k8s/deployment.yaml
       ├── kubectl apply -f k8s/service.yaml
       ├── kubectl apply -f k8s/hpa.yaml
       ├── kubectl apply -f k8s/networkpolicy.yaml
       │
       ▼
Verify Health
       │
       ├── kubectl rollout status deployment/app-api-deployment -n demo-app-mba
       ├── curl http://app-api-service:8000/health → 200 OK
       ├── Verificar error rate < 0.1% nos próximos 5min
       └── Verificar p99 < 500ms nos próximos 5min
```

### Procedimento de Rollback

```
ROLLBACK ÁRDUO — CRITÉRIOS:

  p99 > 500ms por 5min OU error rate > 0.1% por 5min
  ──► ROLLBACK AUTOMÁTICO

  p99 > 400ms por 10min OU error rate > 0.05% por 5min
  ──► ROLLBACK MANUAL (decisão do on-call)
```

#### Rollback Manual — Passo a Passo

```bash
# 1. Verificar revisão atual
kubectl rollout history deployment/app-api-deployment -n demo-app-mba

# 2. Rollback para revisão anterior
kubectl rollout undo deployment/app-api-deployment -n demo-app-mba

# 3. Verificar status do rollback
kubectl rollout status deployment/app-api-deployment -n demo-app-mba

# 4. Verificar pods
kubectl get pods -l app=app-api -n demo-app-mba -o wide

# 5. Verificar health check
curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health
# Esperado: 200

# 6. Verificar SLOs nos próximos 5-10min
#      - Error rate < 0.1%
#      - p99 < 500ms
#      - p95 < 200ms
```

#### Verificação Pós-Rollback

| Verificação | Comando/Observável | Critério de Sucesso |
|---|---|---|
| Pods healthy | `kubectl get pods -l app=app-api -n demo-app-mba` | Todos Running 1/1 |
| Health check | `curl /health` | HTTP 200 |
| Error rate | Grafana ou PromQL | < 0.1% por 10min |
| Latência p99 | Grafana ou PromQL | < 500ms por 10min |
| HPA estável | `kubectl get hpa app-api-hpa -n demo-app-mba` | Replicas estáveis, não no máximo |

---

## 7. Lições Aprendidas

> Seção placeholder — preencher após cada incidente real.

| Data | Incidente | Lição Aprendida | Action Item | Status |
|---|---|---|---|---|
| _YYYY-MM-DD_ | _Descrição do incidente_ | _O que aprendemos_ | _O que faremos para prevenir recorrência_ | _A fazer / Em progresso / Concluído_ |
| | | | | |
| | | | | |