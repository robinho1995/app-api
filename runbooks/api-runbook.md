# Runbook Operacional — app-api

| Campo | Valor |
|---|---|
| **Serviço** | app-api |
| **Tipo** | API REST — FastAPI / Python 3.11 / Uvicorn |
| **Namespace** | demo-app-mba |
| **Deployment** | app-api-deployment |
| **Owners** | Time SRE |
| **Última atualização** | 2026-05-25 |
| **Versão do runbook** | 1.0.0 |

---

## 1. Referência Rápida

| Recurso | Comando |
|---|---|
| Pods | `kubectl get pods -l app=app-api -n demo-app-mba -o wide` |
| Logs | `kubectl logs -l app=app-api -n demo-app-mba --tail=100` |
| Events | `kubectl get events -n demo-app-mba --sort-by='.lastTimestamp'` |
| Deploy | `kubectl describe deployment app-api-deployment -n demo-app-mba` |
| HPA | `kubectl get hpa app-api-hpa -n demo-app-mba` |
| PostgreSQL | `kubectl exec -n demo-app-mba statefulset/postgresql -- pg_isready -U mbauser -d mbaapi` |
| Redis | `kubectl exec -n demo-app-mba statefulset/redis -- redis-cli ping` |
| Health check | `curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health` |

---

## 2. SLOs e Thresholds de Alerta

| SLO | Target | Warning | Critical | Error Budget (mês) |
|---|---|---|---|---|
| Disponibilidade | ≥ 99.9% | < 99.95% | < 99.9% | 43.2 min |
| Latência p99 | < 500ms | > 400ms | > 500ms | — |
| Latência p95 | < 200ms | > 150ms | > 200ms | — |
| Error rate | < 0.1% | > 0.05% | > 0.1% | — |

### Burn Rate

| Tipo | Burn Rate | Janela | Condição |
|---|---|---|---|
| Fast burn | 14.4x | 5 min | 2% do error budget em 5min → alerta imediato |
| Slow burn | 6x | 30 min | 1% do error budget em 30min → alerta warning |

---

## 3. Sintomas e Diagnóstico

---

### Sintoma 1: Latência Alta — p99 acima de 500ms

**SLO violado:** p99 < 500ms

#### Comandos de diagnóstico

```bash
# Status dos pods
kubectl get pods -l app=app-api -n demo-app-mba -o wide

# Logs de erro e latência
kubectl logs -l app=app-api -n demo-app-mba --tail=200 | grep -E 'elapsed|duration|slow|timeout'

# Events recentes
kubectl get events -n demo-app-mba --sort-by='.lastTimestamp' | tail -20

# Verificar uso de recursos (CPU/memory)
kubectl top pods -l app=app-api -n demo-app-mba

# HPA status
kubectl get hpa app-api-hpa -n demo-app-mba
```

#### Queries PromQL

```promql
# Latência p99 dos últimos 15min
histogram_quantile(0.99, sum(rate(http_server_request_duration_seconds_bucket{job="app-api"}[15m])) by (le))

# Latência p95 dos últimos 15min
histogram_quantile(0.95, sum(rate(http_server_request_duration_seconds_bucket{job="app-api"}[15m])) by (le))

# Latência por endpoint
histogram_quantile(0.99, sum(rate(http_server_request_duration_seconds_bucket{job="app-api"}[15m])) by (le, path))

# CPU dos pods
sum(rate(container_cpu_usage_seconds_total{pod=~"app-api-deployment-.*"}[5m])) by (pod)
```

#### Teste direto

```bash
# Port-forward
kubectl port-forward svc/app-api-service -n demo-app-mba 8000:8000 &

# Latência do endpoint /api/v1/items
curl -o /dev/null -s -w "status: %{http_code}\ntime_total: %{time_total}s\n" http://localhost:8000/api/v1/items

# Latência do health check
curl -o /dev/null -s -w "status: %{http_code}\ntime_total: %{time_total}s\n" http://localhost:8000/health
```

#### Possíveis causas

| Causa | Indicador | Ação |
|---|---|---|
| PostgreSQL lento | p99 do DB > 300ms, queries lentas | Verificar carga no PostgreSQL (Sintoma DB) |
| Redis misses | Cache hit rate < 80% | Investigar padrões de acesso |
| CPU saturada | Pods com CPU > 70% do limit | Scale up (Seção 4) |
| Poucos pods | HPA no máximo ou CPU throttling | Scale up (Seção 4) |

