# 02 — Architettura di un Cluster Kubernetes

## 2.1 Visione d'insieme

Un **cluster Kubernetes** è un insieme di macchine (fisiche o virtuali) che lavorano insieme per eseguire applicazioni containerizzate. È composto da due tipi di nodi:

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLUSTER KUBERNETES                       │
│                                                                 │
│  ┌───────────────────────────┐   ┌───────────────────────────┐  │
│  │      CONTROL PLANE        │   │      WORKER NODES         │  │
│  │    (cervello del cluster) │   │   (muscoli del cluster)   │  │
│  │                           │   │                           │  │
│  │  • API Server             │   │  ┌─────────────────────┐  │  │
│  │  • etcd                   │   │  │    Node 1           │  │  │
│  │  • Scheduler              │   │  │  [Pod] [Pod] [Pod]  │  │  │
│  │  • Controller Manager     │   │  └─────────────────────┘  │  │
│  │                           │   │  ┌─────────────────────┐  │  │
│  └───────────────────────────┘   │  │    Node 2           │  │  │
│                                  │  │  [Pod] [Pod]        │  │  │
│                                  │  └─────────────────────┘  │  │
│                                  └───────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

> **Nel nostro progetto:** K3s in modalità single-node — control plane e worker girano sulla stessa VM Ubuntu. Perfetto per sviluppo e demo.

---

## 2.2 Il Control Plane

Il control plane è il sistema nervoso centrale del cluster. Prende decisioni globali e risponde agli eventi.

### API Server (`kube-apiserver`)

È il **punto di ingresso** per tutte le operazioni. Ogni comando `kubectl` parla con l'API Server tramite REST.

```
Developer          │   CI/CD Pipeline      │   Altri componenti K8s
kubectl apply ...  │   helm install ...    │   kubelet, scheduler...
        │                  │                          │
        └──────────────────┴──────────────────────────┘
                                │
                         ┌──────▼──────┐
                         │  API Server  │  ← autenticazione, validazione,
                         │  :6443       │    autorizzazione (RBAC)
                         └──────┬──────┘
                                │
                           legge/scrive
                                │
                         ┌──────▼──────┐
                         │    etcd     │
                         └─────────────┘
```

**Responsabilità:**
- Valida e processa le richieste REST
- Autentica e autorizza gli utenti (RBAC)
- Unico componente che legge/scrive su etcd
- Notifica gli altri componenti dei cambiamenti

### etcd

È il **database distribuito** del cluster. Memorizza lo stato completo del cluster in formato chiave-valore.

```bash
# Cosa c'è dentro etcd (semplificato):
/registry/pods/app/backend-7d9f8b-xk2p1     → {spec, status, ...}
/registry/deployments/app/backend            → {spec, status, ...}
/registry/services/app/backend               → {spec, clusterIP, ...}
/registry/nodes/osboxes                      → {capacity, conditions, ...}
```

**Caratteristiche chiave:**
- **Consistente** — tutti i nodi vedono lo stesso stato
- **Alta disponibilità** — in produzione si usa un cluster di 3 o 5 istanze
- **Il backup di etcd = backup dell'intero cluster**

### Scheduler (`kube-scheduler`)

Decide **su quale nodo** far girare ogni nuovo Pod, basandosi su:

```
Nuovo Pod da schedulare
        │
        ▼
┌───────────────────────────────────────┐
│           SCHEDULING PIPELINE         │
│                                       │
│  1. Filtering   → esclude nodi non    │
│                   idonei (risorse,    │
│                   taints, selectors)  │
│                                       │
│  2. Scoring     → punteggio nodi      │
│                   rimanenti (CPU      │
│                   disponibile, data   │
│                   locality, ...)      │
│                                       │
│  3. Binding     → assegna il pod al   │
│                   nodo con score più  │
│                   alto                │
└───────────────────────────────────────┘
```

### Controller Manager (`kube-controller-manager`)

Esegue i **controller loops** — cicli continui che confrontano stato attuale e stato desiderato.

Alcuni controller importanti:

| Controller | Compito |
|---|---|
| `ReplicaSet Controller` | Mantiene il numero corretto di Pod |
| `Deployment Controller` | Gestisce rolling update e rollback |
| `Node Controller` | Monitora la salute dei nodi |
| `HPA Controller` | Scala i deployment in base a metriche |
| `EndpointSlice Controller` | Aggiorna gli endpoint dei Service |

```
┌─────────────────────────────────────────┐
│         Controller Loop (esempio HPA)   │
│                                         │
│  while(true):                           │
│    current = getCPUUsage(backend)       │
│    desired = 70%                        │
│    if current > desired:                │
│      scaleUp(backend)    ← agisce!      │
│    elif current < desired * 0.5:        │
│      scaleDown(backend)  ← agisce!      │
│    sleep(15s)                           │
└─────────────────────────────────────────┘
```

---

## 2.3 Il Worker Node

Ogni worker node esegue i container delle applicazioni ed espone risorse al cluster.

### kubelet

L'**agente** che gira su ogni nodo. Riceve le specifiche dei Pod dall'API Server e si assicura che i container siano in esecuzione.

```
API Server  ──→  kubelet  ──→  container runtime (containerd)
               "esegui Pod X"  "crea container, monta volumi..."
```

