# 11 — I 5 Esperimenti di Chaos

## Panoramica

| # | Nome | Tipo | Target | Durata | Steady State Atteso |
|---|---|---|---|---|---|
| 01 | Pod Failure | PodChaos | 1 pod backend | 30s | K8s riavvia entro 30s, nessun 5xx |
| 02 | Network Delay | NetworkChaos | backend→PostgreSQL | 2 min | Latenza alta, nessun errore |
| 03 | Network Partition | NetworkChaos | backend↔Redis | 2 min | Fallback su DB, nessun 5xx |
| 04 | CPU Stress | StressChaos | tutti i backend | 3 min | HPA scala nuove repliche |
| 05 | Pod Cascading | Schedule | 1 pod ogni 20s | ricorrente | K8s riavvia continuamente |

---

## Esperimento 01 — Pod Failure

### Obiettivo

Verificare che Kubernetes rilevi automaticamente un pod terminato e ne crei uno nuovo (**self-healing**), mantenendo il servizio disponibile grazie alle altre repliche.

### Configurazione

```yaml
# chaos-experiments/01-pod-failure.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: backend-pod-failure
  namespace: chaos-mesh
spec:
  action: pod-kill          # termina brutalmente il pod (SIGKILL)
  mode: one                 # colpisce 1 pod casuale
  selector:
    namespaces: [app]
    labelSelectors:
      app: backend
  duration: "30s"
```

### Ipotesi

> "Se un pod del backend viene ucciso, Kubernetes creerà un nuovo pod entro 30 secondi. Le 2 repliche rimanenti continueranno a servire traffico senza errori 5xx visibili."

### Esecuzione

```bash
# Osserva i pod in tempo reale
watch kubectl get pods -n app

# Applica l'esperimento
kubectl apply -f chaos-experiments/01-pod-failure.yaml

# Monitora l'esperimento
kubectl get podchaos -n chaos-mesh
```

### Sequenza degli eventi

```
t=0s   Chaos Mesh invia SIGKILL al pod backend-7d9f8b-abc
t=1s   Pod entra in stato Terminating
t=2s   Pod eliminato dal cluster
t=3s   ReplicaSet Controller rileva: attuale=2, desiderato=3
t=3s   Scheduler assegna nuovo pod al nodo
t=5s   Container Runtime scarica/avvia l'immagine
t=10s  Pod in Running, initialDelaySeconds=5 → readiness probe
t=15s  Pod supera readiness probe → riceve traffico
t=30s  Sistema completamente ripristinato
```

### Cosa Osservare in Grafana

```
Pod Attivi:
│ 3 ────────╮        ╭──── 3
│ 2         ╰────────╯
└──────────────────────────→ tempo
    t=0      t=2     t=15

Error Rate:
│ 0% ─────────────────────── 0%
│ (nessun 5xx visibile)
```

### Risultato Atteso

✅ Il pod count scende da 3 a 2 per ~15 secondi, poi torna a 3.  
✅ L'error rate rimane 0% grazie alle altre 2 repliche.  
✅ Lo steady state è mantenuto.

### Cleanup

```bash
kubectl delete -f chaos-experiments/01-pod-failure.yaml
```

---

## Esperimento 02 — Network Delay

### Obiettivo

Simulare una rete congestionata o un database lento introducendo latenza artificiale sul traffico dal backend verso PostgreSQL.

### Configurazione

```yaml
# chaos-experiments/02-network-delay.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: db-network-delay
  namespace: chaos-mesh
spec:
  action: delay
  mode: all                  # tutti i pod backend
  selector:
    namespaces: [app]
    labelSelectors:
      app: backend
  delay:
    latency: "500ms"         # latenza base
    correlation: "25"        # 25% di correlazione tra pacchetti
    jitter: "100ms"          # ±100ms di variazione casuale
  direction: to              # solo traffico in uscita dal backend
  target:
    selector:
      namespaces: [app]
      labelSelectors:
        app.kubernetes.io/name: postgresql
    mode: all
  duration: "2m"             # termina automaticamente dopo 2 minuti
```

