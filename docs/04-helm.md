# 04 - Helm: Package Manager per Kubernetes

## 4.1 Il Problema senza Helm

Deploiare un'applicazione su Kubernetes richiede molti file YAML: Deployment, Service, Ingress, ConfigMap, HPA, ServiceAccount... Con applicazioni complesse si arriva facilmente a 10-20 file.

**Senza Helm:**
```bash
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
kubectl apply -f ingress.yaml
kubectl apply -f hpa.yaml
kubectl apply -f servicemonitor.yaml
# ... per ogni ambiente (dev, staging, prod) devo duplicare tutto
# ... e cambiare a mano le variabili (immagine, repliche, host...)
```

**Con Helm:**
```bash
helm install backend ./helm/backend \
  --namespace app \
  --set image.tag=v1.2.3 \
  --set replicaCount=5
```

---

## 4.2 Cos'è Helm

**Helm** è il package manager per Kubernetes. Permette di:
- Impacchettare applicazioni K8s in **Chart** riutilizzabili
- Gestire le dipendenze tra componenti
- Parametrizzare la configurazione con **Values**
- Fare versioning di installazioni (**Release**)
- Aggiornare e fare rollback in modo atomico

```
┌─────────────────────────────────────────────────────┐
│                     Helm                            │
│                                                     │
│  Chart (template)  +  Values  →  Manifesti YAML     │
│                                        │            │
│                               kubectl apply         │
│                                        │            │
│                                   Kubernetes        │
└─────────────────────────────────────────────────────┘
```

---

## 4.3 Struttura di un Chart

```
helm/backend/                  ← root del chart
├── Chart.yaml                 ← metadati (nome, versione, descrizione)
├── values.yaml                ← valori di default
└── templates/                 ← template dei manifesti
    ├── deployment.yaml
    ├── service.yaml
    ├── hpa.yaml
    ├── servicemonitor.yaml
    └── _helpers.tpl           ← funzioni helper riutilizzabili
```

### Chart.yaml

```yaml
# helm/backend/Chart.yaml
apiVersion: v2
name: backend
description: FastAPI backend per il progetto Chaos Engineering
type: application
version: 0.1.0        # versione del chart
appVersion: "1.0.0"   # versione dell'applicazione
```

### values.yaml

```yaml
# helm/backend/values.yaml - valori di default
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
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 512Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 6
  targetCPUUtilizationPercentage: 70

env:
  DATABASE_URL: "postgresql+asyncpg://appuser:apppassword@postgresql:5432/appdb"
  REDIS_URL: "redis://redis-master:6379"
```

---

## 4.4 I Template

I template usano il linguaggio **Go Template** con funzioni aggiuntive fornite da Helm (Sprig library).

```yaml
# helm/backend/templates/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ .Release.Name }}               # ← nome della release
  namespace: {{ .Release.Namespace }}
  labels:
    app: {{ .Chart.Name }}
    version: {{ .Chart.AppVersion }}
spec:
  replicas: {{ .Values.replicaCount }}    # ← da values.yaml
  selector:
    matchLabels:
      app: {{ .Chart.Name }}
  template:
    metadata:
      labels:
        app: {{ .Chart.Name }}
    spec:
      containers:
      - name: {{ .Chart.Name }}
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        ports:
        - containerPort: {{ .Values.service.port }}
        env:
        {{- range $key, $val := .Values.env }}
        - name: {{ $key }}
          value: {{ $val | quote }}
        {{- end }}
        resources:
          {{- toYaml .Values.resources | nindent 10 }}
```

### Sintassi Go Template

```
{{ .Values.chiave }}           → valore da values.yaml
{{ .Release.Name }}            → nome della release Helm
{{ .Chart.Name }}              → nome del chart
{{ if .Values.autoscaling.enabled }} ... {{ end }}  → condizione
{{- range .Values.env }} ... {{- end }}              → ciclo
{{ "stringa" | upper }}        → pipe (funzioni)
{{ toYaml .Values.obj | nindent 4 }}  → serializza YAML indentato
```

