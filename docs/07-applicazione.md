# 07 - L'Applicazione a Microservizi

## 7.1 Panoramica dell'Architettura

Il progetto implementa un'applicazione CRUD (Create, Read, Update, Delete) per la gestione di oggetti "Item", progettata per essere **testata con il Chaos Engineering**.

```
                         Internet / Host
                              │
                              ▼
                    ┌─────────────────┐
                    │  Traefik Ingress │
                    │  app.localhost   │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
              ▼ /                           ▼ /api/
    ┌──────────────────┐          ┌──────────────────┐
    │    Frontend       │          │    Backend        │
    │    (Nginx)        │          │    (FastAPI)      │
    │    2 repliche     │          │    3 repliche     │
    └──────────────────┘          └────────┬──────────┘
                                           │
                              ┌────────────┴────────────┐
                              │                         │
                              ▼                         ▼
                    ┌──────────────────┐    ┌──────────────────┐
                    │   PostgreSQL     │    │   Redis Cache    │
                    │   (StatefulSet)  │    │   (StatefulSet)  │
                    │   Persistente    │    │   Volatile       │
                    └──────────────────┘    └──────────────────┘
```

### Perché questa architettura per il chaos testing?

Ogni componente introduce un potenziale punto di failure:
- **Frontend → Backend:** HTTP, può avere latenza
- **Backend → PostgreSQL:** TCP, può disconnettersi
- **Backend → Redis:** TCP, gestito con fallback

---

## 7.2 Il Backend (FastAPI)

**FastAPI** è un framework Python moderno per la creazione di API REST ad alte prestazioni, basato su asyncio.

### Struttura del Codice

```
backend/
├── app/
│   ├── main.py       ← endpoint REST + lifespan
│   ├── database.py   ← connessione PostgreSQL (asyncpg)
│   ├── cache.py      ← client Redis con fallback
│   └── models.py     ← modelli Pydantic
├── Dockerfile
└── requirements.txt
```

### `main.py` - Gli Endpoint

```python
# backend/app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
from .database import init_db, get_db
from .cache import cache_get, cache_set, cache_delete
import json

# ── Modelli ──────────────────────────────────────────────────
class ItemCreate(BaseModel):
    name: str
    description: str | None = None

class Item(ItemCreate):
    id: int
    class Config:
        from_attributes = True

# ── Lifespan: init DB all'avvio ───────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()          # crea tabella items se non esiste
    yield
    # cleanup (se necessario)

app = FastAPI(title="Chaos Demo API", lifespan=lifespan)

# ── Prometheus metrics ────────────────────────────────────────
Instrumentator().instrument(app).expose(app)

# ── Health check ──────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"status": "ok"}

# ── CRUD Items ────────────────────────────────────────────────
@app.get("/api/items")
async def get_items():
    # 1. Prova dalla cache Redis
    cached = await cache_get("items:all")
    if cached:
        return json.loads(cached)
    
    # 2. Cache miss → leggi da PostgreSQL
    async with get_db() as db:
        result = await db.execute("SELECT id, name, description FROM items")
        items = [dict(r) for r in result.fetchall()]
    
    # 3. Scrivi in cache (TTL 30s)
    await cache_set("items:all", json.dumps(items), ttl=30)
    return items

@app.post("/api/items", status_code=201)
async def create_item(item: ItemCreate):
    async with get_db() as db:
        result = await db.execute(
            "INSERT INTO items (name, description) VALUES ($1, $2) RETURNING id",
            item.name, item.description
        )
        new_id = result.fetchone()[0]
    
    await cache_delete("items:all")   # invalida cache
    return {**item.dict(), "id": new_id}

@app.delete("/api/items/{item_id}", status_code=204)
async def delete_item(item_id: int):
    async with get_db() as db:
        result = await db.execute(
            "DELETE FROM items WHERE id = $1 RETURNING id", item_id
        )
        if not result.fetchone():
            raise HTTPException(status_code=404, detail="Item not found")
    
    await cache_delete("items:all")
    return None
```

### `database.py` - Connessione Asincrona a PostgreSQL

```python
# backend/app/database.py
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from contextlib import asynccontextmanager

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://appuser:apppassword@postgresql:5432/appdb"
)

# Pool di connessioni asincrono
engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,    # verifica la connessione prima di usarla
)

async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: c.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                description TEXT
            )
        """))

@asynccontextmanager
async def get_db():
    async with async_session() as session:
        yield session
```

### `cache.py` - Redis con Fallback Graceful

Questo è il componente più importante per la resilienza - se Redis non è disponibile, l'app continua a funzionare:

```python
# backend/app/cache.py
import os
import redis.asyncio as redis

REDIS_URL = os.getenv("REDIS_URL", "redis://redis-master:6379")

async def get_redis():
    """Restituisce client Redis, o None se non raggiungibile."""
    try:
        client = redis.from_url(REDIS_URL, socket_connect_timeout=1)
        await client.ping()
        return client
    except Exception:
        return None   # ← silenzioso, non blocca l'app

async def cache_get(key: str) -> str | None:
    client = await get_redis()
    if client is None:
        return None   # cache miss: l'app andrà direttamente al DB
    try:
        return await client.get(key)
    except Exception:
        return None

async def cache_set(key: str, value: str, ttl: int = 60):
    client = await get_redis()
    if client is None:
        return         # scrivi nel nulla, non è un errore
    try:
        await client.setex(key, ttl, value)
    except Exception:
        pass           # ignora errori di scrittura cache

async def cache_delete(key: str):
    client = await get_redis()
    if client is None:
        return
    try:
        await client.delete(key)
    except Exception:
        pass
```

