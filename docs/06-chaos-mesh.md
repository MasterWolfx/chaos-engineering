# 06 — Chaos Mesh

## 6.1 Cos'è Chaos Mesh

**Chaos Mesh** è una piattaforma open source di Chaos Engineering nativa per Kubernetes, sviluppata da PingCAP (i creatori di TiDB). È il progetto ufficiale della CNCF (Cloud Native Computing Foundation) per il fault injection su K8s.

```
┌──────────────────────────────────────────────────────────┐
│                    Chaos Mesh                            │
│                                                          │
│  • Fault injection nativo Kubernetes (CRD-based)         │
│  • Dashboard Web per gestire esperimenti                 │
│  • Supporto a decine di tipi di chaos                    │
│  • Scheduling e workflow degli esperimenti               │
│  • Integrazione con Prometheus e Grafana                 │
│  • Fine-grained selector (namespace, label, pod name)    │
└──────────────────────────────────────────────────────────┘
```

---

## 6.2 Architettura di Chaos Mesh

```
┌─────────────────────────────────────────────────────────────┐
│                      Chaos Mesh                             │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │            chaos-controller-manager                 │    │
│  │  • Elabora le risorse CRD (PodChaos, NetworkChaos)  │    │
│  │  • Scheduling degli esperimenti                     │    │
│  │  • Webhook per validazione risorse                  │    │
│  └────────────────────────┬────────────────────────────┘    │
│                           │ gRPC                            │
│  ┌────────────────────────▼────────────────────────────┐    │
│  │              chaos-daemon (DaemonSet)               │    │
│  │  • Gira su ogni nodo del cluster                    │    │
│  │  • Esegue effettivamente il chaos (iptables, cgroup)│    │
│  │  • Accesso privilegiato al nodo host                │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              chaos-dashboard                        │    │
│  │  • UI Web per gestire e monitorare esperimenti      │    │
│  │  • Porta 2333                                       │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Come funziona il fault injection

```
1. Sviluppatore applica una risorsa CRD:
   kubectl apply -f 01-pod-failure.yaml

2. API Server K8s notifica il controller-manager
   (tramite webhook di ammissione)

3. controller-manager elabora la risorsa,
   seleziona i pod target tramite il selector

4. controller-manager invia istruzione al chaos-daemon
   sul nodo dove gira il pod target (via gRPC)

5. chaos-daemon esegue il chaos:
   • pod-kill → chiama containerd per terminare il container
   • network delay → aggiunge regole tc/netem
   • CPU stress → lancia processo di stress in cgroup
```

---

## 6.3 Custom Resource Definitions (CRD)

Chaos Mesh estende Kubernetes con i propri tipi di risorse tramite **CRD**. Un CRD è essenzialmente un nuovo tipo di oggetto Kubernetes.

```bash
# Vedi tutti i CRD installati da Chaos Mesh
kubectl get crd | grep chaos-mesh
```

```
awschaos.chaos-mesh.org
dnschaos.chaos-mesh.org
gcpchaos.chaos-mesh.org
httpchaos.chaos-mesh.org
iochaos.chaos-mesh.org
jvmchaos.chaos-mesh.org
kernelchaos.chaos-mesh.org
networkchaos.chaos-mesh.org      ← usato nel progetto
physicalmachinechaos.chaos-mesh.org
podchaos.chaos-mesh.org          ← usato nel progetto
schedule.chaos-mesh.org          ← usato nel progetto
stresschaos.chaos-mesh.org       ← usato nel progetto
timechaos.chaos-mesh.org
workflow.chaos-mesh.org
```

---

## 6.4 Tipi di Chaos Supportati

### PodChaos

Agisce direttamente sui Pod:

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
spec:
  action: pod-kill        # uccide il pod (K8s lo riavvia)
  action: pod-failure     # rende il pod non schedulabile
  action: container-kill  # uccide solo un container nel pod
```

### NetworkChaos

Manipola il traffico di rete tra Pod:

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
spec:
  action: delay      # aggiunge latenza
  action: loss       # perdita di pacchetti
  action: duplicate  # duplica pacchetti
  action: corrupt    # corrompe pacchetti
  action: bandwidth  # limita la banda
  action: partition  # blocca completamente il traffico
```

### StressChaos

Stresa le risorse del sistema:

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
spec:
  stressors:
    cpu:
      workers: 2      # numero di thread stressors
      load: 80        # percentuale di CPU da occupare
    memory:
      workers: 1
      size: "256MB"   # memoria da allocare
```

### IOChaos

Introduce errori nel filesystem:

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: IOChaos
spec:
  action: latency    # latenza sulle syscall I/O
  action: fault      # errori casuali (ENOSPC, ENOENT)
  action: attrOverride  # modifica attributi file
```

### TimeChaos

Distorce l'orologio di sistema:

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: TimeChaos
spec:
  timeOffset: "-2h"  # riporta il clock indietro di 2 ore
```

### Schedule (Ricorrente)

