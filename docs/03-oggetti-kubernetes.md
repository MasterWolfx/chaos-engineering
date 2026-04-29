# 03 — Oggetti Kubernetes

## 3.1 Cosa sono gli Oggetti Kubernetes

Un **oggetto Kubernetes** è un'entità persistente nel sistema che rappresenta lo stato desiderato del cluster. Ogni oggetto ha:

```yaml
apiVersion: apps/v1          # versione dell'API
kind: Deployment              # tipo di oggetto
metadata:
  name: backend               # nome univoco nel namespace
  namespace: app              # namespace di appartenenza
  labels:                     # etichette per selezione
    app: backend
spec:                         # stato DESIDERATO
  replicas: 3
status:                       # stato ATTUALE (gestito da K8s)
  readyReplicas: 3
```

---

## 3.2 Namespace

I **namespace** sono partizioni virtuali del cluster che isolano le risorse.

```
┌─────────────────────────────────────────────────────┐
│                   Cluster K8s                       │
│                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────┐  │
│  │     app      │  │  monitoring  │  │chaos-mesh│  │
│  │              │  │              │  │          │  │
│  │ backend      │  │ prometheus   │  │controller│  │
│  │ frontend     │  │ grafana      │  │daemon    │  │
│  │ postgresql   │  │ alertmanager │  │dashboard │  │
│  │ redis        │  │              │  │          │  │
│  └──────────────┘  └──────────────┘  └──────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │              kube-system                     │   │
│  │  coredns  traefik  kube-proxy  flannel        │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

```yaml
# k8s/namespaces.yaml — dal nostro progetto
apiVersion: v1
kind: Namespace
metadata:
  name: app
  labels:
    chaos-mesh.org/inject: enabled   # ← etichetta per Chaos Mesh
```

```bash
# Comandi utili
kubectl get namespaces
kubectl get pods -n app              # pod nel namespace "app"
kubectl get pods -A                  # tutti i namespace
```

---

## 3.3 Pod

Il **Pod** è l'unità atomica di deployment in Kubernetes. Contiene uno o più container che condividono rete e storage.

```
┌──────────────────────────────────────────┐
│                  Pod                     │
│   IP: 10.42.0.15                         │
│                                          │
│  ┌─────────────────┐  ┌───────────────┐  │
│  │  Container      │  │  Sidecar      │  │
│  │  (backend app)  │  │  (opzionale)  │  │
│  │  port: 3000     │  │               │  │
│  └─────────────────┘  └───────────────┘  │
│                                          │
│  Volume condiviso: /tmp/data             │
└──────────────────────────────────────────┘
```

**Regola fondamentale:** I Pod sono **effimeri**. Non si modifica un Pod — lo si sostituisce. Ogni Pod ha un IP che cambia ad ogni ricreazione.

```bash
kubectl get pods -n app
kubectl describe pod backend-7d9f8b-xk2p1 -n app
kubectl logs backend-7d9f8b-xk2p1 -n app
kubectl exec -it backend-7d9f8b-xk2p1 -n app -- /bin/bash
```

---

## 3.4 Deployment

Il **Deployment** gestisce un insieme di Pod identici (repliche) e garantisce rolling update e rollback.

```yaml
# helm/backend/templates/deployment.yaml (semplificato)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: app
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1        # max pod extra durante update
      maxUnavailable: 0  # nessun pod giù durante update
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
      - name: backend
        image: chaos-backend:local
        ports:
        - containerPort: 3000
        env:
        - name: DATABASE_URL
          value: "postgresql+asyncpg://appuser:apppassword@postgresql:5432/appdb"
        - name: REDIS_URL
          value: "redis://redis-master:6379"
        resources:
          requests:
            cpu: "100m"
            memory: "128Mi"
          limits:
            cpu: "500m"
            memory: "512Mi"
        readinessProbe:
          httpGet:
            path: /api/health
            port: 3000
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /api/health
            port: 3000
          initialDelaySeconds: 15
          periodSeconds: 20
```

### Rolling Update

```
Deployment con 3 repliche, update da v1 → v2:

Stato iniziale:  [v1] [v1] [v1]
Step 1:          [v1] [v1] [v1] [v2]   ← +1 nuovo (maxSurge: 1)
Step 2:          [v1] [v1] [v2]        ← -1 vecchio (maxUnavailable: 0)
Step 3:          [v1] [v2] [v2]
Step 4:          [v2] [v2] [v2]
Fine:            [v2] [v2] [v2]        ← zero downtime!
```

```bash
kubectl rollout status deployment/backend -n app
kubectl rollout history deployment/backend -n app
kubectl rollout undo deployment/backend -n app   # rollback
```

---

## 3.5 Service

Un **Service** è un'astrazione che espone un gruppo di Pod come endpoint stabile. Risolve il problema degli IP dei Pod che cambiano.

```
                    Service: backend
                    ClusterIP: 10.43.100.50
                    port: 3000
                         │
              ┌──────────┼──────────┐
              │          │          │
        [Pod 10.42.0.10] [Pod 10.42.0.11] [Pod 10.42.0.12]
