# 12 — Risultati e Conclusioni

## 12.1 Riepilogo degli Esperimenti

### Steady State del Sistema

Prima di ogni esperimento, il sistema si trova nello steady state:

```
✓ 3 pod backend Running (HPA minimo: 2)
✓ 2 pod frontend Running
✓ PostgreSQL e Redis operativi
✓ Error rate: 0%
✓ Latenza p95: ~10ms (con cache Redis)
✓ Latenza p95: ~50ms (senza cache, da DB)
✓ http://app.localhost/api/health → {"status":"ok"}
```

---

### Risultati per Esperimento

#### Esperimento 01 — Pod Failure ✅

| Metrica | Prima | Durante | Dopo |
|---|---|---|---|
| Pod attivi | 3 | 2 (per ~15s) | 3 |
| Error rate | 0% | 0% | 0% |
| Latenza p95 | ~10ms | ~15ms | ~10ms |
| Steady state | ✅ | ✅ mantenuto | ✅ |

**Conclusione:** K8s self-healing funziona come previsto. Il `replicaCount: 3` garantisce ridondanza sufficiente per assorbire il kill di 1 pod senza impatti visibili.

---

#### Esperimento 02 — Network Delay ✅

| Metrica | Prima | Durante | Dopo |
|---|---|---|---|
| Latenza p95 | ~10ms | ~600ms | ~10ms |
| Error rate | 0% | 0% | 0% |
| App funzionale | ✅ | ✅ (degraded) | ✅ |

**Conclusione:** L'applicazione gestisce correttamente la latenza di rete degradata. I timeout configurati su SQLAlchemy (`pool_pre_ping`, timeout connection) evitano che la latenza si propaghi in errori. Il sistema degrada in performance ma non in disponibilità.

---

#### Esperimento 03 — Network Partition ✅

| Metrica | Prima | Durante | Dopo |
|---|---|---|---|
| Cache hit | ~100% | 0% (tutti miss) | ~100% |
| Latenza p95 | ~10ms | ~60ms | ~10ms |
| Error rate | 0% | 0% | 0% |
| Fallback attivo | No | Sì | No |

**Conclusione:** Il pattern di **graceful degradation** implementato in `cache.py` ha funzionato perfettamente. Redis irraggiungibile non causa errori — il backend cade automaticamente in fallback su PostgreSQL con overhead di ~50ms. Il `socket_connect_timeout=1s` evita attese lunghe.

---

#### Esperimento 04 — CPU Stress ✅

| Metrica | Prima | Durante | Dopo |
|---|---|---|---|
| CPU media pod | ~15% | ~80% | ~15% |
| Repliche | 3 | 4-5 (HPA) | 2 (min) |
| Latenza p95 | ~10ms | ~12ms | ~10ms |
| Error rate | 0% | 0% | 0% |

**Conclusione:** L'HPA ha scalato da 3 a 4 repliche entro ~60 secondi dal superamento della soglia del 70%. La latenza è rimasta stabile perché le nuove repliche hanno assorbito il carico. Dopo la fine dello stress, lo scale-down è avvenuto nel periodo di cooldown di default (5 minuti).

---

#### Esperimento 05 — Pod Cascading ✅

| Metrica | Valore |
|---|---|
| Frequenza kill | 1 pod ogni 20s |
| Minimo pod simultanei | 2 (mai 0) |
| Error rate medio | ~0.1% (spike brevissimi durante kill) |
| Recovery time | ~15s per pod |

**Conclusione:** Con recovery time ~15s e kill ogni 20s, il sistema mantiene sempre almeno 2 repliche attive. I brevissimi spike di errore (durante il transition da 2 a 3 pod) sono accettabili e rientrano nella soglia dell'1% definita nello steady state.

---

## 12.2 Analisi Complessiva

### Il Sistema ha Superato tutti i Test