**Pattern: Graceful Degradation**

```
Con Redis:                    Senza Redis (o partizione):
  GET /api/items                GET /api/items
    → cache hit → 5ms             → cache miss
                                  → DB query → 50ms
                                  ← 200 OK (più lento ma OK)

Il servizio degrada
in performance ma non in disponibilità.
```

---

## 7.3 Il Frontend (Nginx + Vanilla JS)

Il frontend è una Single Page Application (SPA) che:
- Mostra la lista degli item in tempo reale
- Si aggiorna ogni 5 secondi (polling)
- Mostra un badge di stato dell'API

```
frontend/
├── html/
│   └── index.html    ← SPA completa (HTML + CSS + JS)
└── nginx.conf        ← configurazione Nginx + proxy
```

### `nginx.conf` - Proxy verso il Backend

```nginx
# frontend/nginx.conf
server {
    listen 80;
    
    # Serve i file statici
    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files $uri $uri/ /index.html;
    }
    
    # Proxy delle richieste API al backend
    location /api/ {
        proxy_pass http://backend:3000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
    }
}
```

**Perché il proxy su Nginx:**
- Il browser non può chiamare `http://backend:3000` (è un DNS interno del cluster)
- Nginx risolve `backend` via CoreDNS e fa da ponte
- Evita problemi di CORS

### La SPA - Loop di Polling

```javascript
// frontend/html/index.html (estratto)
async function fetchItems() {
    const statusEl = document.getElementById('api-status');
    try {
        const response = await fetch('/api/items');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const items = await response.json();
        renderItems(items);
        
        statusEl.textContent = '● API Online';
        statusEl.className = 'status online';
    } catch (err) {
        statusEl.textContent = '● API Offline';
        statusEl.className = 'status offline';
        // Non crasho - mostro solo lo stato di errore
    }
}

// Polling ogni 5 secondi
setInterval(fetchItems, 5000);
fetchItems(); // prima chiamata immediata
```

---

## 7.4 PostgreSQL - Il Database Persistente

```
Configurazione nel progetto:
  Database: appdb
  User:     appuser
  Password: apppassword
  Port:     5432

Schema:
  TABLE items (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    description TEXT
  )
```

**Perché PostgreSQL invece di MySQL/SQLite:**
- Supporto nativo per async (asyncpg è il driver più veloce)
- ACID compliant (transazioni sicure)
- Bitnami Helm chart maturo e ben supportato

---

## 7.5 Redis - La Cache

```
Configurazione nel progetto:
  Host:     redis-master  (nome del Service Bitnami)
  Port:     6379
  Auth:     disabilitato (ambiente di sviluppo)
  
Strategia: Cache-Aside con TTL 30s
  ┌─────────────────────────────────────────┐
  │           Cache-Aside Pattern           │
  │                                         │
  │  Read:                                  │
  │    1. Cerca in Redis                    │
  │    2. Se cache hit → ritorna subito     │
  │    3. Se cache miss → leggi da DB       │
  │    4. Scrivi in Redis con TTL           │
  │                                         │
  │  Write (POST/DELETE):                   │
  │    1. Scrivi/elimina da DB              │
  │    2. Invalida la chiave in Redis       │
  └─────────────────────────────────────────┘
```

---

## 7.6 I Pattern di Resilienza Implementati

### 1. Graceful Degradation (Redis)
Se Redis è irraggiungibile, le richieste vanno direttamente a PostgreSQL. Performance peggiore, ma zero errori 5xx.

### 2. Health Check
```python
@app.get("/api/health")
async def health():
    return {"status": "ok"}
```
Kubernetes usa questo endpoint per le probe di liveness e readiness:
- **Readiness:** il pod riceve traffico solo se risponde 200
- **Liveness:** se smette di rispondere, K8s riavvia il pod

### 3. Connection Pool con `pool_pre_ping`
```python
engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,
    pool_pre_ping=True,   # verifica la connessione prima di usarla
)
```
Se PostgreSQL ha riavviato, il pool non usa connessioni stantie.

### 4. Timeout di Connessione Redis
```python
client = redis.from_url(REDIS_URL, socket_connect_timeout=1)
```
Massimo 1 secondo di attesa per Redis. Evita che un Redis lento blocchi tutto.

### 5. Repliche Multiple
3 repliche del backend + HPA garantiscono che se un pod viene ucciso (esperimento 1), gli altri continuano a servire traffico.

---

## Riepilogo

| Componente | Tecnologia | Ruolo | Repliche |
|---|---|---|---|
| Frontend | Nginx + HTML/JS | UI, proxy verso API | 2 |
| Backend | FastAPI (Python) | Logica CRUD, cache, DB | 3 (HPA: 2-6) |
| Database | PostgreSQL 16 | Persistenza dati | 1 (StatefulSet) |
| Cache | Redis 7 | Cache read-through | 1 (StatefulSet) |

**Prossima lezione →** [08 - Deploy su Kubernetes](08-deploy-kubernetes.md)