---

## 4.5 Comandi Helm Fondamentali

### Gestione Repository

```bash
# Aggiungere repository
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add chaos-mesh https://charts.chaos-mesh.org
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts

# Aggiornare indice locale
helm repo update

# Cercare un chart
helm search repo bitnami/postgresql
helm search repo bitnami/postgresql --versions   # tutte le versioni
```

### Installazione e Upgrade

```bash
# Installare (crea una Release)
helm install <release-name> <chart> [flags]

# Esempi del progetto:
helm install backend ./helm/backend \
  --namespace app \
  --set image.repository=chaos-backend \
  --set image.tag=local \
  --set image.pullPolicy=Never \
  --set env.REDIS_URL=redis://redis-master:6379

helm install postgresql bitnami/postgresql \
  --namespace app \
  --set auth.username=appuser \
  --set auth.password=apppassword \
  --set auth.database=appdb

# Aggiornare una Release esistente
helm upgrade backend ./helm/backend --namespace app \
  --set image.tag=v2.0.0

# Installare O aggiornare (idempotente)
helm upgrade --install backend ./helm/backend --namespace app
```

### Ispezione e Debug

```bash
# Lista delle release installate
helm list -n app
helm list -A                    # tutti i namespace

# Stato di una release
helm status backend -n app

# Valori in uso (default + override)
helm get values backend -n app

# Anteprima dei manifesti generati (senza installare)
helm template backend ./helm/backend \
  --namespace app \
  --set image.tag=local

# Debug del template
helm install backend ./helm/backend --dry-run --debug
```

### Rollback e Disinstallazione

```bash
# Storico degli upgrade
helm history backend -n app

# Rollback alla revisione precedente
helm rollback backend -n app

# Rollback a una revisione specifica
helm rollback backend 2 -n app

# Disinstallare (rimuove tutti i manifesti)
helm uninstall backend -n app
```

---

## 4.6 Chart di Terze Parti: Bitnami

**Bitnami** (VMware) offre chart di alta qualità per i database e middleware più comuni. Nel progetto usiamo:

```bash
# PostgreSQL con autenticazione personalizzata
helm install postgresql bitnami/postgresql \
  --namespace app \
  --set auth.username=appuser \
  --set auth.password=apppassword \
  --set auth.database=appdb

# Redis senza password (ambiente di sviluppo)
helm install redis bitnami/redis \
  --namespace app \
  --set auth.enabled=false \
  --set architecture=standalone
```

**Perché Bitnami:**
- Chart battle-tested, usati in produzione da migliaia di aziende
- Aggiornamenti frequenti per vulnerabilità di sicurezza
- Configurazione ricca tramite values
- Documentazione eccellente

> **Nota importante:** Bitnami Redis crea un Service chiamato `redis-master` (non `redis`). Nel codice del backend bisogna usare `redis://redis-master:6379`.

---

## 4.7 Override dei Values

I valori possono essere sovrascritti in ordine crescente di priorità:

```
values.yaml (default)
    ↓
-f custom-values.yaml
    ↓
--set chiave=valore
    ↓
--set-string chiave=valore (forza string)
```

```bash
# File di override per produzione
cat values-production.yaml
---
replicaCount: 10
resources:
  limits:
    cpu: 2000m
    memory: 2Gi
autoscaling:
  maxReplicas: 20

# Applica override
helm install backend ./helm/backend \
  -f values-production.yaml \
  --set image.tag=v3.0.0   # priorità massima
```

---

## Riepilogo

```
Chart     = ricetta (template + values.yaml)
Release   = istanza installata di un chart
Values    = parametri configurabili
Repository = registro di chart (Bitnami, etc.)

helm install   → prima installazione
helm upgrade   → aggiornamento
helm rollback  → torna alla versione precedente
helm uninstall → rimozione
helm template  → anteprima YAML generato
```

**Prossima lezione →** [05 - Principi del Chaos Engineering](05-chaos-engineering.md)