```
┌────────────────────────────────────────────────────────────────┐
│                   Scorecard di Resilienza                      │
│                                                                │
│  Self-healing (K8s)              ████████████████████ ✅ 100%  │
│  Graceful degradation (Redis)    ████████████████████ ✅ 100%  │
│  Autoscaling (HPA)               ████████████████████ ✅ 100%  │
│  Resistenza a latenza di rete    ████████████████████ ✅ 100%  │
│  Resistenza a stress continuo    ██████████████████░░ ✅  90%  │
│                                  (spike 0.1% errori)          │
│                                                                │
│  Overall Resilience Score:       ████████████████████ ✅  98%  │
└────────────────────────────────────────────────────────────────┘
```

### Pattern di Resilienza Verificati

| Pattern | Dove | Risultato |
|---|---|---|
| **Redundancy** | 3 pod backend, 2 frontend | Assorbimento di singoli failure |
| **Self-healing** | K8s ReplicaSet controller | Pod ricreati automaticamente |
| **Graceful degradation** | Cache fallback su DB | Zero errori con Redis down |
| **Circuit breaker** implicito | Redis timeout 1s | No cascading failure |
| **Horizontal scaling** | HPA 2-6 repliche | Risposta automatica al carico |
| **Health probes** | Liveness + Readiness | No traffico su pod non pronti |

---

## 12.3 Lezioni Apprese

### ✅ Cosa ha funzionato bene

**1. Il modello dichiarativo di Kubernetes**  
Definire lo stato desiderato (`replicas: 3`) e lasciare che K8s lo mantenga è estremamente efficace. Non serve scrivere script di monitoring e restart — il sistema si autogestisce.

**2. Il fallback Redis con timeout breve**  
Impostare `socket_connect_timeout=1s` e restituire `None` invece di sollevare un'eccezione è la scelta giusta. Un timeout di 5-10 secondi avrebbe reso l'esperimento 03 molto più impattante per gli utenti.

**3. Le probe di liveness e readiness**  
La `readinessProbe` su `/api/health` garantisce che K8s non indirizzi traffico a un pod non ancora pronto. Senza di essa, l'esperimento 01 avrebbe generato errori durante i primissimi secondi del nuovo pod.

**4. Le risorse (requests/limits) correttamente dimensionate**  
Senza `resources.requests`, l'HPA non avrebbe metriche su cui basare lo scaling. Senza `resources.limits`, un pod con CPU runaway potrebbe affamare gli altri.

### ⚠️ Punti di Attenzione

**1. Single point of failure: PostgreSQL**  
Nel progetto PostgreSQL ha 1 sola replica. Un guasto al database abbatterebbe tutto il servizio. In produzione si usa:
- PostgreSQL con replica di standby (Patroni)
- Multi-AZ su cloud (RDS Multi-AZ)
- PgBouncer come connection pooler

**2. HPA e metrics-server latency**  
L'HPA campiona le metriche ogni 15 secondi e richiede 2 campioni consecutivi sopra soglia prima di agire. In totale ~30-60 secondi prima dello scale-up. Per applicazioni con spike improvvisi, si usa **KEDA** (event-driven autoscaling).

**3. Scale-down aggressivo**  
Il cooldown di default dell'HPA (5 minuti per lo scale-down) protegge da flapping ma rallenta il ritorno al minimo. Configurabile con `--horizontal-pod-autoscaler-downscale-stabilization`.

**4. Chaos Mesh su K3s**  
L'installazione di Chaos Mesh su K3s richiede configurazione specifica (`socketPath`, `replicaCount=1`). In un cluster multi-node in produzione, l'installazione è più semplice e il chaos-daemon gira su tutti i nodi automaticamente.

---

## 12.4 Confronto con le Fallacies del Distributed Computing

Al termine del progetto, possiamo verificare le 8 fallacies contro i nostri esperimenti:

| Fallacy | Esperimento | Sistema tiene? |
|---|---|---|
| "La rete è affidabile" | Exp 02 (delay), Exp 03 (partition) | ✅ Sì |
| "La latenza è zero" | Exp 02 (500ms di delay) | ✅ Sì |
| "I componenti non falliscono" | Exp 01, Exp 05 (pod kill) | ✅ Sì |
| "La banda è infinita" | Parzialmente testato con CPU stress | ✅ Sì |
| "La topologia non cambia" | HPA (nuovi pod, nuovi IP) | ✅ Sì (grazie a Service) |

