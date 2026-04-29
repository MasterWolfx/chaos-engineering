# Chaos Engineering su Kubernetes
**Resilience Testing di un'Architettura a Microservizi**

> Progetto individuale — Corso di Distributed Edge Programming, Università degli Studi di Modena e Reggio Emilia, A.A. 2025/2026 
> Studente: Leonardo Cavedoni

---

## Panoramica

Questo progetto dimostra come applicare il **Chaos Engineering** a un'architettura a microservizi deployata su Kubernetes. L'obiettivo è verificare la resilienza del sistema attraverso fault injection controllata con **Chaos Mesh**, monitorando gli effetti in real-time con **Prometheus** e **Grafana**.

---

## Architettura

```
┌─────────────────────────────────── namespace: app ──────────────────────────────────┐
│                                                                                      │
│   ┌──────────────┐    ┌──────────────────┐    ┌─────────────┐    ┌──────────────┐   │
│   │  Frontend    │───▶│   Backend API    │───▶│ PostgreSQL  │    │    Redis     │   │
│   │  Nginx x2   │    │   FastAPI x3     │    │ StatefulSet │◀───│   Cache      │   │
│   └──────────────┘    └──────────────────┘    └─────────────┘    └──────────────┘   │
│         ▲                     ▲ HPA (2-6)                                           │
└─────────┼─────────────────────┼───────────────────────────────────────────────────-─┘
          │                     │
    Ingress nginx          ServiceMonitor
          │                     │
   ┌──────┴──────┐    ┌─────────┴────────┐    ┌─────────────────────┐
   │   Internet  │    │    Prometheus     │───▶│       Grafana        │
   └─────────────┘    └──────────────────┘    └─────────────────────┘
                       namespace: monitoring

                       ┌──────────────────────────────┐
                       │  Chaos Mesh (namespace:       │
                       │  chaos-mesh)                  │
                       │  Operator + Dashboard + CRDs  │
                       └──────────────────────────────┘
```

### Componenti

| Componente   | Tecnologia               | Repliche | Ruolo                          |
|-------------|--------------------------|----------|--------------------------------|
| Frontend    | Nginx + HTML statico     | 2        | Interfaccia utente, proxy API  |
| Backend API | FastAPI (Python)         | 3 (+HPA) | Logica applicativa, REST API   |
| Database    | PostgreSQL 15 (StatefulSet)| 1      | Persistenza dati principale    |
| Cache       | Redis 7                  | 1        | Cache sessioni e query         |

### Namespace K8s

| Namespace    | Contenuto                                 | Scopo                          |
|-------------|-------------------------------------------|--------------------------------|
| `app`        | Frontend, Backend, PostgreSQL, Redis, HPA | Applicazione target            |
| `chaos-mesh` | Chaos Mesh Operator, Dashboard, CRD       | Piattaforma fault injection     |
| `monitoring` | Prometheus, Grafana, Alertmanager         | Observability e metriche       |

---

## Struttura Repository

```
chaos-kubernetes/
├── backend/                    # Applicazione FastAPI
│   ├── app/
│   │   ├── main.py             # Entry point FastAPI + endpoint API
│   │   ├── models.py           # Modello SQLAlchemy (Item)
│   │   ├── database.py         # Connessione PostgreSQL (asyncpg)
│   │   └── cache.py            # Client Redis con fallback graceful
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                   # Applicazione HTML + Nginx
│   ├── html/index.html         # SPA vanilla JS per gestione Items
│   ├── nginx.conf              # Proxy verso backend
│   └── Dockerfile
├── helm/                       # Helm Charts
│   ├── frontend/               # Chart frontend (Deployment + Service)
│   ├── backend/                # Chart backend (Deployment + Service + HPA + ServiceMonitor)
│   ├── postgresql/             # Wrapper Bitnami PostgreSQL
│   └── redis/                  # Wrapper Bitnami Redis
├── chaos-experiments/          # CRD Chaos Mesh
│   ├── 01-pod-failure.yaml
│   ├── 02-network-delay.yaml
│   ├── 03-network-partition.yaml
│   ├── 04-cpu-stress.yaml
│   └── 05-pod-failure-cascading.yaml
├── k8s/                        # Manifest Kubernetes base
│   ├── namespaces.yaml
│   └── ingress.yaml
├── monitoring/
│   └── grafana-dashboards/
│       └── app-resilience.json # Dashboard Grafana pronta
├── load-test/
│   └── k6-script.js            # Script k6 per load testing
└── .github/workflows/ci.yml    # GitHub Actions CI/CD
```