---

### Sintoma 2: Erros 5xx — Error rate acima de 0.1%

**SLO violado:** Disponibilidade ≥ 99.9% (error rate < 0.1%)

#### Comandos de diagnóstico

```bash
# Status dos pods
kubectl get pods -l app=app-api -n demo-app-mba -o wide

# Logs de erro
kubectl logs -l app=app-api -n demo-app-mba --tail=200 | grep -E 'ERROR|5[0-9]{2}|Exception|Traceback'

# Logs dos pods em CrashLoop
kubectl get pods -n demo-app-mba | grep -E 'Error|CrashLoop'

# Describe pods com problemas
kubectl describe pod -l app=app-api -n demo-app-mba | grep -A5 -E 'Events|Last State|State'

# Verificar conectividade com PostgreSQL
kubectl exec -n demo-app-mba statefulset/postgresql -- pg_isready -U mbauser -d mbaapi

# Verificar conectividade com Redis
kubectl exec -n demo-app-mba statefulset/redis -- redis-cli ping
```

#### Queries PromQL

```promql
# Error rate dos últimos 5min
sum(rate(http_server_request_duration_seconds_count{job="app-api",code=~"5.."}[5m]))
/
sum(rate(http_server_request_duration_seconds_count{job="app-api"}[5m]))

# Error rate por status code
sum(rate(http_server_request_duration_seconds_count{job="app-api",code=~"5.."}[5m])) by (code)

# Error rate por endpoint
sum(rate(http_server_request_duration_seconds_count{job="app-api",code=~"5.."}[5m])) by (path)

# Fast burn: error budget consumido em 5min
(
  1 - (
    sum(rate(http_server_request_duration_seconds_count{job="app-api",code!~"5.."}[5m]))
    /
    sum(rate(http_server_request_duration_seconds_count{job="app-api"}[5m]))
  )
) > 0.001 * 14.4
```

#### Teste direto

```bash
# Port-forward
kubectl port-forward svc/app-api-service -n demo-app-mba 8000:8000 &

# Testar endpoint principal
curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/v1/items

# Testar com payload
curl -s -X POST http://localhost:8000/api/v1/items \
  -H 'Content-Type: application/json' \
  -d '{"name": "test-item"}' \
  -w '\nHTTP %{http_code}\n'

# Testar health check
curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health
```

#### Possíveis causas

| Causa | Indicador | Ação |
|---|---|---|
| PostgreSQL indisponível | pg_isready falha, erros de conexão | Verificar StatefulSet PostgreSQL |
| Redis indisponível | redis-cli ping falha | Verificar StatefulSet Redis |
| Deployment quebrado | Pods em CrashLoopBackOff | Rolling restart ou rollback (Seção 4) |
| ConfigMap/Secret faltando | Erros de variável de ambiente | Verificar configmap e secret |

---

### Sintoma 3: Pod Reiniciando — CrashLoopBackOff ou OOMKilled

**Impacto no SLO:** Reiniciamentos reduzem disponibilidade e podem violar o SLO de 99.9%

#### Comandos de diagnóstico

```bash
# Listar pods com problemas
kubectl get pods -l app=app-api -n demo-app-mba | grep -v Running

# Verificar restarts
kubectl get pods -l app=app-api -n demo-app-mba -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.containerStatuses[0].restartCount}{"\n"}{end}'

# Verificar se é OOMKilled
kubectl describe pod -l app=app-api -n demo-app-mba | grep -A3 "Last State"

# Logs do container antes do crash
kubectl logs -l app=app-api -n demo-app-mba --previous --tail=100

# Uso de memória atual
kubectl top pods -l app=app-api -n demo-app-mba

# Verificar limits do container
kubectl get deployment app-api-deployment -n demo-app-mba -o jsonpath='{.spec.template.spec.containers[0].resources}'
```

#### Queries PromQL

```promql
# Restart rate
sum(rate(kube_pod_container_status_restarts_total{pod=~"app-api-deployment-.*"}[15m]))

# Pods em OOMKilled
kube_pod_container_status_last_terminated_reason{pod=~"app-api-deployment-.*",reason="OOMKilled"}

# Uso de memória vs limit
sum(container_memory_working_set_bytes{pod=~"app-api-deployment-.*"}) by (pod)
/
sum(kube_pod_container_resource_limits{resource="memory",pod=~"app-api-deployment-.*"}) by (pod)
```