---

## 12.5 Estensioni Possibili

### Livello Avanzato

**1. Esperimento: Memory Stress**
```yaml
kind: StressChaos
spec:
  stressors:
    memory:
      workers: 1
      size: "400MB"   # forza OOMKill se supera il limit
```

**2. Esperimento: Database Failure**
```yaml
kind: PodChaos
spec:
  action: pod-kill
  selector:
    labelSelectors:
      app.kubernetes.io/name: postgresql
```
*Verificherebbe la risposta del backend con DB completamente irraggiungibile.*

**3. Chaos in CI/CD**
Integrare gli esperimenti nella pipeline GitHub Actions:
```yaml
# .github/workflows/chaos.yml
- name: Run chaos experiments
  run: |
    kubectl apply -f chaos-experiments/01-pod-failure.yaml
    sleep 60
    # verifica metriche via Prometheus API
    ERROR_RATE=$(curl -s prometheus:9090/api/v1/query?query=... | jq '.data.result[0].value[1]')
    [ "$ERROR_RATE" -lt "0.01" ] || exit 1
```

**4. Workflow Sequenziale**
Chaos Mesh supporta `Workflow` per sequenziare esperimenti:
```yaml
kind: Workflow
spec:
  entry: pod-failure
  templates:
  - name: pod-failure
    deadline: 30s
    children: [network-delay]
  - name: network-delay
    deadline: 2m
    children: [cpu-stress]
  - name: cpu-stress
    deadline: 3m
```

---

## 12.6 Architettura Target per la Produzione

```
┌────────────────────────────────────────────────────────────────┐
│                 Evoluzione verso la Produzione                 │
│                                                                │
│  Dev (questo progetto)          Produzione                     │
│  ──────────────────────         ─────────────────────────      │
│  K3s single-node          →     K8s multi-node (3+ master)     │
│  SQLite (K3s etcd)         →     etcd cluster (3 nodi)         │
│  PostgreSQL 1 replica      →     PostgreSQL HA (Patroni)       │
│  Redis standalone          →     Redis Sentinel/Cluster        │
│  Immagini locali           →     Container Registry (GHCR)     │
│  Traefik                   →     Traefik / Istio (service mesh)│
│  No TLS                    →     cert-manager + Let's Encrypt   │
│  Chaos manuale             →     Chaos in CI/CD automatizzato   │
│  Grafana alert manuale     →     PagerDuty / OpsGenie          │
└────────────────────────────────────────────────────────────────┘
```

---

## 12.7 Conclusioni

Il progetto ha dimostrato che un'architettura a microservizi su Kubernetes, progettata con i principi di resilienza in mente, può resistere a un'ampia gamma di guasti senza impatti significativi sugli utenti.

**I tre ingredienti fondamentali della resilienza osservati:**

```
1. RIDONDANZA
   → Multiple repliche bilanciate dal load balancer
   → Nessun single point of failure (eccetto DB)

2. SELF-HEALING
   → Kubernetes riporta sempre allo stato desiderato
   → Nessun intervento manuale necessario

3. GRACEFUL DEGRADATION
   → Il sistema funziona anche senza Redis
   → Fallback trasparente per l'utente finale
```

Il Chaos Engineering non è "rompere cose per divertimento" — è una disciplina scientifica che costruisce **fiducia misurabile** nella resilienza del sistema. La differenza tra un sistema che "speriamo regga" e uno che "sappiamo che regge" è esattamente questa: esperimenti, metriche, evidenza.

> *"The best way to avoid failure is to fail constantly."* — Netflix Engineering

---

## Riferimenti

- [Kubernetes Documentation](https://kubernetes.io/docs/)
- [Helm Documentation](https://helm.sh/docs/)
- [Chaos Mesh Documentation](https://chaos-mesh.org/docs/)
- [Principles of Chaos Engineering](https://principlesofchaos.org/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [K3s Documentation](https://docs.k3s.io/)
- [Bitnami Helm Charts](https://charts.bitnami.com/)

---

*← [11 — I 5 Esperimenti di Chaos](11-esperimenti-chaos.md) | [Torna all'Indice](00-indice.md)*