### Ipotesi

> "Ogni query SQL richiederà ~500ms in più. La latenza p95 dell'API salirà da ~10ms a ~600ms. Il sistema rimane funzionale con performance degradate — nessun errore 5xx."

### Meccanismo Tecnico

Chaos Mesh usa `tc` (Traffic Control) con il modulo `netem` del kernel Linux:

```bash
# Cosa Chaos Mesh esegue internamente sul nodo
tc qdisc add dev eth0 root netem delay 500ms 100ms 25%
```

### Cosa Osservare

```bash
# Testa la latenza durante il chaos
for i in {1..5}; do
  curl -o /dev/null -s -w "Response: %{time_total}s\n" http://app.localhost/api/items
done
```

```
Latenza p95 in Grafana:
│ 600ms ────────────────────────────╮          ╭── back to 10ms
│ 400ms                             │          │
│ 200ms                             │          │
│  10ms ───────────────────────────╯╰──────────╯
└──────────────────────────────────────────────→
       t=0 (delay ON)              t=2min (delay OFF)
```

### Nota sul Jitter

Il parametro `jitter: "100ms"` simula la variabilità reale della rete. La latenza effettiva di ogni pacchetto sarà tra 400ms e 600ms, con una distribuzione non uniforme (parametro `correlation: "25"` introduce correlazione temporale tra pacchetti consecutivi, simulando burst di congestione).

### Risultato Atteso

✅ Latenza API aumenta significativamente durante l'esperimento.  
✅ Nessun errore 5xx — l'app funziona, solo più lentamente.  
✅ Alla fine dei 2 minuti, la latenza torna ai valori normali.

### Cleanup

```bash
kubectl delete -f chaos-experiments/02-network-delay.yaml
```

---

## Esperimento 03 — Network Partition

### Obiettivo

Simulare un'interruzione completa della comunicazione tra backend e Redis. Verifica che il meccanismo di **graceful degradation** (fallback su PostgreSQL) funzioni correttamente.

### Configurazione

```yaml
# chaos-experiments/03-network-partition.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: redis-network-partition
  namespace: chaos-mesh
spec:
  action: partition          # blocco totale del traffico
  mode: all
  selector:
    namespaces: [app]
    labelSelectors:
      app: backend           # sorgente: tutti i pod backend
  direction: both            # bidirezionale
  target:
    selector:
      namespaces: [app]
      labelSelectors:
        app.kubernetes.io/name: redis    # destinazione: Redis
    mode: all
  duration: "2m"
```

### Ipotesi

> "Con Redis irraggiungibile, tutte le richieste risulteranno in cache miss. Il backend utilizzerà il fallback su PostgreSQL. L'error rate rimane 0%, la latenza aumenta leggermente (cache miss overhead)."

### Il Codice di Fallback

```python
# backend/app/cache.py
async def get_redis():
    try:
        client = redis.from_url(REDIS_URL, socket_connect_timeout=1)
        await client.ping()
        return client
    except Exception:
        return None   # ← Redis non raggiungibile: ritorna None

async def cache_get(key: str) -> str | None:
    client = await get_redis()
    if client is None:
        return None   # ← None = cache miss, il chiamante andrà al DB
    ...
```

### Sequenza degli eventi

```
Richiesta GET /api/items con partizione attiva:

1. cache_get("items:all") → None (Redis irraggiungibile)
2. Cache miss → query su PostgreSQL
3. Risposta al client con dati da DB
4. cache_set() → fallisce silenziosamente (nessun errore)

Ogni richiesta va direttamente al DB, ma nessun 5xx.
```

### Differenza tra Partizione e Guasto Redis

```
Redis POD DOWN:        Il pod non esiste → DNS lookup fallisce
Redis PARTITION:       Il pod esiste ma è irraggiungibile → TCP timeout

Chaos Mesh simula la partition (scenario più realistico):
  iptables: DROP tutti i pacchetti verso redis-master-0
```

