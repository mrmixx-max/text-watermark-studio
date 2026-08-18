# Monitoring & Observability

Text Watermark Studio v2.4.1 — Prometheus metrics, health/readiness endpoints,
and alerting rules for production deployments.

## Quick Start (Dev)

```bash
# Start the full stack including Prometheus + Grafana
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d

# Prometheus:  http://localhost:9090
# Grafana:     http://localhost:3000  (admin/admin)
# Metrics:     http://localhost:8080/metrics
```

## Endpoints

| Endpoint       | Auth | Purpose                                      |
|----------------|------|----------------------------------------------|
| `GET /metrics` | none | Prometheus scrape target (root-level)        |
| `GET /health`  | none | Liveness + Redis health (503 if Redis down)  |
| `GET /ready`   | none | K8s readiness probe (503 if Redis unreachable) |

## Metrics

### HTTP (`PrometheusMiddleware`)

- **`tws_http_requests_total`** — Counter, labels: `method`, `route`, `status`
- **`tws_http_request_duration_seconds`** — Histogram, labels: `method`, `route`

### Business Logic

- **`tws_watermark_operations_total`** — Counter, labels: `operation` (detect, embed, clean, dilute, pipeline, text_detect), `status` (success, error)
- **`tws_detection_score`** — Histogram of detection |Z| scores
- **`tws_detection_verdict_total`** — Counter, labels: `verdict` (redlist_detected, weak_redlist_signal, watermark_detected, ...)

### Stream / Queue

- **`tws_stream_pending_jobs`** — Gauge: pending jobs in Redis stream
- **`tws_stream_dead_letter_jobs`** — Gauge: jobs in the dead-letter queue
- **`tws_dlq_replays_total`** — Counter: DLQ replay operations

## Alerting Rules

Defined in `monitoring/prometheus/alerting-rules.yml`:

| Alert                  | Severity | Condition                                    |
|------------------------|----------|----------------------------------------------|
| TWSHighErrorRate       | warning  | > 5% 5xx over 5 min                          |
| TWSCriticalErrorRate   | critical | > 20% 5xx over 3 min                         |
| TWSWatermarkOperationErrors | warning | > 10% watermark op errors over 5 min    |
| TWSHighLatency         | warning  | p95 latency > 2s over 5 min                  |
| TWSRedisDown           | critical | /health returns 503 (Redis unreachable)      |
| TWSStreamBacklog       | warning  | > 100 pending stream jobs for 10 min         |
| TWSDLQGrowing          | warning  | > 0 DLQ jobs for 5 min                       |

## Grafana Dashboard

The dashboard (`monitoring/grafana/dashboards/tws-dashboard.json`) is provisioned
automatically and includes:

- 5xx error rate stat panel
- P95 latency stat panel
- Stream pending jobs stat panel
- DLQ jobs stat panel
- Watermark operations rate time series
- Detection verdicts time series
- Detection score heatmap
- HTTP requests by route time series
- Request duration percentiles (p50/p95/p99)

## Kubernetes Probes

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 15

readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
```