#### Possíveis causas

| Causa | Indicador | Ação |
|---|---|---|
| OOMKilled | Last State: OOMKilled, memória > 512Mi | Aumentar memory limit ou investigar leak |
| CrashLoopBackOff | Exit code != 0, erro no startup | Verificar logs com `--previous` |
| Probe falhando | Readiness/Liveness falhando | Verificar se /health responde, ajustar probes |
| ImagePullBackOff | Imagem não encontrada | Verificar se imagem existe no registry |

---

### Sintoma 4: Tráfego Anômalo — Drop > 50% ou Spike > 200% em 5min

**Impacto no SLO:** Drops afetam disponibilidade; spikes podem saturar capacidade e violar latência p99 < 500ms

#### Comandos de diagnóstico

```bash
# Verificar contagem de pods disponíveis
kubectl get deployment app-api-deployment -n demo-app-mba -o jsonpath='{.status.availableReplicas}'

# Verificar HPA
kubectl describe hpa app-api-hpa -n demo-app-mba

# Verificar NetworkPolicy
kubectl describe networkpolicy app-api-netpol -n demo-app-mba

# Verificar se serviço está respondendo
kubectl get endpoints app-api-service -n demo-app-mba
```

#### Queries PromQL

```promql
# Request rate atual vs 5min atrás
sum(rate(http_server_request_duration_seconds_count{job="app-api"}[5m]))

# Comparação com 1h atrás
sum(rate(http_server_request_duration_seconds_count{job="app-api"}[5m]))
/
sum(rate(http_server_request_duration_seconds_count{job="app-api"}[5m] offset 1h))

# Tráfego por endpoint
sum(rate(http_server_request_duration_seconds_count{job="app-api"}[5m])) by (path)

# Status codes distribuição
sum(rate(http_server_request_duration_seconds_count{job="app-api"}[5m])) by (code)
```

#### Teste direto

```bash
# Verificar se endpoints existem
kubectl get endpoints app-api-service -n demo-app-mba

# Port-forward e verificar resposta
kubectl port-forward svc/app-api-service -n demo-app-mba 8000:8000 &
curl -s http://localhost:8000/health | head -20
```

---

## 4. Ações de Mitigação

### 4.1 Rolling Restart

**Quando usar:**
- Pods em estado inconsistente
- Erros 5xx sem deploy recente
- Conexões com DB/Redis "presas"
- Não usar se houve deploy recente (< 5min)

```bash
# Executar rolling restart
kubectl rollout restart deployment/app-api-deployment -n demo-app-mba

# Verificar andamento
kubectl rollout status deployment/app-api-deployment -n demo-app-mba

# Verificar se novos pods estão healthy
kubectl get pods -l app=app-api -n demo-app-mba -o wide
```

**Como verificar se funcionou:**
```bash
# Todos os pods Running e Ready
kubectl get pods -l app=app-api -n demo-app-mba --no-headers | awk '{print $3}' | grep -c "1/1"

# Health check respondendo 200
curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health
# Esperado: 200

# Error rate normalizado (< 0.1%)
# Verificar no Prometheus: error rate dos últimos 5min
```

---

### 4.2 Scale Up

**Quando usar:**
- CPU > 70% do limit (SLO p99 < 500ms em risco)
- Latência p99 subindo consistentemente
- Tráfego anômalo — spike > 200%
- HPA não está escalando rápido o suficiente

```bash
# Escalar para 5 réplicas
kubectl scale deployment/app-api-deployment -n demo-app-mba --replicas=5

# Verificar se novos pods subiram
kubectl get pods -l app=app-api -n demo-app-mba -o wide

# Verificar se pods estão prontos
kubectl rollout status deployment/app-api-deployment -n demo-app-mba
```

**Como verificar se funcionou:**
```bash
# Pods disponíveis
kubectl get deployment app-api-deployment -n demo-app-mba -o jsonpath='{.status.availableReplicas}'

# Latência caiu abaixo do SLO
# PromQL: p99 < 500ms
curl -s -o /dev/null -w 'time_total: %{time_total}s\n' http://localhost:8000/health
```

**Nota:** Após a resolução, reverter para o HPA:
```bash
# Annotate para o HPA assumir o controle novamente
kubectl annotate hpa app-api-hpa -n demo-app-mba autoscaling.alpha.kubernetes.io/managed-by=true --overwrite
```

---

### 4.3 Rollback

