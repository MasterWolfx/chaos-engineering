# 10 - Osservabilità con Prometheus e Grafana

## 10.1 Il Problema dell'Osservabilità

> *"You can't improve what you can't measure."* - Peter Drucker

Nel Chaos Engineering, l'osservabilità non è opzionale - è il prerequisito. Senza metriche, non si può:
- Definire il **steady state**
- Capire l'**impatto** di un esperimento
- Verificare il **recovery** dopo il chaos

### I 3 Pilastri dell'Osservabilità

```
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│    METRICS    │  │     LOGS      │  │    TRACES     │
│               │  │               │  │               │
│ Cosa sta      │  │ Cosa è        │  │ Come fluisce  │
│ succedendo    │  │ successo      │  │ una richiesta │
│ adesso        │  │ in passato    │  │ tra servizi   │
│               │  │               │  │               │
│ Prometheus    │  │ Loki/ELK      │  │ Jaeger/Zipkin │
│ + Grafana     │  │               │  │               │
└───────────────┘  └───────────────┘  └───────────────┘
       ↑
  Nel progetto
  usiamo questo
```

---

## 10.2 Prometheus

**Prometheus** è un sistema open source di monitoraggio e alerting, progettato per ambienti cloud-native. Usa un modello **pull**: va lui a raccogliere le metriche dai target ogni N secondi.

### Architettura

```
┌─────────────────────────────────────────────────────────┐
│                     Prometheus                          │
│                                                         │
│  ┌─────────────┐   HTTP GET /metrics    ┌────────────┐  │
│  │  Scrape     │ ─────────────────────→ │  Backend   │  │
│  │  Engine     │ ←───────────────────── │  :3000     │  │
│  └──────┬──────┘   risposta: text/plain └────────────┘  │
│         │                                               │
│  ┌──────▼──────┐                        ┌────────────┐  │
│  │  TSDB       │                        │  K8s nodes │  │
│  │  (Time      │ ←───────────────────── │  kubelet   │  │
│  │  Series DB) │                        └────────────┘  │
│  └──────┬──────┘                                        │
│         │ PromQL query                                  │
│  ┌──────▼──────┐                                        │
│  │  HTTP API   │ ←─────── Grafana, AlertManager        │
│  └─────────────┘                                        │
└─────────────────────────────────────────────────────────┘
```

### Il Formato delle Metriche

Ogni metrica è una serie temporale con un nome e un set di label:

```
# TYPE http_requests_total counter
http_requests_total{method="GET",handler="/api/items",status="200"} 1234
http_requests_total{method="POST",handler="/api/items",status="201"} 56
http_requests_total{method="GET",handler="/api/items",status="500"} 3

# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{handler="/api/items",le="0.005"} 10
http_request_duration_seconds_bucket{handler="/api/items",le="0.01"} 45
http_request_duration_seconds_bucket{handler="/api/items",le="0.1"} 890
http_request_duration_seconds_bucket{handler="/api/items",le="+Inf"} 1234
```

### Tipi di Metriche

| Tipo | Descrizione | Esempio |
|---|---|---|
| **Counter** | Sempre crescente, conta eventi | `http_requests_total` |
| **Gauge** | Può salire e scendere | `memory_usage_bytes` |
| **Histogram** | Distribuzione dei valori in bucket | `http_request_duration_seconds` |
| **Summary** | Quantili pre-calcolati | `go_gc_duration_seconds` |

### ServiceMonitor - Come Prometheus trova il Backend

Invece di configurare Prometheus manualmente, nel progetto usiamo il CRD `ServiceMonitor` di Prometheus Operator:

```yaml
# helm/backend/templates/servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: backend
  namespace: app
  labels:
    release: prometheus    # ← Prometheus Operator cerca questa label
spec:
  selector:
    matchLabels:
      app: backend          # ← Service con questa label
  endpoints:
  - port: http
    path: /metrics          # ← endpoint esposto da FastAPI
    interval: 15s           # ← ogni 15 secondi
```

