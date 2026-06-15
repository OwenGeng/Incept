# Incept — Architecture Reference

> AI Operating System for Moloco NBS China GTM team

---

## 1. Overview

**Incept** is an internal AI workspace for Moloco's NBS China GTM team. It hosts three product modules, each with its own portal and AI agents:

| Module | Purpose | Status |
|--------|---------|--------|
| **Supply** | Supply intelligence — prospect ranking, weekly briefs, AI cross-sell signals. Multi-tenant: SMB, Xiaomi, and future verticals. | Live |
| **Studio** | AI creative workspace — generate, edit, and manage ad creatives at scale via Vertex AI / Gemini / Imagen. | Live |
| **CTV** | Connected TV intelligence — CTV to Web, CTV to App attribution and analytics. | Coming Soon |

---

## 2. Services

| Service | Cloud Run name | Image | Port | Auth |
|---------|---------------|-------|------|------|
| Python backend | `incept-api` | `Dockerfile.api` | 8080 | IAM (no public access) |
| Next.js frontend | `incept-web` | `Dockerfile.web` | 8080 | Public |
| Dify (AI platform) | VM / Cloud Run | Docker Compose | 80/443 | Internal |

### Cloud Run configuration

```
incept-api:
  Memory:      2 GiB
  Timeout:     300 s
  Concurrency: 40
  Auth:        --no-allow-unauthenticated

incept-web:
  Memory:      512 MiB
  Timeout:     30 s
  Auth:        --allow-unauthenticated
```

---

## 3. Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15 (App Router) + TypeScript |
| UI | Tailwind CSS + shadcn/ui |
| Auth | NextAuth.js v5 + Google OAuth |
| Backend | FastAPI (Python 3.12) |
| Analytics DB | BigQuery (cross-project read + write) |
| Studio persistence | SQLite (`apps/api/data/incept.db`) |
| Static files | Local filesystem, served at `/static/` by incept-api |
| Deployment | Cloud Run + Artifact Registry (`deploy.sh`) |
| AI — Supply | Gemini 2.5 Flash (weekly summaries, AI insights) |
| AI — Studio | Vertex AI Gemini / Imagen (image generation + editing) |
| AI — Agents | Dify (self-hosted) + Gemini 2.5 Flash |
| Agent RAG | Dify Knowledge Base (PPT / DOC / Slack ingestion) |
| Agent Memory | Dify conversation memory (short/mid) + BigQuery (long-term) |
| GCP auth (local) | Application Default Credentials (ADC) |
| GCP auth (Cloud Run) | Service Account attached to incept-api |

---