**Quando usar:**
- Deploy recente causou erros 5xx (error rate > 0.1%, SLO violado)
- Pods em CrashLoopBackOff após deploy
- Rollout não está progredindo
- Burn rate fast (14.4x) detectado após deploy

```bash
# Verificar histórico de rollouts
kubectl rollout history deployment/app-api-deployment -n demo-app-mba

# Rollback para versão anterior
kubectl rollout undo deployment/app-api-deployment -n demo-app-mba

# Verificar status do rollback
kubectl rollout status deployment/app-api-deployment -n demo-app-mba

# Verificar pods
kubectl get pods -l app=app-api -n demo-app-mba -o wide
```

**Como verificar se funcionou:**
```bash
# Pods Running e Ready
kubectl get pods -l app=app-api -n demo-app-mba --no-headers | awk '{print $3}' | grep -c "1/1"

# Error rate normalizado
# PromQL: error rate < 0.1%

# Health check
curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health
# Esperado: 200

# Verificar revision atual
kubectl rollout history deployment/app-api-deployment -n demo-app-mba | tail -5
```

**Rollback para revisão específica:**
```bash
# Rollback para revisão N
kubectl rollout undo deployment/app-api-deployment -n demo-app-mba --to-revision=N
```

---

### 4.4 Diagnóstico de PostgreSQL

```bash
# Status do StatefulSet
kubectl get statefulset postgresql -n demo-app-mba

# Verificar se PostgreSQL está aceitando conexões
kubectl exec -n demo-app-mba statefulset/postgresql -- pg_isready -U mbauser -d mbaapi

# Verificar conexões ativas
kubectl exec -n demo-app-mba statefulset/postgresql -- psql -U mbauser -d mbaapi -c "SELECT count(*) FROM pg_stat_activity;"

# Verificar queries lentas ( > 500ms — viola SLO p99 )
kubectl exec -n demo-app-mba statefulset/postgresql -- psql -U mbauser -d mbaapi -c "SELECT query, state, now()-query_start AS duration FROM pg_stat_activity WHERE now()-query_start > interval '500 milliseconds' ORDER BY duration DESC;"

# Logs do PostgreSQL
kubectl logs statefulset/postgresql -n demo-app-mba --tail=50
```

### 4.5 Diagnóstico de Redis

```bash
# Status do StatefulSet
kubectl get statefulset redis -n demo-app-mba

# Verificar conectividade
kubectl exec -n demo-app-mba statefulset/redis -- redis-cli ping
# Esperado: PONG

# Verificar info do Redis
kubectl exec -n demo-app-mba statefulset/redis -- redis-cli info

# Verificar hit rate do cache (impacto na latência p95 < 200ms)
kubectl exec -n demo-app-mba statefulset/redis -- redis-cli info stats | grep -E 'keyspace_hits|keyspace_misses'

# Verificar memória usada
kubectl exec -n demo-app-mba statefulset/redis -- redis-cli info memory | grep used_memory_human

# Logs do Redis
kubectl logs statefulset/redis -n demo-app-mba --tail=50
```

---

## 5. Critérios de Escalonamento

| Severidade | Condição | Error Budget | Ação | SLA de Resposta |
|---|---|---|---|---|
| **P1 — Crítico** | SLO violado + error budget < 25% | < 25% (≤ 10.8 min restantes) | Escalar imediatamente para SRE Lead | 5 min |
| **P2 — Alto** | SLO violado + error budget 25–50% | 25–50% (10.8–21.6 min) | Escalar em 15 min para SRE On-Call | 15 min |
| **P3 — Médio** | Sintoma detectado, SLO não violado | > 50% | Monitorar e investigar | 1 hora |
| **P4 — Baixo** | Anomalia leve, sem impacto no SLO | > 75% | Registrar e acompanhhar | próximo dia útil |

### Escalonamento P1 — SLO violado com error budget crítico

**Gatilhos:**
- p99 > 500ms por mais de 5min consecutivos
- Error rate > 0.1% por mais de 5min (burn rate 14.4x)
- Pods em CrashLoopBackOff reduzindo capacidade abaixo de 2 réplicas healthy
- PostgreSQL ou Redis completamente indisponíveis

**Escalação:**
1. PagerDuty: `[SRE_ONCALL_PAGER]`
2. Email: `[SRE_LEAD_EMAIL]`
3. Slack: `#sre-alerts`