```bash
# Verifica che Prometheus stia raccogliendo i dati
kubectl port-forward svc/prometheus-kube-prometheus-prometheus -n monitoring 9090:9090
# Apri http://localhost:9090/targets
# Deve apparire: app/backend/0 → UP
```

---

## 10.3 PromQL - Il Linguaggio di Query

**PromQL** (Prometheus Query Language) è il linguaggio per interrogare le metriche.

### Sintassi Base

```promql
# Seleziona una metrica
http_requests_total

# Filtra per label
http_requests_total{status="200"}
http_requests_total{status=~"5.."}     # regex: tutti i 5xx

# Rate (variazione per secondo negli ultimi N minuti)
rate(http_requests_total[1m])          # RPS

# Somma per label
sum(rate(http_requests_total[1m])) by (handler)

# Percentile da histogram
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[1m])) by (le)
)
```

### Le Query della Dashboard del Progetto

```promql
# Request Rate totale
sum(rate(http_requests_total{namespace="app",pod=~"backend.*"}[1m]))

# Error Rate (5xx)
sum(rate(http_requests_total{
  namespace="app",
  pod=~"backend.*",
  status=~"5.."
}[1m]))
/
sum(rate(http_requests_total{namespace="app",pod=~"backend.*"}[1m]))

# Latenza p95
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket{
    namespace="app",pod=~"backend.*"
  }[1m])) by (le)
) * 1000   # in millisecondi

# Pod attivi
count(kube_pod_status_ready{
  namespace="app",
  pod=~"backend.*",
  condition="true"
})

# CPU per pod
sum(rate(container_cpu_usage_seconds_total{
  namespace="app",
  container!="",
  container!="POD"
}[1m])) by (pod)

# RPS per endpoint
sum(rate(http_requests_total{
  namespace="app",pod=~"backend.*"
}[1m])) by (handler, method)
```

---

## 10.4 Grafana

**Grafana** è la piattaforma di visualizzazione. Si connette a Prometheus come datasource e permette di creare dashboard interattive.

### Installazione (kube-prometheus-stack)

```bash
helm install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set grafana.adminPassword=admin \
  --set grafana.service.type=ClusterIP

# Accesso
kubectl port-forward svc/prometheus-grafana -n monitoring 3000:80
# http://localhost:3000  (admin/admin)
```

### La Dashboard del Progetto

La dashboard `monitoring/grafana-dashboards/app-resilience.json` include:

```
┌──────────────────────────────────────────────────────────────┐
│              App Resilience - Chaos Engineering              │
├─────────────┬─────────────┬─────────────┬────────────────────┤
│  RPS        │  Error Rate │  Latenza p95│  Pod Attivi        │
│  (stat)     │  (stat)     │  (stat)     │  (stat)            │
├─────────────┴─────────────┴─────────────┴────────────────────┤
│  Latenza HTTP - p50 / p95 / p99         │  Pod Attivi per    │
│  (timeseries)                           │  Deployment        │
│                                         │  (timeseries)      │
├─────────────────────────────────────────┴────────────────────┤
│  CPU Usage per Pod                      │  Memory per Pod    │
│  (timeseries)                           │  (timeseries)      │
├─────────────────────────────────────────┴────────────────────┤
│  RPS per Endpoint (Backend)                                  │
│  (timeseries - una linea per ogni endpoint)                  │
├──────────────────────────────────────────────────────────────┤
│  Richieste HTTP per Endpoint e Status Code                   │
│  (tabella con barre progress - ordinata per volume)          │
└──────────────────────────────────────────────────────────────┘
```

### Importare la Dashboard

