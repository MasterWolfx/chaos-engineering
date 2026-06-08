# 01 - Introduzione a Kubernetes

## 1.1 Il Problema: Gestire Applicazioni in Produzione

Prima di parlare di Kubernetes, è necessario capire il problema che risolve.

Negli anni 2000, un'applicazione web tipica era un **monolite**: un singolo processo che gestiva tutto - logica di business, database, interfaccia utente. Il deploy avveniva copiando file su un server fisico.

```
┌─────────────────────────────────┐
│         Server Fisico           │
│                                 │
│  ┌─────────────────────────┐    │
│  │    Applicazione         │    │
│  │   (tutto in uno)        │    │
│  │  - Frontend             │    │
│  │  - Backend              │    │
│  │  - Database             │    │
│  └─────────────────────────┘    │
└─────────────────────────────────┘
```

**Problemi:**
- Se il server cade, l'applicazione è giù
- Per scalare bisogna comprare un server più potente (scale up verticale)
- Un bug in una parte può abbattere tutto
- Il deploy richiede downtime

---

## 1.2 La Rivoluzione dei Container

### Virtual Machine vs Container

```
┌──────────────────────┐    ┌──────────────────────┐
│   Virtual Machine    │    │      Container        │
├──────────────────────┤    ├──────────────────────┤
│ App A │ App B │ App C│    │ App A │ App B │ App C│
├───────┼───────┼──────┤    ├───────┴───────┴──────┤
│ OS A  │ OS B  │ OS C │    │    Container Runtime  │
├───────┴───────┴──────┤    │    (containerd/Docker)│
│    Hypervisor        │    ├──────────────────────┤
├──────────────────────┤    │     OS Host           │
│    Hardware          │    ├──────────────────────┤
└──────────────────────┘    │    Hardware           │
                            └──────────────────────┘
```

| Caratteristica | VM | Container |
|---|---|---|
| Avvio | Minuti | Secondi |
| Dimensione immagine | GB | MB |
| Isolamento | Completo (kernel separato) | Parziale (kernel condiviso) |
| Overhead | Alto | Basso |
| Portabilità | Media | Alta |

Un **container** è un processo isolato che porta con sé tutto il necessario per eseguire l'applicazione: librerie, dipendenze, configurazione. L'immagine è definita da un `Dockerfile`:

```dockerfile
# Dockerfile del backend del progetto
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
```

### L'Ascesa dei Microservizi

Con i container è diventato pratico suddividere l'applicazione in **microservizi**: componenti piccoli, indipendenti, comunicanti via rete.

```
┌──────────┐   HTTP    ┌──────────┐   TCP    ┌──────────┐
│ Frontend │ ────────> │ Backend  │ ───────> │PostgreSQL│
│  (Nginx) │           │ (FastAPI)│          │          │
└──────────┘           └──────────┘          └──────────┘
                            │
                            │ TCP
                            ▼
                       ┌──────────┐
                       │  Redis   │
                       │  Cache   │
                       └──────────┘
```

**Vantaggi:**
- Ogni servizio scala indipendentemente
- Un servizio che cade non abbatte gli altri
- Team diversi lavorano su componenti diversi
- Deploy indipendenti

**Nuovi problemi:**
- Come gestisco 50 container distribuiti su 10 macchine?
- Come faccio a sapere dove sta girando ogni container?
- Come bilancio il traffico tra più istanze?
- Come gestisco i crash e i restart automatici?

**Risposta: un orchestratore di container.**

---

## 1.3 Cos'è Kubernetes

**Kubernetes** (dal greco: κυβερνήτης, "timoniere") è un sistema open source per l'automazione del deployment, della scalabilità e della gestione di applicazioni containerizzate.

> "Kubernetes è un sistema di gestione di container che automatizza il deployment, la scalabilità e le operazioni dei container su cluster di host." - kubernetes.io

### Breve Storia

| Anno | Evento |
|------|--------|
| 2003 | Google sviluppa **Borg**, sistema interno di orchestrazione |
| 2013 | Docker democratizza i container |
| 2014 | Google open-source Kubernetes (derivato da Borg) |
| 2016 | Cloud Native Computing Foundation (CNCF) adotta K8s |
| 2018 | K8s diventa lo standard de facto per l'orchestrazione |
| 2024 | Usato da oltre il 96% delle grandi aziende tech |

### Cosa fa Kubernetes

```
┌─────────────────────────────────────────────────────────┐
│                    Kubernetes                           │
│                                                         │
│  ✓ Self-healing      → riavvia i container crashati     │
│  ✓ Scaling           → aumenta/diminuisce le repliche   │
│  ✓ Load balancing    → distribuisce il traffico         │
│  ✓ Rolling updates   → deploy senza downtime            │
│  ✓ Service discovery → i servizi si trovano tra loro    │
│  ✓ Config management → gestisce segreti e configuraz.  │
│  ✓ Storage           → monta volumi persistenti         │
└─────────────────────────────────────────────────────────┘
```

### Il Principio Dichiarativo

Kubernetes adotta un approccio **dichiarativo**: non si dice *come* fare qualcosa, ma si dichiara lo *stato desiderato*. K8s si occupa di raggiungerlo e mantenerlo.

```yaml
# Non dico "avvia 3 container del backend"
# Dichiaro: "voglio che ci siano sempre 3 repliche del backend"
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  replicas: 3          # ← stato desiderato
  selector:
    matchLabels:
      app: backend
  template:
    spec:
      containers:
      - name: backend
        image: chaos-backend:local
```

Se uno dei 3 pod crasha, il **controller loop** di K8s rileva la discrepanza tra stato attuale (2 pod) e stato desiderato (3 pod) e crea automaticamente un nuovo pod.

```
Stato desiderato: 3 repliche
Stato attuale:    2 repliche  ← crash!
Azione K8s:       crea 1 pod
Stato attuale:    3 repliche  ✓
```

---

## 1.4 Kubernetes nel Contesto dell'Edge Computing

L'Edge Computing porta la computazione vicino ai dati, riducendo latenza e dipendenza dalla cloud centrale. Kubernetes è sempre più usato anche sull'edge grazie a distribuzioni leggere:

| Distribuzione | Uso tipico | Footprint |
|---|---|---|
| **K3s** (Rancher) | Edge, IoT, VM singola | ~70 MB RAM |
| **MicroK8s** | Developer, IoT | ~200 MB RAM |
| **K8s standard** | Cloud, datacenter | ~1 GB+ RAM |

> **Nel nostro progetto** usiamo **K3s** su una VM Ubuntu in Hyper-V - la scelta ideale per un ambiente di sviluppo/demo che simula un nodo edge.

---

## Riepilogo

- I container risolvono il problema "funziona sul mio PC"
- I microservizi portano flessibilità ma complessità operativa
- Kubernetes automatizza la gestione di container su larga scala
- Il modello dichiarativo garantisce la convergenza allo stato desiderato
- K3s è la variante leggera ideale per edge e sviluppo

**Prossima lezione →** [02 - Architettura di un Cluster Kubernetes](02-architettura-cluster.md)