**Ações imediatas:**
1. Confirmar SLO violado via Prometheus/Grafana
2. Executar diagnóstico (Seção 3)
3. Executar mitigação (Seção 4) — preferir rollback se deploy recente
4. Comunicar em `#incident-status` com formato: `[P1] app-api — <sintoma> — SLO <nome> violado`

### Escalonamento P2 — SLO violado com error budget entre 25-50%

**Gatilhos:**
- p99 > 400ms consistentemente (warning threshold)
- Error rate 0.05–0.1%
- Restart count > 3 em 30min

**Escalação:**
1. Slack: `#sre-alerts`
2. Email: `[SRE_ONCALL_PAGER]`

**Ações:**
1. Investigar causa raiz
2. Scale up se necessário
3. Monitorar por 30min — se piorar, escalar para P1

### Escalonamento P3 — Monitorar

**Gatilhos:**
- Latência p95 > 150ms mas < 200ms (warning, SLO não violado)
- Restart esporádico (1–2 em 1h)
- Tráfego anômalo (-30% a -50% ou +100% a +200%)

**Ações:**
1. Investigar durante próximas 1h
2. Se evoluir para P2 ou P1, escalar
3. Documentar em ticket

---

## 6. Referência dos SLOs

| SLO | Target | Warning | Critical | Error Budget | Burn Rate Fast | Burn Rate Slow |
|---|---|---|---|---|---|---|
| Disponibilidade | ≥ 99.9% | < 99.95% | < 99.9% | 43.2 min/mês | 14.4x (5min) | 6x (30min) |
| Latência p99 | < 500ms | > 400ms | > 500ms | — | 14.4x (5min) | 6x (30min) |
| Latência p95 | < 200ms | > 150ms | > 200ms | — | 14.4x (5min) | 6x (30min) |
| Error rate | < 0.1% | > 0.05% | > 0.1% | 43.2 min/mês | 14.4x (5min) | 6x (30min) |

### Cálculo de Error Budget

- **Disponibilidade 99.9%** → 0.1% de downtime = 43.2 min/mês (43,200 seg/mês)
- **Burn rate 14.4x** → consome budget 14.4x mais rápido → alerta em ~5min
- **Burn rate 6x** → consome budget 6x mais rápido → alerta em ~30min

### Alertas Prometheus (referência)

```yaml
# Fast burn — P1 imediato
- alert: AppApiHighErrorRateFastBurn
  expr: |
    (
      1 - (
        sum(rate(http_server_request_duration_seconds_count{job="app-api",code!~"5.."}[5m]))
        /
        sum(rate(http_server_request_duration_seconds_count{job="app-api"}[5m]))
      )
    ) > 0.001 * 14.4
  for: 2m
  labels:
    severity: critical

# Slow burn — P2
- alert: AppApiHighErrorRateSlowBurn
  expr: |
    (
      1 - (
        sum(rate(http_server_request_duration_seconds_count{job="app-api",code!~"5.."}[30m]))
        /
        sum(rate(http_server_request_duration_seconds_count{job="app-api"}[30m]))
      )
    ) > 0.001 * 6
  for: 15m
  labels:
    severity: warning

# Latência p99 — Critical
- alert: AppApiHighLatencyP99
  expr: |
    histogram_quantile(0.99, sum(rate(http_server_request_duration_seconds_bucket{job="app-api"}[5m])) by (le))
    > 0.5
  for: 5m
  labels:
    severity: critical

# Latência p95 — Warning
- alert: AppApiLatencyP95Warning
  expr: |
    histogram_quantile(0.95, sum(rate(http_server_request_duration_seconds_bucket{job="app-api"}[10m])) by (le))
    > 0.2
  for: 10m
  labels:
    severity: warning
```

---

## 7. Checklist Pós-Incidente

- [ ] SLOs restaurados (p99 < 500ms, error rate < 0.1%)
- [ ] Error budget restante verificado
- [ ] Pods healthy: `kubectl get pods -l app=app-api -n demo-app-mba` — todos Running 1/1
- [ ] HPA funcionando: `kubectl get hpa app-api-hpa -n demo-app-mba`
- [ ] PostgreSQL conectivo: `kubectl exec -n demo-app-mba statefulset/postgresql -- pg_isready`
- [ ] Redis conectivo: `kubectl exec -n demo-app-mba statefulset/redis -- redis-cli ping`
- [ ] Health check: `curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health` retorna 200
- [ ] Incidente documentado em postmortem
- [ ] Runbook atualizado se necessário