```

### Tipi di Service

| Tipo | Visibilità | Uso tipico |
|---|---|---|
| `ClusterIP` | Solo interno al cluster | Comunicazione tra servizi |
| `NodePort` | Host del nodo (porta 30000-32767) | Accesso esterno semplice |
| `LoadBalancer` | IP pubblico (cloud provider) | Produzione cloud |
| `ExternalName` | CNAME DNS | Accesso a servizi esterni |

```yaml
# Service ClusterIP per il backend
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: app
spec:
  type: ClusterIP
  selector:
    app: backend          # ← seleziona i Pod con questa label
  ports:
  - port: 3000
    targetPort: 3000
    protocol: TCP
```

```bash
kubectl get services -n app
kubectl get endpoints -n app   # vedi gli IP reali dietro ogni Service
```

---

## 3.6 Ingress

L'**Ingress** gestisce l'accesso HTTP/HTTPS esterno al cluster, con routing basato su host e path.

```
Internet
    │
    ▼
┌─────────────────────────────────────┐
│      Ingress Controller (Traefik)   │
│                                     │
│  app.localhost/          → frontend │
│  app.localhost/api/      → backend  │
└─────────────────────────────────────┘
    │                │
    ▼                ▼
 Service          Service
 frontend         backend
    │                │
[Pod][Pod]      [Pod][Pod][Pod]
```

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  namespace: app
spec:
  ingressClassName: traefik    # ← K3s usa Traefik (non nginx!)
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

---

## 3.7 HorizontalPodAutoscaler (HPA)

L'**HPA** scala automaticamente il numero di repliche di un Deployment in base a metriche (CPU, memoria, custom).

```
┌─────────────────────────────────────────────────────┐
│                   HPA Loop                          │
│                                                     │
│  Ogni 15 secondi:                                   │
│    cpu_media = media CPU tutti i pod backend        │
│    replicas_target = ceil(replicas * cpu/target)    │
│                                                     │
│  cpu = 80%, target = 70%, replicas = 3:             │
│    target = ceil(3 * 80/70) = ceil(3.43) = 4       │
│    → scala da 3 a 4 repliche                        │
└─────────────────────────────────────────────────────┘
```

```yaml
# helm/backend/templates/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-hpa
  namespace: app
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend
  minReplicas: 2
  maxReplicas: 6
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

```bash
kubectl get hpa -n app
# NAME          REFERENCE             TARGETS   MINPODS   MAXPODS   REPLICAS
# backend-hpa   Deployment/backend    15%/70%   2         6         3
```

---

## 3.8 ConfigMap e Secret

**ConfigMap** — configurazione non sensibile in formato chiave-valore.  
**Secret** — dati sensibili (password, token) codificati in Base64.

```yaml
# ConfigMap
apiVersion: v1
kind: ConfigMap
metadata:
  name: app-config
data:
  LOG_LEVEL: "info"
  MAX_CONNECTIONS: "100"

# Secret
apiVersion: v1
kind: Secret
metadata:
  name: db-credentials
type: Opaque
data:
  password: YXBwcGFzc3dvcmQ=   # base64("apppassword")
```

```yaml
# Utilizzo nel Pod
env:
- name: LOG_LEVEL
  valueFrom:
    configMapKeyRef:
      name: app-config
      key: LOG_LEVEL
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: db-credentials
      key: password
```

---

## 3.9 StatefulSet

A differenza del Deployment, lo **StatefulSet** è pensato per applicazioni con stato (database, cache) che necessitano di:
- Identità di rete stabile (`postgresql-0`, `postgresql-1`, ...)
- Storage persistente collegato alla specifica istanza
- Ordine di startup e shutdown

```
Deployment:  Pod nomi casuali   [backend-7d9f8-abc] [backend-7d9f8-xyz]
                                 eliminati/ricreati con nomi diversi

StatefulSet: Pod nomi stabili   [postgresql-0] [postgresql-1]
                                 mantenuti anche dopo restart
```

> **Nel progetto:** PostgreSQL e Redis sono gestiti come StatefulSet da Bitnami Helm chart.

---

## Riepilogo degli Oggetti

```
Namespace
└── Deployment (gestisce rolling update)
    └── ReplicaSet (mantiene N repliche)
        └── Pod (unità di esecuzione)
            └── Container (processo isolato)

Service          → endpoint stabile per i Pod
Ingress          → routing HTTP dall'esterno
HPA              → autoscaling basato su metriche
ConfigMap/Secret → configurazione e credenziali
StatefulSet      → applicazioni stateful (DB, cache)
```

**Prossima lezione →** [04 — Helm](04-helm.md)