## 4. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser                                                              │
│  /              → Portal (Supply / Studio / CTV cards)               │
│  /supply-smb/*  → Supply module pages                                │
│  /xiaomi/*      → Xiaomi module pages (Supply vertical)              │
│  /ctv/*         → CTV portal (coming soon)                           │
│  /incept/*      → Studio workspace                                    │
└──────────────────────┬───────────────────────────────────────────────┘
                       │ HTTPS (public)
┌──────────────────────▼───────────────────────────────────────────────┐
│  Cloud Run: incept-web (Next.js 15)                                  │
│  ├── App Router pages + layouts                                      │
│  ├── NextAuth v5: Google OAuth + JWT session                         │
│  ├── /api/[...path]           → proxy to incept-api (Supply routes)  │
│  └── /api/incept/[...path]    → proxy to incept-api (Studio routes)  │
└──────────────────────┬───────────────────────────────────────────────┘
                       │ Cloud Run service-to-service
                       │ (x-internal-api-key + x-user-email)
┌──────────────────────▼───────────────────────────────────────────────┐
│  Cloud Run: incept-api (FastAPI)                                     │
│                                                                      │
│  Supply routes:                                                      │
│  ├── /api/v1/supply-smb/*     prospect lists (SMB vertical)          │
│  ├── /api/v1/ai-insights/*    Gemini weekly summaries                │
│  ├── /api/v1/leads/*          lead management                        │
│  ├── /api/v1/agent/supply/*   Supply Agent proxy → Dify              │
│  └── /health                  health check                           │
│                                                                      │
│  Studio routes:                                                      │
│  ├── /me, /provider-config, /tools                                   │
│  ├── /workspaces, /jobs, /assets                                     │
│  ├── /threads, /sessions                                             │
│  └── /workflows/{image-generation,image-edit,outpaint,...}           │
└──────────┬───────────────────────────────┬───────────────────────────┘
           │                               │
           ▼                               ▼
    BigQuery                        SQLite + Vertex AI / Gemini
    (Supply data)                   (Studio jobs / assets / threads)
           │
           ▼
    Dify (self-hosted)
    ├── Supply Agent
    ├── Studio Agent (future)
    └── CTV Agent (future)
```

---

## 5. Portal Structure

Three top-level products, each with its own entry point:

```
/ (Portal Home)
├── Supply  ─→  /supply-smb/...   (Live)
│               Sidebar: Supply SMB | Xiaomi | AI Insights | Settings
├── Studio  ─→  /incept/          (Live)
│               Sidebar: Image | Video (Soon) | Analyze | Library
└── CTV     ─→  /ctv/             (Soon)
                Cards: CTV to Web | CTV to App
```

Supply is a **multi-vertical module** — each vertical (SMB, Xiaomi, ...) has its own BigQuery data pipeline and Dify Knowledge Base, but shares the same sidebar and UI shell.

---

## 6. Agent Architecture

### Design Principles

- **One Agent per product module** (Supply, Studio, CTV)
- **One Knowledge Base per business vertical** (supply-smb, supply-xiaomi, ...)
- Agents share a `company-general` knowledge base for cross-cutting knowledge
- Memory is layered: short-term in Dify context, long-term in BigQuery

### Agent Overview

```
User question
     │
     ▼
incept-api /api/v1/agent/supply/chat
     │
     ▼  (HTTP POST to Dify API)
┌────────────────────────────────────────┐
│  Dify: Supply Agent                    │
│  Model: Gemini 2.5 Flash               │
│  System prompt: Supply SMB/Xiaomi expert│
│                                        │
│  Knowledge Bases (RAG):                │
│  ├── supply-smb      (SMB docs/PPT)    │
│  ├── supply-xiaomi   (Xiaomi docs)     │
│  ├── supply-[future] (add as needed)   │
│  └── company-general (Moloco basics)   │
│                                        │
│  Tools:                                │
│  └── call incept-api for live BQ data  │
│                                        │
│  Memory:                               │
│  ├── Short: in-context (1M token)      │
│  ├── Mid:   Dify conversation_id       │
│  └── Long:  BigQuery agent_memory table│
└────────────────────────────────────────┘
```

### Dify Knowledge Bases

| Knowledge Base | Content | Updated |
|---------------|---------|---------|
| `supply-smb` | SMB prospect docs, analysis PPT, business rules | Manual upload |
| `supply-xiaomi` | Xiaomi-specific strategy docs | Manual upload |
| `supply-[vertical]` | New verticals added over time | Manual upload |
| `company-general` | Moloco product intro, NBS processes, terminology | Manual upload |
| `studio-creative` | Creative best practices, ad spec guidelines | Manual upload |
| `ctv-general` | CTV business context (placeholder) | TBD |

### Memory Architecture

```
Short-term (In-context)      Mid-term (Session)           Long-term (Persistent)
────────────────────────     ────────────────────────     ────────────────────────
Dify conversation window     Dify conversation_id          BigQuery: agent_memory
Current turn context         Cross-session continuity      User prefs, key decisions
Auto-managed by Dify         Stored in Dify PostgreSQL     Queryable analytics
No extra infra needed        No extra infra needed         agents write via API
```

**No Firestore needed.** Dify's built-in PostgreSQL handles short + mid-term memory. BigQuery (already in use) handles long-term memory.

### Dify API Integration

```python
# incept-api: apps/api/app/routers/agent.py (to be implemented)
import httpx

async def ask_supply_agent(question: str, user_id: str, conversation_id: str = ""):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{settings.dify_base_url}/v1/chat-messages",
            headers={"Authorization": f"Bearer {settings.dify_supply_api_key}"},
            json={
                "query": question,
                "user": user_id,
                "conversation_id": conversation_id,  # "" = new, id = continue
                "response_mode": "blocking",
            },
            timeout=60,
        )
    return resp.json()
```

---

## 7. Authentication & Authorization

### Auth flow

```
1. User visits incept-web → redirected to Google OAuth sign-in
2. NextAuth verifies @moloco.com domain (rejects others)
3. JWT session created: { email, name, role }
4. Every incept-web → incept-api call includes:
   - x-internal-api-key: <shared secret>     (portal identity)
   - x-user-email:       user@moloco.com      (forwarded identity)
5. incept-api validates x-internal-api-key; derives role from email
```

### Roles

| Role | How assigned | Access |
|------|-------------|--------|
| `admin` | Email in `INCEPT_ADMIN_EMAILS` env var | Full access + admin ops |
| `manager` | Email in `INCEPT_MANAGER_EMAILS` env var | Elevated access |
| `user` | Any `@moloco.com` email | Standard access |
| `agency` | Email in `INCEPT_AGENCY_EMAILS` env var | Supply-only, redirected directly |

No Firestore or external user DB — role derived from env var email lists at request time.

---

## 8. GCP Projects

| Role | Project ID |
|------|-----------|
| **Deploy + Write** | `ads-bpd-guard-sandbox` — Cloud Run, Artifact Registry, write BQ tables |
| **Read data** | `ads-bpd-guard-china` — all analytical source tables (cross-project BQ read) |

### BigQuery — Read tables (ads-bpd-guard-china)

```
athena.dim1_app_v3                      App metadata, company info, monetization
athena.fact_dsp_core                    UA spend history
athena.fact_dsp_publisher               Publisher SDK impressions
athena.fact_app_basis_v3                Monthly downloads by app
gtm.supply_demand_overlap               SDK + UA status (Tier 1/2/3)
gtm.fact_supply_with_tracking_publisher Supply partner tracking
sensortower.network_analysis            Competitor ad network signals
sensortower.fact_app_basis_v3           ST download data
```

### BigQuery — Write tables (ads-bpd-guard-sandbox)

```
supply_smb.apps                 Weekly prospect list refresh output
supply_smb.companies            Weekly company-level aggregation
supply_smb.manual_input         AM status updates / notes
supply_smb.ai_reports           Gemini weekly summaries
agent_memory.interactions       Long-term agent memory (to be created)
```

---

## 9. Data Persistence

| What | Storage | Notes |
|------|---------|-------|
| Supply BQ data | BigQuery (ads-bpd-guard-china) | Read-only, refreshed weekly |
| Supply write data | BigQuery (ads-bpd-guard-sandbox) | Prospect lists, AI reports |
| Studio jobs/assets | SQLite (`apps/api/data/incept.db`) | Not persistent across restarts |
| Generated images | `/app/static/generated/` | Container filesystem |
| Uploaded images | `/app/static/uploads/` | Container filesystem |
| Agent conversation | Dify PostgreSQL (self-hosted) | Persistent, managed by Dify |
| Agent long-term memory | BigQuery `agent_memory.interactions` | Queryable, permanent |
| Dify knowledge bases | Dify PostgreSQL + pgvector | Vector embeddings for RAG |

---

## 10. Directory Structure

```
Incept/
├── apps/
│   ├── api/                              → incept-api (FastAPI)
│   │   ├── app/
│   │   │   ├── main.py                   → app factory, router registration
│   │   │   ├── core/
│   │   │   │   └── config.py             → pydantic settings (INCEPT_* env vars)
│   │   │   ├── routers/
│   │   │   │   ├── supply_smb.py         → Supply SMB endpoints
│   │   │   │   ├── ai_insights.py        → Gemini weekly summary endpoints
│   │   │   │   ├── leads.py              → lead management
│   │   │   │   ├── agent.py              → Agent proxy → Dify (to be implemented)
│   │   │   │   ├── incept.py             → all Studio API routes
│   │   │   │   ├── health.py             → /health
│   │   │   │   └── admin.py              → admin ops
│   │   │   ├── incept/                   → Studio business logic
│   │   │   │   ├── auth.py               → user identity from headers
│   │   │   │   ├── models.py             → Pydantic models
│   │   │   │   ├── db.py                 → SQLite CRUD
│   │   │   │   └── workflows/            → image gen, edit, outpaint, remove-bg
│   │   │   └── services/
│   │   │       ├── supply_smb_live.py    → BigQuery supply queries
│   │   │       └── gemini.py             → Gemini summarization
│   │   ├── .env                          → local dev config
│   │   └── requirements.txt
│   │
│   └── web/                              → incept-web (Next.js 15)
│       ├── app/
│       │   ├── page.tsx                  → portal home (Supply / Studio / CTV cards)
│       │   ├── supply-smb/               → Supply SMB pages
│       │   ├── xiaomi/                   → Xiaomi pages (Supply vertical)
│       │   ├── ctv/                      → CTV portal (coming soon)
│       │   ├── incept/                   → Studio workspace
│       │   └── api/
│       │       ├── auth/                 → NextAuth OAuth handlers
│       │       ├── [...path]/            → Supply API proxy
│       │       └── incept/[...path]/     → Studio API proxy
│       ├── components/
│       │   ├── layout/
│       │   │   ├── sidebar.tsx           → Supply sidebar (SMB, Xiaomi, AI Insights)
│       │   │   └── app-shell.tsx         → Supply layout wrapper
│       │   └── incept/                   → Studio UI components
│       └── .env.local                    → local dev config
│
├── sql/                                  → BigQuery SQL files
│   ├── list1_2_sdk_no_ua.sql
│   ├── list3_supply_partner_upsdk.sql
│   └── list4_5_6_cold_prospects.sql
│
├── docs/
│   ├── incept-architecture.md            → this file
│   └── dify-setup.md                     → Dify deployment guide (to be created)
│
├── Dockerfile.api                        → incept-api image
├── Dockerfile.nbs-api                    → incept-api image (with rembg deps for Studio)
├── Dockerfile.web                        → incept-web image
├── deploy.sh                             → one-click Cloud Run deployment
├── cloudbuild.web.yaml                   → Cloud Build config (alternative to local Docker)
├── DEVELOPMENT.md                        → local dev setup guide (Chinese)
└── .env.deploy                           → production secrets (git-ignored)
```

---

## 11. Environment Variables

### incept-api (.env / Cloud Run)

```dotenv
INCEPT_ENV=production
INCEPT_API_MODE=live
INCEPT_INTERNAL_API_KEY=<shared secret>
INCEPT_PROJECT_ROOT=/app           # SQL file path in Cloud Run
CORS_ALLOW_ORIGINS=https://incept-web-...run.app

GCP_PROJECT_DEPLOY=ads-bpd-guard-sandbox
GCP_PROJECT_DATA=ads-bpd-guard-china
BQ_WRITE_PROJECT=ads-bpd-guard-sandbox
BQ_READ_PROJECT=ads-bpd-guard-china

GOOGLE_CLOUD_PROJECT=ads-bpd-guard-sandbox
GOOGLE_CLOUD_LOCATION=global
GOOGLE_GENAI_USE_ENTERPRISE=True
GEMINI_MODEL=gemini-2.5-flash

# Agent (Dify) — to be added
DIFY_BASE_URL=https://your-dify-domain
DIFY_SUPPLY_API_KEY=<dify app api key>
```

### incept-web (.env.local / Cloud Run)

```dotenv
API_BASE_URL=https://incept-api-...run.app
INCEPT_INTERNAL_API_KEY=<shared secret>   # must match incept-api
GOOGLE_CLIENT_ID=<oauth client id>
GOOGLE_CLIENT_SECRET=<oauth client secret>
AUTH_SECRET=<nextauth signing key>
NEXTAUTH_URL=https://incept-web-...run.app
```

---

## 12. Supply Data Flow

```
Weekly refresh (manual or scheduled):
  1. Run SQL queries in BigQuery (sql/*.sql)
     → writes to ads-bpd-guard-sandbox.supply_smb.{apps, companies}

  2. Gemini summarization
     → reads supply_smb.apps
     → writes AI report to supply_smb.ai_reports

On each user request:
  Browser → incept-web → /api/[path] → incept-api → BigQuery (live query)
                                                    ↓
                                             Returns JSON to UI
```

Prospect tiers (P1–P4) computed at query time from BQ data.

---

## 13. Supply Agent Flow (to be implemented)

```
User asks Supply Agent a question
    ↓
Browser POST /api/agent/supply/chat
    ↓
incept-web proxy → incept-api /api/v1/agent/supply/chat
    ↓
incept-api: load conversation_id from request (or create new)
    ↓
POST to Dify API: { query, user, conversation_id }
    ↓
Dify Supply Agent:
  1. Semantic search across supply-smb / supply-xiaomi Knowledge Bases
  2. (Optional) Tool call → incept-api /api/v1/supply-smb/* for live BQ data
  3. Generate response with Gemini 2.5 Flash
    ↓
Return answer + conversation_id to browser
    ↓
Browser stores conversation_id for next turn (session continuity)
```

---

## 14. Studio Image Generation Flow

```
User triggers generation in Studio UI
    ↓
Browser POST /api/incept/workflows/image-generation
    ↓
incept-web proxy (strips prefix, adds auth headers)
    ↓
incept-api POST /workflows/image-generation
    ↓
WorkflowRunner:
  1. Creates GenerationJob in SQLite + memory store
  2. Dispatches to provider (Vertex Gemini / Imagen / OpenAI)
  3. Saves result to /app/static/generated/
  4. Creates Asset records in SQLite
  5. Updates job status: queued → running → completed
    ↓
Browser polls GET /api/incept/jobs/{id} until completed
    ↓
Renders images via /api/incept/static/generated/{filename}
```

---

## 15. Deployment

```bash
./deploy.sh [target]

  api   → build Dockerfile.api → push → deploy incept-api to Cloud Run
  web   → build Dockerfile.web → push → deploy incept-web (auto-fetches incept-api URL)
  both  → deploy api then web (default)
```

### Artifact Registry

```
Region:  asia-northeast1
Host:    asia-northeast1-docker.pkg.dev
Repo:    incept
Images:
  asia-northeast1-docker.pkg.dev/ads-bpd-guard-sandbox/incept/incept-api
  asia-northeast1-docker.pkg.dev/ads-bpd-guard-sandbox/incept/incept-web
```

### Notes

- Mac M-series: always build with `--platform linux/amd64`
- China network: use VPN or Cloud Build (`gcloud builds submit --config cloudbuild.web.yaml .`)
- Docker credentials: use `gcloud auth print-access-token | docker login` if `docker-credential-gcloud` missing
