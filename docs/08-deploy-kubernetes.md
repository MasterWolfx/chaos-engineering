# 08 — Deploy su Kubernetes

## 8.1 Il Percorso dal Codice al Cluster

```
┌──────────────┐    docker build    ┌──────────────┐
│  Codice      │ ────────────────→  │  Immagine    │
│  sorgente    │                    │  Docker      │
└──────────────┘                    └──────┬───────┘
                                           │
                                    k3s ctr import
                                           │
                                    ┌──────▼───────┐
                                    │  Containerd  │
                                    │  (K3s local) │
                                    └──────┬───────┘
                                           │
                                    helm install
                                           │
                                    ┌──────▼───────┐
                                    │  Kubernetes  │
                                    │  (Running)   │
                                    └──────────────┘
```

---

## 8.2 Build dell'Immagine Docker

### Il Dockerfile del Backend

```dockerfile
# backend/Dockerfile
FROM python:3.12-slim

# Installa dipendenze di sistema per asyncpg
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia e installa dipendenze Python prima del codice
# (ottimizza il layer caching di Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia il codice sorgente
COPY app/ ./app/

EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
```

### Build e Import in K3s

K3s usa **containerd** come runtime, non Docker. Le immagini costruite con Docker non sono automaticamente disponibili in K3s — bisogna importarle:

```bash
# 1. Build dell'immagine con Docker
docker build -t chaos-backend:local ./backend
docker build -t chaos-frontend:local ./frontend

# 2. Salva come file tar ed importa in containerd di K3s
docker save chaos-backend:local | sudo k3s ctr images import -
docker save chaos-frontend:local | sudo k3s ctr images import -

# 3. Verifica che le immagini siano disponibili in K3s
sudo k3s ctr images list | grep chaos
```

**Perché `imagePullPolicy: Never`:**
```yaml
# Nel values.yaml del chart
image:
  repository: chaos-backend
  tag: local
  pullPolicy: Never    # ← non cercare l'immagine su Docker Hub!
                       #   usa quella già presente in containerd
```

---

## 8.3 Struttura dei Namespace

Il primo passo del deploy è creare i namespace con le label corrette:

```yaml
# k8s/namespaces.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: app
  labels:
    chaos-mesh.org/inject: enabled    # ← permette a Chaos Mesh di agire
---
apiVersion: v1
kind: Namespace
metadata:
  name: monitoring
---
apiVersion: v1
kind: Namespace
metadata:
  name: chaos-mesh
```

```bash
kubectl apply -f k8s/namespaces.yaml
```

---

## 8.4 Deploy di PostgreSQL e Redis (Bitnami)

```bash
# PostgreSQL
helm install postgresql bitnami/postgresql \
  --namespace app \
  --set auth.username=appuser \
  --set auth.password=apppassword \
  --set auth.database=appdb \
  --set primary.resources.requests.memory=256Mi \
  --set primary.resources.requests.cpu=100m

# Redis (modalità standalone, senza auth per sviluppo)
helm install redis bitnami/redis \
  --namespace app \
  --set auth.enabled=false \
  --set architecture=standalone \
  --set master.resources.requests.memory=128Mi \
  --set master.resources.requests.cpu=100m
```

**Verifica:**
```bash
kubectl get pods -n app
# NAME                READY   STATUS    RESTARTS
# postgresql-0        1/1     Running   0
# redis-master-0      1/1     Running   0
```

**Test di connessione:**
```bash
# Accedi a PostgreSQL
kubectl exec -it postgresql-0 -n app -- psql -U appuser -d appdb

# Accedi a Redis
kubectl exec -it redis-master-0 -n app -- redis-cli ping
# PONG
```

---

## 8.5 Il Chart Helm del Backend

```
helm/backend/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── deployment.yaml
    ├── service.yaml
    ├── hpa.yaml
    └── servicemonitor.yaml
```

### `values.yaml` — Configurazione Completa

```yaml
replicaCount: 3

image:
  repository: chaos-backend
  tag: local
  pullPolicy: Never

service:
  type: ClusterIP
  port: 3000

resources:
  requests:
    cpu: "100m"
    memory: "128Mi"
  limits:
    cpu: "500m"
    memory: "512Mi"

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 6
  targetCPUUtilizationPercentage: 70

env:
  DATABASE_URL: "postgresql+asyncpg://appuser:apppassword@postgresql:5432/appdb"
  REDIS_URL: "redis://redis-master:6379"

livenessProbe:
  httpGet:
    path: /api/health
    port: 3000
  initialDelaySeconds: 15
  periodSeconds: 20
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /api/health
    port: 3000
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3
```

### `hpa.yaml` — Autoscaling

```yaml
# helm/backend/templates/hpa.yaml
{{- if .Values.autoscaling.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ .Release.Name }}-hpa
  namespace: {{ .Release.Namespace }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ .Release.Name }}
  minReplicas: {{ .Values.autoscaling.minReplicas }}
  maxReplicas: {{ .Values.autoscaling.maxReplicas }}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: {{ .Values.autoscaling.targetCPUUtilizationPercentage }}
{{- end }}
```

