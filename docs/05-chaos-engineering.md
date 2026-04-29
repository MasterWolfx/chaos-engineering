# 05 — Principi del Chaos Engineering

## 5.1 La Domanda Fondamentale

> *"Il vostro sistema è davvero resiliente, o lo credete soltanto?"*

I sistemi distribuiti moderni sono intrinsecamente complessi. Decine di microservizi, database, cache, bilanciatori di carico, reti — tutto deve funzionare in armonia. Ma come si **verifica** la resilienza prima che lo faccia un guasto reale in produzione?

La risposta è il **Chaos Engineering**: la disciplina di sperimentare su un sistema in produzione (o che la simula) per costruire fiducia nella sua capacità di resistere a condizioni turbolente.

---

## 5.2 Storia e Origine

### Netflix e il Grande Blackout del 2008

Il 3 agosto 2008, un bug nel database di Netflix causò **3 giorni di downtime** completo. Tutto il servizio fu irraggiungibile per milioni di utenti.

Dopo quell'evento, Netflix iniziò una trasformazione radicale:
1. Migrazione da data center propri ad AWS
2. Adozione di un'architettura a microservizi
3. Sviluppo di strumenti di resilienza

### Chaos Monkey (2011)

Netflix creò **Chaos Monkey**: un tool che **termina casualmente istanze** in produzione durante le ore lavorative.

```
Filosofia Netflix:
"Se le macchine si rompono in produzione (e lo fanno),
 vogliamo scoprirlo durante l'orario di lavoro
 quando tutto il team è disponibile a reagire,
 non alle 3 di notte."
```

Chaos Monkey era parte della **Simian Army**:

| Tool | Chaos Introdotto |
|---|---|
| Chaos Monkey | Termina istanze random |
| Chaos Gorilla | Termina un'intera availability zone AWS |
| Chaos Kong | Simula il fallimento di un'intera region AWS |
| Latency Monkey | Introduce latenza artificiale |
| Doctor Monkey | Controlla la salute dei servizi |
| Janitor Monkey | Pulizia risorse inutilizzate |

### L'Evoluzione: Principi del Chaos Engineering (2014)

Nel 2014, il team di Netflix formalizzò i **Principles of Chaos Engineering** (principlesofchaos.org), che ancora oggi guidano la disciplina.

---

## 5.3 I 5 Principi del Chaos Engineering

### Principio 1: Definire il "Steady State"

Il **steady state** è il comportamento normale del sistema, misurabile tramite metriche.

```
Steady State del nostro progetto:
┌────────────────────────────────────────────────┐
│  ✓ Almeno 2 pod backend Running                │
│  ✓ Error rate (5xx) < 1%                       │
│  ✓ Latenza p95 < 200ms                         │
│  ✓ API /api/items risponde con 200             │
│  ✓ Dati persistenti in PostgreSQL              │
└────────────────────────────────────────────────┘
```

Senza una definizione chiara dello steady state, non si può sapere se il chaos ha avuto impatto.

### Principio 2: Formulare un'Ipotesi

Ogni esperimento parte da un'ipotesi testabile:

```
Esperimento: "Cosa succede se uccido un pod del backend?"

Ipotesi: "Kubernetes riavvierà il pod entro 30 secondi.
          Le altre repliche continueranno a servire traffico.
          L'error rate rimarrà < 1% durante il recovery."

Verifica: misuro error rate e latenza durante e dopo il kill.
```

### Principio 3: Variare le Condizioni del Mondo Reale

I guasti devono simulare scenari realistici, non inventati. Esempi comuni:

```
Hardware:    ● Crash di server
             ● Disco pieno
             ● Spike di CPU

Rete:        ● Latenza elevata (rete trafficata)
             ● Perdita di pacchetti
             ● Partizionamento (split-brain)

Software:    ● Memory leak → OOMKill
             ● Deadlock → timeout
             ● Bug in dependency → eccezione non gestita

Dipendenze:  ● Database non raggiungibile
             ● Cache vuota (cold start)
             ● API esterna timeout
```

### Principio 4: Eseguire Esperimenti in Produzione

Il chaos in staging non conta abbastanza: il traffico reale, il volume di dati e le interazioni sono diversi. Il vero test è in produzione.

```
Sicurezza prima:
┌─────────────────────────────────────────────────┐
│  1. Inizia piccolo (1 pod, non tutti)           │
│  2. Aumenta gradualmente il raggio d'azione     │
│  3. Monitora attivamente durante l'esperimento  │
│  4. Hai sempre un "abort button" pronto         │
│  5. Non farlo durante peak traffic              │
└─────────────────────────────────────────────────┘
```

### Principio 5: Automatizzare gli Esperimenti

Il chaos manuale è utile all'inizio ma non scala. L'obiettivo è l'esecuzione continua:

```
Pipeline CI/CD:
  build → test unitari → integration tests → chaos tests → deploy
                                                ↑
                                    Chaos Engineering automatizzato
```

---

## 5.4 Perché il Chaos Engineering è Importante

### Le 8 Fallacies del Distributed Computing

Peter Deutsch (Sun Microsystems, 1994) elencò le **8 false assunzioni** che gli sviluppatori fanno sui sistemi distribuiti:

```
1. ❌ "La rete è affidabile"
2. ❌ "La latenza è zero"
3. ❌ "La banda è infinita"
4. ❌ "La rete è sicura"
5. ❌ "La topologia non cambia"
6. ❌ "C'è un solo amministratore"
7. ❌ "Il costo del trasporto è zero"
8. ❌ "La rete è omogenea"
```

Il Chaos Engineering **forza il sistema a dimostrare** che queste assunzioni non impattano la disponibilità.

### Il Costo del Downtime

| Azienda | Costo stimato per ora di downtime |
|---|---|
| Amazon | ~$34 milioni |
| Google | ~$5.6 milioni |
| Netflix | ~$0 (grazie al chaos engineering!) |
| Banca media | ~$3 milioni |

---

## 5.5 Il Processo di un Esperimento

```
┌─────────────────────────────────────────────────────────────┐
│                  Ciclo di Chaos Engineering                 │
│                                                             │
│   1. OBSERVE          Misura il steady state attuale        │
│         │                                                   │
│         ▼                                                   │
│   2. HYPOTHESIZE      "Se faccio X, il sistema Y"          │
│         │                                                   │
│         ▼                                                   │
│   3. INJECT           Introduci il guasto controllato       │
│         │                                                   │
│         ▼                                                   │
│   4. MEASURE          Osserva metriche durante il chaos     │
│         │                                                   │
│         ▼                                                   │
│   5. ANALYZE          Lo steady state è stato mantenuto?   │
│         │                                                   │
│         ├── SÌ → il sistema è resiliente a questo guasto   │
│         │        Aumenta la portata dell'esperimento        │
│         │                                                   │
│         └── NO → hai trovato una WEAKNESS                  │
│                  Correggi e ripeti                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 5.6 GameDay

Un **GameDay** è una sessione strutturata in cui il team esegue esperimenti di chaos e gestisce gli incidenti in un ambiente controllato.

```
Struttura tipica di un GameDay:
┌──────────────────────────────────────────────────────┐
│  9:00  — Briefing: scenari da testare oggi           │
│  9:30  — Esperimento 1: Pod failure                  │
│ 10:00  — Post-mortem intermedio                      │
│ 10:30  — Esperimento 2: Network partition            │
│ 11:00  — Esperimento 3: CPU stress                   │
│ 12:00  — Pausa                                       │
│ 13:00  — Review metriche Grafana                     │
│ 14:00  — Retrospettiva: cosa ha retto, cosa no       │
│ 15:00  — Piano di remediation                        │
└──────────────────────────────────────────────────────┘
```

---

## 5.7 Chaos Engineering vs Testing Tradizionale

```
Test tradizionale:            Chaos Engineering:
"Il sistema fa quello         "Il sistema regge quando
 che dovrebbe fare?"           le cose vanno storte?"

Unit test                     Fault injection
Integration test              Game days
Load test                     Continuous chaos
E2E test                      Production experiments

Ambiente: dev/staging         Ambiente: produzione
Guasti: previsti dal dev      Guasti: scenari realistici
Frequenza: pre-deploy         Frequenza: continua
```

---

## 5.8 Maturità del Chaos Engineering

Il **Chaos Maturity Model** (da Gremlin):

```
Livello 1 — Chaos Infante
  • Nessun chaos engineering
  • I guasti vengono scoperti dai clienti

Livello 2 — Chaos Consapevole
  • Test manuali occasionali in staging
  • Chaos Monkey di base

Livello 3 — Chaos Strutturato
  • GameDay regolari
  • Esperimenti documentati e ripetibili
  • Steady state definito                ← noi siamo qui

Livello 4 — Chaos Automatizzato
  • CI/CD con chaos integrato
  • Esperimenti in produzione automatici

Livello 5 — Chaos Proattivo
  • Chaos come cultura aziendale
  • Ogni team ha il proprio piano di resilienza
  • Chaos come prerequisito al deploy
```

---

## Riepilogo

- Il Chaos Engineering nasce da Netflix dopo un blackout da 3 giorni
- Si basa su esperimenti scientifici controllati, non vandalismo
- Il **steady state** è il punto di riferimento: se il sistema lo mantiene durante il chaos, è resiliente
- I 5 principi guidano ogni esperimento: steady state → ipotesi → iniezione → misura → analisi
- Le 8 fallacies ricordano che i sistemi distribuiti sono sempre più fragili di quanto sembri

**Prossima lezione →** [06 — Chaos Mesh](06-chaos-mesh.md)