```bash
# Via API (curl)
curl -X POST http://admin:admin@localhost:3000/api/dashboards/import \
  -H "Content-Type: application/json" \
  -d "{\"dashboard\": $(cat monitoring/grafana-dashboards/app-resilience.json), \"overwrite\": true}"

# Oppure via UI:
# Grafana → Dashboards → Import → Upload JSON file
```

---

## 10.5 Metriche Esposte dal Backend

`prometheus-fastapi-instrumentator` espone automaticamente:

```bash
curl http://app.localhost/metrics
```

```
# HELP http_requests_total Total number of requests
# TYPE http_requests_total counter
http_requests_total{handler="/api/items",method="GET",status="200"} 42
http_requests_total{handler="/api/items",method="POST",status="201"} 5
http_requests_total{handler="/api/health",method="GET",status="200"} 156

# HELP http_request_duration_seconds Duration of HTTP requests
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{handler="/api/items",le="0.005"} 0
http_request_duration_seconds_bucket{handler="/api/items",le="0.01"} 2
http_request_duration_seconds_bucket{handler="/api/items",le="0.025"} 18
http_request_duration_seconds_bucket{handler="/api/items",le="0.05"} 38
http_request_duration_seconds_bucket{handler="/api/items",le="0.1"} 42
http_request_duration_seconds_bucket{handler="/api/items",le="+Inf"} 42
http_request_duration_seconds_sum{handler="/api/items"} 1.234
http_request_duration_seconds_count{handler="/api/items"} 42
```

---

## 10.6 Leggere i Grafici Durante il Chaos

### Scenario: Pod Failure (Esperimento 1)

```
Latenza p95 (ms)
│
│     Spike!
│     ╭──╮
│  ───╯  ╰───────────────── ritorno a normale
│
└────────────────────────────────────────→ Tempo
     │                │
   Pod kill       Pod ready

Pod Attivi
│ 3   ─────────╮        ╭───── 3
│ 2            ╰────────╯
│
└────────────────────────────────────────→ Tempo
```

**Cosa leggere:**
- Il pod count scende da 3 a 2 → K8s lo rileva
- C'è uno spike di latenza durante il failure
- Il pod count torna a 3 entro ~30 secondi
- La latenza si normalizza → **steady state mantenuto**

### Scenario: CPU Stress (Esperimento 4)

```
CPU Usage
│         ████████████████████
│         ████████████████████ ← 80% su tutti i pod
│         ████████████████████
│ ────────╯                  ╰─ fine stress
└────────────────────────────────────────→ Tempo

Repliche HPA
│ 6  ────────────────────────────────╮
│ 5                              ╭───╯
│ 4                         ╭────╯
│ 3 ───────────────────╮────╯
│ 2                                   ╰──── scale down
└────────────────────────────────────────→ Tempo
     │                    │
  Stress start         Stress end
```

---

## 10.7 Prometheus + Grafana in Produzione

Nel progetto usiamo la configurazione di sviluppo. In produzione si aggiungono:

```yaml
# AlertManager: notifica quando qualcosa va storto
alerting_rules:
- name: high-error-rate
  expr: error_rate > 0.05   # > 5% errori
  for: 2m
  annotations:
    summary: "Error rate alta su backend"
    
- name: pod-down
  expr: kube_pod_status_ready == 0
  for: 1m
  annotations:
    summary: "Pod non pronto: {{ $labels.pod }}"
```

---

## Riepilogo

```
Prometheus:
  • Raccoglie metriche in pull ogni 15s
  • TSDB interno per storico temporale
  • PromQL per query avanzate
  • ServiceMonitor per auto-discovery K8s

Grafana:
  • Visualizza le metriche di Prometheus
  • Dashboard con pannelli configurabili
  • Alert visivi durante il chaos

prometheus-fastapi-instrumentator:
  • Espone /metrics sul backend automaticamente
  • Counter: numero richieste per endpoint/status
  • Histogram: distribuzione latenze
```

**Prossima lezione →** [11 - I 5 Esperimenti di Chaos](11-esperimenti-chaos.md)
