# 09 - Componenti del Progetto

## 9.1 Struttura del Repository

```
chaos-kubernetes/
│
├── backend/                     ← Applicazione FastAPI
│   ├── app/
│   │   ├── main.py              ← Endpoint REST
│   │   ├── database.py          ← Connessione PostgreSQL
│   │   └── cache.py             ← Client Redis con fallback
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                    ← SPA Nginx
│   ├── html/
│   │   └── index.html           ← UI + JavaScript
│   ├── nginx.conf               ← Proxy config
│   └── Dockerfile
│
├── helm/                        ← Helm Charts custom
│   ├── backend/
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/
│   │       ├── deployment.yaml
│   │       ├── service.yaml
│   │       ├── hpa.yaml
│   │       └── servicemonitor.yaml
│   └── frontend/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│           ├── deployment.yaml
│           └── service.yaml
│
├── k8s/                         ← Manifesti Kubernetes
│   ├── namespaces.yaml          ← Namespace: app, monitoring, chaos-mesh
│   └── ingress.yaml             ← Traefik Ingress
│
├── chaos-experiments/           ← Esperimenti Chaos Mesh
│   ├── 01-pod-failure.yaml
│   ├── 02-network-delay.yaml
│   ├── 03-network-partition.yaml
│   ├── 04-cpu-stress.yaml
│   └── 05-pod-failure-cascading.yaml
│
├── monitoring/                  ← Osservabilità
│   └── grafana-dashboards/
│       └── app-resilience.json  ← Dashboard Grafana custom
│
└── docs/                        ← Questa documentazione
    ├── 00-indice.md
    ├── 01-kubernetes-fondamenti.md
    └── ...
```

---

## 9.2 Stack Tecnologico Completo

```
┌─────────────────────────────────────────────────────────────────┐
│                    STACK DEL PROGETTO                           │
│                                                                 │
│  INFRASTRUTTURA                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Hyper-V VM (Windows 11)                                │    │
│  │  └── Ubuntu 22.04 LTS                                   │    │
│  │      └── K3s v1.28 (Kubernetes leggero)                 │    │
│  │          ├── containerd (runtime)                       │    │
│  │          ├── Flannel (CNI)                              │    │
│  │          ├── Traefik (Ingress)                          │    │
│  │          └── CoreDNS (DNS)                              │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  PACKAGE MANAGEMENT                                             │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Helm 3                                                 │    │
│  │  ├── Chart custom: backend, frontend                    │    │
│  │  └── Chart Bitnami: postgresql, redis                   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  APPLICAZIONE (namespace: app)                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Frontend  → Nginx 1.25 + HTML/CSS/JS                   │    │
│  │  Backend   → Python 3.12 + FastAPI + asyncpg            │    │
│  │  Database  → PostgreSQL 16 (Bitnami)                    │    │
│  │  Cache     → Redis 7 (Bitnami)                          │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  CHAOS ENGINEERING (namespace: chaos-mesh)                      │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Chaos Mesh 2.x                                         │    │
│  │  ├── chaos-controller-manager                           │    │
│  │  ├── chaos-daemon (DaemonSet)                           │    │
│  │  └── chaos-dashboard                                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  OSSERVABILITÀ (namespace: monitoring)                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  kube-prometheus-stack                                  │    │
│  │  ├── Prometheus (scraping metriche)                     │    │
│  │  ├── Grafana (dashboard)                                │    │
│  │  ├── AlertManager (alerting)                            │    │
│  │  └── kube-state-metrics (metriche K8s)                  │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 9.3 Comunicazione tra i Componenti

```
Host Windows
    │ HTTP :80
    ▼
Traefik Ingress (K3s built-in)
    │
    ├─── / ──────────────────── Service: frontend :80
    │                                    │
    │                           [Pod frontend-1]
    │                           [Pod frontend-2]
    │                                    │ /api/ proxy_pass
    │                                    │
    └─── /api/ ──────────────── Service: backend :3000
                                         │
                               [Pod backend-1] ─┐
                               [Pod backend-2] ─┤─── Service: postgresql :5432
                               [Pod backend-3] ─┘         │
                                         │         [Pod postgresql-0]
                                         │
                                         └────── Service: redis-master :6379
                                                          │
                                                 [Pod redis-master-0]