### `servicemonitor.yaml` — Integrazione Prometheus

```yaml
# helm/backend/templates/servicemonitor.yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: {{ .Release.Name }}
  namespace: {{ .Release.Namespace }}
  labels:
    release: prometheus    # ← label richiesta da kube-prometheus-stack
spec:
  selector:
    matchLabels:
      app: {{ .Chart.Name }}
  endpoints:
  - port: http
    path: /metrics         # esposto da prometheus-fastapi-instrumentator
    interval: 15s
```

### Deploy del Backend

```bash
helm install backend helm/backend \
  --namespace app \
  --set image.repository=chaos-backend \
  --set image.tag=local \
  --set image.pullPolicy=Never \
  --set env.REDIS_URL=redis://redis-master:6379
```

---

## 8.6 Deploy del Frontend

```bash
helm install frontend helm/frontend \
  --namespace app \
  --set image.repository=chaos-frontend \
  --set image.tag=local \
  --set image.pullPolicy=Never
```

---

## 8.7 Configurazione dell'Ingress (Traefik)

K3s include **Traefik** come ingress controller invece di nginx-ingress. È fondamentale usare `ingressClassName: traefik`.

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  namespace: app
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web
spec:
  ingressClassName: traefik    # ← obbligatorio per K3s
  rules:
  - host: app.localhost
    http:
      paths:
      - path: /api
        pathType: Prefix
        backend:
          service:
            name: backend
            port:
              number: 3000
      - path: /
        pathType: Prefix
        backend:
          service:
            name: frontend
            port:
              number: 80
```

```bash
kubectl apply -f k8s/ingress.yaml

# Verifica
kubectl get ingress -n app
# NAME          CLASS     HOSTS           ADDRESS      PORTS
# app-ingress   traefik   app.localhost   10.0.2.15    80
```

**Accesso dall'host Windows:**

Aggiungere al file `C:\Windows\System32\drivers\etc\hosts`:
```
<IP_VM>    app.localhost
```

Poi navigare su `http://app.localhost`.

---

## 8.8 Verifica del Deploy Completo

```bash
# Tutti i pod devono essere Running
kubectl get pods -n app
# NAME                        READY   STATUS    RESTARTS
# postgresql-0                1/1     Running   0
# redis-master-0              1/1     Running   0
# backend-7d9f8b-abc          1/1     Running   0
# backend-7d9f8b-def          1/1     Running   0
# backend-7d9f8b-ghi          1/1     Running   0
# frontend-5c9f7d-xyz         1/1     Running   0
# frontend-5c9f7d-uvw         1/1     Running   0

# HPA configurato
kubectl get hpa -n app
# NAME          REFERENCE             TARGETS   MINPODS   MAXPODS   REPLICAS
# backend-hpa   Deployment/backend    15%/70%   2         6         3

# Servizi raggiungibili
kubectl get svc -n app
# NAME           TYPE        CLUSTER-IP      PORT(S)
# backend        ClusterIP   10.43.100.50    3000/TCP
# frontend       ClusterIP   10.43.100.51    80/TCP
# postgresql     ClusterIP   10.43.100.60    5432/TCP
# redis-master   ClusterIP   10.43.100.70    6379/TCP

# Test API
curl http://app.localhost/api/health
# {"status":"ok"}

curl http://app.localhost/api/items
# []

curl -X POST http://app.localhost/api/items \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","description":"Item di prova"}'
# {"name":"Test","description":"Item di prova","id":1}
```

---

## 8.9 Troubleshooting Comune

| Problema | Causa | Soluzione |
|---|---|---|
| `ImagePullBackOff` | Immagine non trovata in containerd | `docker save ... \| k3s ctr images import -` |
| `CrashLoopBackOff` | App crasha all'avvio | `kubectl logs pod-name --previous` |
| Redis DNS failure | Nome servizio errato | Usa `redis-master` non `redis` |
| Ingress 404 | `ingressClassName: nginx` su K3s | Cambia in `ingressClassName: traefik` |
| HPA `<unknown>/70%` | metrics-server non disponibile | K3s include metrics-server, verifica con `kubectl top pods` |

---

## Riepilogo Ordine di Deploy

```
1. kubectl apply -f k8s/namespaces.yaml
2. helm install postgresql bitnami/postgresql ...
3. helm install redis bitnami/redis ...
4. docker build + k3s ctr import (immagini locali)
5. helm install backend ./helm/backend ...
6. helm install frontend ./helm/frontend ...
7. kubectl apply -f k8s/ingress.yaml
8. Verifica: kubectl get pods -n app
9. Test: curl http://app.localhost/api/health
```

**Prossima lezione →** [09 — Componenti del Progetto](09-componenti-progetto.md)