---

## Prerequisiti

- [K3s](https://k3s.io/) o [MicroK8s](https://microk8s.io/) (oppure qualsiasi cluster K8s ≥ 1.26)
- [Helm 3](https://helm.sh/)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [k6](https://k6.io/) (per i load test)

---

## Setup Completo

### 1. Crea i Namespace

```bash
kubectl apply -f k8s/namespaces.yaml
```

### 2. Installa l'Ingress Controller (nginx)

```bash
helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx
helm repo update
helm install ingress-nginx ingress-nginx/ingress-nginx \
  --namespace kube-system
```

### 3. Installa lo Stack di Monitoring

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set grafana.adminPassword=admin
```

Importa la dashboard Grafana:
```bash
# Accedi a Grafana (porta-forward o Ingress) e importa:
monitoring/grafana-dashboards/app-resilience.json
```

### 4. Installa Chaos Mesh

```bash
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm repo update
helm install chaos-mesh chaos-mesh/chaos-mesh \
  --namespace chaos-mesh \
  --set chaosDaemon.runtime=containerd \
  --set chaosDaemon.socketPath=/run/containerd/containerd.sock
```

### 5. Deploy dell'Applicazione

```bash
# Aggiorna le dipendenze Bitnami
helm dependency update helm/postgresql
helm dependency update helm/redis

# Deploy PostgreSQL
helm install postgresql helm/postgresql \
  --namespace app

# Deploy Redis
helm install redis helm/redis \
  --namespace app

# Deploy Backend
helm install backend helm/backend \
  --namespace app

# Deploy Frontend
helm install frontend helm/frontend \
  --namespace app

# Applica l'Ingress
kubectl apply -f k8s/ingress.yaml
```

### 6. Verifica il Deploy

```bash
kubectl get pods -n app
# Atteso: frontend-* (2/2), backend-* (3/3), postgresql-*, redis-*

kubectl get hpa -n app
# Atteso: backend-hpa TARGETS <10%/70%  MINPODS 2  MAXPODS 6
```

L'app è raggiungibile su: http://app.localhost

---

## Eseguire i Load Test

```bash
# Avvia il traffico di fondo (tieni aperto durante gli esperimenti)
k6 run load-test/k6-script.js
```

---

## Esperimenti di Chaos Engineering

Ogni esperimento segue la struttura classica del Chaos Engineering:
1. **Definire lo Steady State** (latenza p95 < 200ms, error rate 0%)
2. **Formulare l'ipotesi** su cosa accadrà dopo il fault
3. **Eseguire il fault** con Chaos Mesh mentre il sistema è sotto carico
4. **Osservare e misurare** su Grafana
5. **Trarre conclusioni** — il sistema ha rispettato l'ipotesi?

### Esperimento 1 — Pod Failure

```bash
kubectl apply -f chaos-experiments/01-pod-failure.yaml
```

| | |
|---|---|
| **Fault** | PodChaos `pod-kill` — 1 pod backend ogni 60s |
| **Ipotesi** | K8s rileva il pod down e lo riavvia entro 30s; le altre repliche continuano a servire traffico |
| **Verifica** | `kubectl get pods -n app -w` — nessun errore 5xx su Grafana |

### Esperimento 2 — Network Delay

```bash
kubectl apply -f chaos-experiments/02-network-delay.yaml
```

| | |
|---|---|
| **Fault** | NetworkChaos `delay` 500ms ±100ms — backend → PostgreSQL |
| **Ipotesi** | Latenza API aumenta visibilmente; app rimane funzionale (degraded performance) |
| **Verifica** | Dashboard Grafana — picco latenza p95, error rate stabile a 0% |

### Esperimento 3 — Network Partition (Cache)

```bash
kubectl apply -f chaos-experiments/03-network-partition.yaml
```

| | |
|---|---|
| **Fault** | NetworkChaos `partition` — backend ↔ Redis |
| **Ipotesi** | Backend cade in fallback (cache miss), richieste vanno a DB, nessun errore 5xx |
| **Verifica** | Latenza più alta ma nessun 5xx; log backend mostrano "Cache MISS" |

### Esperimento 4 — CPU Stress + HPA

```bash
kubectl apply -f chaos-experiments/04-cpu-stress.yaml
```

| | |
|---|---|
| **Fault** | StressChaos `cpu` 80% su tutti i pod backend |
| **Ipotesi** | HPA rileva l'aumento CPU e scala nuove repliche; latenza rimane stabile |
| **Verifica** | `kubectl get hpa -n app -w` — replica count aumenta; Grafana mostra CPU spike poi stabilizzazione |

### Esperimento 5 — Pod Failure Cascading

```bash
kubectl apply -f chaos-experiments/05-pod-failure-cascading.yaml
```

| | |
|---|---|
| **Fault** | PodChaos `pod-kill` — tutti i pod backend in sequenza ogni 20s |
| **Ipotesi** | K8s scala e ripristina continuamente; almeno 1 replica sempre up |
| **Verifica** | Dashboard Grafana mostra oscillazione pod count ma 0 downtime totale |

### Stop di tutti gli esperimenti

```bash
kubectl delete podchaos,networkchaos,stresschaos --all -n chaos-mesh
```

---

## Script Demo (8-10 minuti)

| Step | Azione | Cosa si osserva |
|------|--------|-----------------|
| 1 | `kubectl get pods -n app` + browser su http://app.localhost | Tutti i pod Running, API rispondono |
| 2 | Apri Grafana → dashboard **App Resilience** | Steady state: latenza bassa, error rate 0% |
| 3 | Apri Chaos Mesh Dashboard | Interfaccia esperimenti configurati |
| 4 | `kubectl apply -f chaos-experiments/01-pod-failure.yaml` | Pod scompare e K8s lo riavvia, spike minimo su Grafana |
| 5 | `kubectl apply -f chaos-experiments/02-network-delay.yaml` | Latenza API aumenta visibilmente |
| 6 | `kubectl apply -f chaos-experiments/04-cpu-stress.yaml` | CPU sale, HPA scala nuovi pod |
| 7 | `kubectl delete podchaos,networkchaos,stresschaos --all -n chaos-mesh` | Sistema torna allo steady state |

---

## Stack Tecnologico

| Categoria          | Tecnologie                              |
|-------------------|-----------------------------------------|
| Orchestrazione    | Kubernetes (K3s / MicroK8s)            |
| Packaging & Deploy| Helm 3                                  |
| Chaos Engineering | Chaos Mesh                              |
| Backend           | FastAPI + asyncpg + Redis (Python 3.12) |
| Database          | PostgreSQL 15 (StatefulSet)             |
| Cache             | Redis 7                                 |
| Frontend          | Nginx + HTML/JS statico                 |
| Observability     | Prometheus + Grafana (kube-prometheus)  |
| Load Testing      | k6                                      |
| CI/CD             | GitHub Actions                          |

---

## Contribuire

1. Fork del repository
2. Crea un branch: `git checkout -b feature/miglioramento`
3. Commit: `git commit -m "feat: descrizione"`
4. Push e apri una Pull Request

---

*Progetto realizzato per il corso di Distributed Edge Programming - Università degli Studi di Modena e Reggio Emilia, A.A. 2025/2026*