### Cosa Osservare

```
Durante la partizione:
  • Backend logs: "Redis connection timeout" (ogni richiesta)
  • Latenza: leggermente più alta (TCP timeout 1s + DB query)
  • Error rate: 0% ← il fallback funziona

Verifica manuale:
  curl http://app.localhost/api/items
  # Risponde correttamente, più lentamente
```

### Risultato Atteso

✅ Zero errori 5xx durante la partizione.  
✅ Il fallback su PostgreSQL è trasparente per il client.  
✅ Redis torna operativo automaticamente alla fine dei 2 minuti.

### Cleanup

```bash
kubectl delete -f chaos-experiments/03-network-partition.yaml
```

---

## Esperimento 04 — CPU Stress

### Obiettivo

Generare carico CPU artificiale su tutti i pod del backend per verificare che l'**HPA** (HorizontalPodAutoscaler) rilevi l'aumento e scala automaticamente nuove repliche.

### Configurazione

```yaml
# chaos-experiments/04-cpu-stress.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: backend-cpu-stress
  namespace: chaos-mesh
spec:
  mode: all                  # tutti i pod backend
  selector:
    namespaces: [app]
    labelSelectors:
      app: backend
  stressors:
    cpu:
      workers: 2             # 2 thread che stressano la CPU
      load: 80               # target 80% di utilizzo CPU
  duration: "3m"
```

### Ipotesi

> "Con tutti i pod backend al 80% di CPU, l'HPA rileva il superamento della soglia del 70% e scala da 3 a 4-5 repliche. La latenza rimane stabile grazie alle nuove repliche."

### Come Funziona lo Stress

```
Chaos Mesh lancia internamente nel container:
  stress-ng --cpu 2 --cpu-load 80

Effetto:
  2 thread consumano ciclicamente CPU
  → container CPU usage: ~80%
  → HPA: current=80% > target=70% → scala!
```

### Formula dell'HPA

```
desired_replicas = ceil(current_replicas × current_cpu / target_cpu)
                 = ceil(3 × 80% / 70%)
                 = ceil(3 × 1.14)
                 = ceil(3.43)
                 = 4
```

### Sequenza degli eventi

```
t=0     Stress ON: tutti i pod al 80% CPU
t=15s   HPA prima rilevazione: 80% > 70%
t=30s   HPA seconda rilevazione (conferma)
t=60s   HPA scala: 3 → 4 repliche
t=90s   Nuovo pod Running, carico si distribuisce
t=120s  CPU per pod scende: 80% × 3/4 = 60%
t=180s  Fine stress (3 minuti)
t=300s  HPA attende periodo di cooldown
t=600s  HPA scala down: 4 → 3 → 2 repliche (minimo)
```

### Cosa Osservare

```bash
# Monitora HPA in tempo reale
kubectl get hpa -n app --watch
# NAME          REFERENCE             TARGETS    REPLICAS
# backend-hpa   Deployment/backend    15%/70%    3
# backend-hpa   Deployment/backend    80%/70%    3    ← stress ON
# backend-hpa   Deployment/backend    80%/70%    4    ← HPA scala!
# backend-hpa   Deployment/backend    62%/70%    4    ← distribuito
```

```
CPU Usage in Grafana:
│ 80% ────────────╮              ╭── scale down
│ 60%             ╰────────────╮ │
│ 15% ────────────              ╰─╯
└────────────────────────────────────→ tempo
     t=0    stress   t=3min   cooldown

Pod Attivi:
│ 4 ────────────────────────────╮
│ 3 ─────────╮                  ╰────────────╮
│ 2                                           ╰── min
```

### Risultato Atteso

✅ HPA scala da 3 a 4+ repliche entro 60-90 secondi.  
✅ La latenza rimane stabile nonostante lo stress CPU.  
✅ Dopo la fine dello stress, le repliche tornano al minimo.

### Cleanup

```bash
kubectl delete -f chaos-experiments/04-cpu-stress.yaml
```