**kubelet controlla continuamente:**
- Il container è vivo? → liveness probe
- Il container è pronto a ricevere traffico? → readiness probe
- Usa troppa memoria? → OOMKill e restart

### kube-proxy

Gestisce le **regole di rete** sul nodo (iptables/ipvs) per implementare i Service di Kubernetes.

```
Richiesta a ClusterIP 10.43.100.50:3000
           │
    kube-proxy (iptables)
           │
    ┌──────┴──────┐
    │   DNAT      │  → sceglie un pod reale (load balancing)
    └──────┬──────┘
           │
   Pod 10.42.0.15:3000  oppure  Pod 10.42.0.16:3000
```

### Container Runtime

Il motore che **esegue effettivamente** i container. Kubernetes usa l'interfaccia CRI (Container Runtime Interface).

| Runtime | Note |
|---|---|
| **containerd** | Standard de facto, usato da K3s, GKE, EKS |
| **CRI-O** | Leggero, usato da OpenShift |
| Docker (tramite dockershim) | Deprecato in K8s 1.24+ |

> **Nel nostro progetto:** K3s usa **containerd** con socket in `/run/k3s/containerd/containerd.sock` — diverso dal Docker standard, per questo serve la configurazione specifica in Chaos Mesh.

---

## 2.4 La Rete in Kubernetes

### CNI — Container Network Interface

Ogni Pod riceve un indirizzo IP unico e raggiungibile all'interno del cluster, grazie al plugin CNI.

```
┌─────────────────────────────────────────────────┐
│               Cluster Network                   │
│                                                 │
│  Pod CIDR: 10.42.0.0/16                         │
│                                                 │
│  backend-pod-1:  10.42.0.10                     │
│  backend-pod-2:  10.42.0.11                     │
│  frontend-pod-1: 10.42.0.20                     │
│  postgresql-0:   10.42.0.30                     │
│  redis-master-0: 10.42.0.31                     │
│                                                 │
│  Service CIDR: 10.43.0.0/16                     │
│                                                 │
│  svc/backend:    10.43.100.50   → pods backend  │
│  svc/postgresql: 10.43.100.60   → pods postgres  │
│  svc/redis:      10.43.100.70   → pods redis     │
└─────────────────────────────────────────────────┘
```

**K3s usa Flannel** (overlay network con VXLAN) come CNI di default.

### DNS Interno (CoreDNS)

CoreDNS risolve i nomi dei Service all'interno del cluster:

```
backend → postgresql:5432
           ↓ (DNS lookup)
           postgresql.app.svc.cluster.local → 10.43.100.60
```

Il formato completo è: `<service>.<namespace>.svc.cluster.local`

Questo è il motivo per cui nel codice del backend scriviamo:
```python
DATABASE_URL = "postgresql+asyncpg://appuser:apppassword@postgresql:5432/appdb"
REDIS_URL = "redis://redis-master:6379"
```

Invece di usare indirizzi IP che cambiano ad ogni deploy.

---

## 2.5 Architettura del Nostro Cluster (K3s)

```
┌─────────────────────────────────────────────────────────┐
│               VM Ubuntu 22.04 (Hyper-V)                 │
│               Indirizzo IP: 192.168.x.x                 │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │              K3s (single-node)                  │    │
│  │                                                 │    │
│  │  Control Plane:                                 │    │
│  │  • API Server    :6443                          │    │
│  │  • etcd          (embedded SQLite in K3s)       │    │
│  │  • Scheduler                                    │    │
│  │  • Controller Manager                           │    │
│  │                                                 │    │
│  │  Worker:                                        │    │
│  │  • kubelet                                      │    │
│  │  • kube-proxy                                   │    │
│  │  • containerd    /run/k3s/containerd/           │    │
│  │  • Flannel CNI   (pod CIDR: 10.42.0.0/16)      │    │
│  │  • Traefik       (Ingress Controller built-in)  │    │
│  │  • CoreDNS                                      │    │
│  │                                                 │    │
│  │  Namespace: app                                 │    │
│  │  • backend (3 repliche)                         │    │
│  │  • frontend (2 repliche)                        │    │
│  │  • postgresql (StatefulSet)                     │    │
│  │  • redis-master (StatefulSet)                   │    │
│  └─────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
```

> **Differenza chiave da K8s standard:** K3s usa SQLite al posto di etcd (in configurazione single-node) e include Traefik come ingress controller pre-installato invece di nginx-ingress.

---

## Riepilogo

| Componente | Dove gira | Funzione |
|---|---|---|
| API Server | Control Plane | Unico punto di accesso, REST API |
| etcd | Control Plane | Database dello stato del cluster |
| Scheduler | Control Plane | Assegna Pod ai nodi |
| Controller Manager | Control Plane | Mantiene lo stato desiderato |
| kubelet | Ogni nodo | Esegue i Pod |
| kube-proxy | Ogni nodo | Gestisce le regole di rete |
| containerd | Ogni nodo | Runtime container |
| CoreDNS | kube-system | DNS interno del cluster |
| Flannel | Ogni nodo | Rete overlay tra Pod |

**Prossima lezione →** [03 — Oggetti Kubernetes](03-oggetti-kubernetes.md)