```

### Tabella delle Porte

| Componente | Porta interna | Tipo Service | Accessibile da |
|---|---|---|---|
| Frontend | 80 | ClusterIP | Traefik → browser |
| Backend | 3000 | ClusterIP | Frontend, Traefik |
| PostgreSQL | 5432 | ClusterIP | Backend |
| Redis | 6379 | ClusterIP | Backend |
| Grafana | 3000 | ClusterIP | Port-forward |
| Prometheus | 9090 | ClusterIP | Port-forward |
| Chaos Dashboard | 2333 | ClusterIP | Port-forward |

---

## 9.4 Il Namespace `app` in Dettaglio

```bash
kubectl get all -n app
```

```
NAME                            READY   STATUS    RESTARTS
pod/postgresql-0                1/1     Running   0
pod/redis-master-0              1/1     Running   0
pod/backend-7d9f8b-abc          1/1     Running   0
pod/backend-7d9f8b-def          1/1     Running   0
pod/backend-7d9f8b-ghi          1/1     Running   0
pod/frontend-5c9f7d-xyz         1/1     Running   0
pod/frontend-5c9f7d-uvw         1/1     Running   0

NAME                  TYPE        CLUSTER-IP      PORT(S)
service/postgresql    ClusterIP   10.43.100.60    5432/TCP
service/redis-master  ClusterIP   10.43.100.70    6379/TCP
service/backend       ClusterIP   10.43.100.50    3000/TCP
service/frontend      ClusterIP   10.43.100.51    80/TCP

NAME                       READY   UP-TO-DATE   AVAILABLE
deployment.apps/backend    3/3     3            3
deployment.apps/frontend   2/2     2            2

NAME                                  DESIRED   CURRENT   READY
replicaset.apps/backend-7d9f8b        3         3         3
replicaset.apps/frontend-5c9f7d       2         2         2

NAME                                           REFERENCE             TARGETS   REPLICAS
horizontalpodautoscaler.apps/backend-hpa       Deployment/backend    15%/70%   3
```

---

## 9.5 Label e Selettori

Le **label** sono la base del routing in Kubernetes. Ogni componente usa label coerenti:

```yaml
# Backend pods
labels:
  app: backend
  version: "1.0.0"
  component: api

# Frontend pods  
labels:
  app: frontend
  component: web

# PostgreSQL (Bitnami)
labels:
  app.kubernetes.io/name: postgresql
  app.kubernetes.io/component: primary

# Redis (Bitnami)
labels:
  app.kubernetes.io/name: redis
  app.kubernetes.io/component: master
```

**Uso nei selettori di Chaos Mesh:**
```yaml
# Targeting del backend per gli esperimenti
selector:
  namespaces: [app]
  labelSelectors:
    app: backend

# Targeting di Redis (label Bitnami)
selector:
  namespaces: [app]
  labelSelectors:
    app.kubernetes.io/name: redis
```

---

## 9.6 Gestione delle Risorse

Ogni container ha **requests** (garantite) e **limits** (massimo):

```yaml
resources:
  requests:          # K8s garantisce queste risorse
    cpu: "100m"      # 0.1 core CPU
    memory: "128Mi"  # 128 MB RAM
  limits:            # K8s non permette di superare questi valori
    cpu: "500m"      # 0.5 core CPU
    memory: "512Mi"  # 512 MB RAM
```

**In una VM con 4 GB RAM:**

| Componente | RAM request | CPU request |
|---|---|---|
| 3x Backend | 3 × 128Mi = 384Mi | 3 × 100m = 300m |
| 2x Frontend | 2 × 64Mi = 128Mi | 2 × 50m = 100m |
| PostgreSQL | 256Mi | 100m |
| Redis | 128Mi | 100m |
| Prometheus stack | ~800Mi | ~200m |
| Chaos Mesh | ~200Mi | ~100m |
| K3s sistema | ~500Mi | ~200m |
| **Totale** | **~2.4 GB** | **~1.1 core** |

La VM ha bisogno di almeno **4 GB RAM** per ospitare tutto comodamente.

---

## 9.7 Persistenza dei Dati

PostgreSQL e Redis usano **PersistentVolumeClaim (PVC)**:

```bash
kubectl get pvc -n app
# NAME                         STATUS   VOLUME              CAPACITY
# data-postgresql-0            Bound    pvc-abc123...       8Gi
# redis-data-redis-master-0    Bound    pvc-def456...       8Gi
```

K3s usa **Local Path Provisioner** come storage class di default - i dati vengono salvati in `/var/lib/rancher/k3s/storage/` sulla VM.

```bash
# I dati di PostgreSQL sopravvivono al restart del pod
kubectl delete pod postgresql-0 -n app
# Il pod si riavvia e i dati sono ancora lì
```

---

## Riepilogo

Il progetto integra 4 layer tecnologici:

```
1. INFRASTRUTTURA: K3s su Ubuntu in Hyper-V
2. APPLICAZIONE:   FastAPI + Nginx + PostgreSQL + Redis
3. CHAOS:          Chaos Mesh con 5 esperimenti
4. OSSERVABILITÀ:  Prometheus + Grafana
```

Ogni layer è progettato per essere **osservabile** (metriche) e **testabile** (chaos experiments).

**Prossima lezione →** [10 - Osservabilità con Prometheus e Grafana](10-osservabilita.md)