---

## Esperimento 05 — Pod Failure Cascading

### Obiettivo

Simulare un fallimento continuo e ricorrente dei pod del backend — lo scenario più aggressivo. Verifica che il sistema rimanga disponibile anche con pod che vengono abbattuti ripetutamente.

### Configurazione

```yaml
# chaos-experiments/05-pod-failure-cascading.yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: Schedule
metadata:
  name: backend-cascading-failure
  namespace: chaos-mesh
spec:
  schedule: "@every 20s"       # ogni 20 secondi
  historyLimit: 2              # mantieni solo 2 esecuzioni in storico
  concurrencyPolicy: Forbid    # non sovrapporre esecuzioni
  type: PodChaos
  podChaos:
    action: pod-kill
    mode: one                  # 1 pod casuale ogni 20s
    selector:
      namespaces: [app]
      labelSelectors:
        app: backend
```

### Ipotesi

> "Con pod eliminati ogni 20 secondi, il deployment mantiene sempre almeno 1-2 repliche attive grazie al rapid recovery di Kubernetes. Il servizio rimane disponibile con possibili brevi spike di latenza."

### Analisi della Temporizzazione

```
Con 3 repliche e recovery time ~15s:

t=0s    Kill pod-1. Repliche: [pod-2][pod-3][new-pod starting]
t=15s   new-pod ready. Repliche: [pod-2][pod-3][pod-4]
t=20s   Kill pod-2. Repliche: [pod-3][pod-4][new-pod starting]
t=35s   new-pod ready. Repliche: [pod-3][pod-4][pod-5]
t=40s   Kill pod-3. ...

Sempre almeno 2 repliche attive → servizio disponibile!
```

### Differenza da Esperimento 01

| | Esperimento 01 | Esperimento 05 |
|---|---|---|
| Tipo | PodChaos singolo | Schedule ricorrente |
| Frequenza | 1 volta | ogni 20 secondi |
| Durata | 30 secondi | fino al delete manuale |
| Scopo | Verifica self-healing | Verifica resilienza continua |

### ⚠️ Importante: Stop Manuale

L'esperimento 05 non termina automaticamente — usa `Schedule` ricorrente:

```bash
# Per fermare l'esperimento
kubectl delete -f chaos-experiments/05-pod-failure-cascading.yaml

# Oppure
kubectl delete schedule backend-cascading-failure -n chaos-mesh
```

### Cosa Osservare

```bash
# Guarda i pod morire e rinascere in loop
kubectl get pods -n app --watch
# NAME                  READY   STATUS        RESTARTS
# backend-7d9f8-abc     1/1     Running       0
# backend-7d9f8-abc     0/1     Terminating   0
# backend-7d9f8-def     0/1     Pending       0
# backend-7d9f8-def     1/1     Running       0
# backend-7d9f8-ghi     0/1     Terminating   0  ← 20s dopo
```

### Risultato Atteso

✅ Il cluster mantiene sempre almeno 2 pod in Running.  
✅ Il servizio risponde anche durante i kill.  
✅ L'error rate potrebbe avere brevi spike durante il pod kill.

---

## Confronto dei 5 Esperimenti

```
┌────────────────────────────────────────────────────────────────┐
│           Impatto sul Sistema (1=basso, 5=alto)                │
│                                                                │
│  Exp 01 Pod Failure      ████░░░░░░  2/5  (1 pod, 30s)        │
│  Exp 02 Network Delay    ██████░░░░  3/5  (latenza 500ms)     │
│  Exp 03 Net Partition    ████████░░  4/5  (cache completamente │
│                                            isolata)           │
│  Exp 04 CPU Stress       ██████████  5/5  (tutti pod al 80%)  │
│  Exp 05 Cascading        █████████░  4/5  (ricorrente ogni    │
│                                            20s)               │
└────────────────────────────────────────────────────────────────┘
```

**Prossima lezione →** [12 — Risultati e Conclusioni](12-conclusioni.md)