Esegue qualsiasi tipo di chaos su uno schedule ricorrente:

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: Schedule
spec:
  schedule: "@every 20s"  # ogni 20 secondi
  type: PodChaos
  podChaos:               # configurazione inline del chaos
    action: pod-kill
    mode: one
    selector: ...
```

---

## 6.5 Il Selettore

Il **selettore** determina quali Pod vengono colpiti dal chaos:

```yaml
selector:
  namespaces:
    - app                        # solo nel namespace "app"
  labelSelectors:
    app: backend                 # solo pod con label app=backend
  
  # Selettori aggiuntivi:
  pods:                          # pod specifici per nome
    app:
      - backend-7d9f8-abc
  
  podPhaseSelectors:
    - Running                    # solo pod in Running (default)
  
  annotationSelectors:
    experiment: "enabled"        # pod con questa annotation
```

### Modalità di Selezione (`mode`)

```yaml
mode: one        # 1 pod casuale
mode: all        # tutti i pod selezionati
mode: fixed      # numero fisso di pod
  value: "2"     # 2 pod
mode: fixed-percent  # percentuale fissa
  value: "50"    # 50% dei pod
mode: random-max-percent  # percentuale random
  value: "40"    # max 40% dei pod
```

---

## 6.6 Esempio Completo: NetworkChaos con Target

La risorsa più complessa è NetworkChaos con un target specifico — simula la partizione di rete tra due servizi:

```yaml
# chaos-experiments/03-network-partition.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: redis-network-partition
  namespace: chaos-mesh
spec:
  action: partition            # blocca tutto il traffico
  mode: all                    # da tutti i pod backend
  selector:
    namespaces: [app]
    labelSelectors:
      app: backend             # ← sorgente: backend
  direction: both              # traffico in entrambe le direzioni
  target:
    selector:
      namespaces: [app]
      labelSelectors:
        app.kubernetes.io/name: redis   # ← destinazione: redis
    mode: all
  duration: "2m"               # per 2 minuti poi ripristino automatico
```

Implementazione interna:

```
Chaos Mesh aggiunge regole iptables:
  INPUT  → DROP da redis-master-0
  OUTPUT → DROP verso redis-master-0

Effetto:
  Backend tenta TCP connect a redis:6379 → RST/timeout
  Backend: fallback attivato, va direttamente a PostgreSQL
  Redis: non riceve richieste, ma è ancora Running
```

---

## 6.7 La Dashboard

Chaos Mesh include una dashboard web accessibile tramite port-forward:

```bash
kubectl port-forward svc/chaos-dashboard -n chaos-mesh 2333:2333
# Apri http://localhost:2333
```

La dashboard permette di:
- **Creare esperimenti** tramite UI visuale (senza scrivere YAML)
- **Monitorare** gli esperimenti attivi in tempo reale
- **Visualizzare il grafo** delle dipendenze e dei chaos attivi
- **Schedulare** esperimenti ricorrenti
- **Creare Workflow** (sequenze di esperimenti)
- **Audit log** di tutti gli esperimenti eseguiti

---

## 6.8 Best Practice per gli Esperimenti

```
✓ Inizia con mode: one (un pod solo)
  Prima di mode: all

✓ Imposta sempre una duration
  Gli esperimenti devono avere un termine automatico

✓ Monitora in tempo reale
  Tieni Grafana aperto durante l'esperimento

✓ Definisci il steady state prima
  Senza baseline non puoi misurare l'impatto

✓ Documenta i risultati
  Ogni esperimento = ipotesi + risultato

✗ Non usare mode: all in produzione senza averlo
  testato prima con mode: one

✗ Non eseguire più esperimenti contemporaneamente
  (difficile isolare causa ed effetto)
```

---

## 6.9 Installazione nel Progetto

```bash
# Installazione corretta per K3s
helm install chaos-mesh chaos-mesh/chaos-mesh \
  --namespace chaos-mesh \
  --set chaosDaemon.runtime=containerd \
  --set chaosDaemon.socketPath=/run/k3s/containerd/containerd.sock \
  --set controllerManager.replicaCount=1 \
  --set dashboard.securityMode=false

# Il namespace app deve avere la label per il chaos injection
kubectl label namespace app chaos-mesh.org/inject=enabled
```

**Perché la configurazione specifica per K3s:**
- `chaosDaemon.runtime=containerd` → K3s non usa Docker
- `chaosDaemon.socketPath=...` → K3s ha il socket containerd in posizione non standard
- `controllerManager.replicaCount=1` → single-node, non serve HA
- `dashboard.securityMode=false` → demo, non produzione

---

## Riepilogo

| Aspetto | Dettaglio |
|---|---|
| **Cosa è** | Platform CNCF per Chaos Engineering su K8s |
| **Come funziona** | CRD + controller + daemon su ogni nodo |
| **Tipi principali** | PodChaos, NetworkChaos, StressChaos, IOChaos |
| **Configurazione** | YAML dichiarativo con selector e duration |
| **Scheduling** | Risorsa `Schedule` con cron syntax |
| **UI** | Dashboard web sulla porta 2333 |

**Prossima lezione →** [07 — L'Applicazione a Microservizi](07-applicazione.md)
