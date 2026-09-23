# NBSpark — Architecture Reference

> Two tools, one unified backend, Cloud Run on GCP

---

## 1. Overview

**NBSpark** is an internal AI workspace for Moloco's NBS China GTM team. It hosts two tools:

| Tool | Purpose |
|------|---------|
| **InterSight** | AI-powered BI for supply SMB cross-sell. Queries BigQuery, surfaces prospect lists (P1–P4), and generates weekly Gemini AI summaries. |
| **Incept** | AI creative generation workspace. Uses Vertex AI (Gemini / Imagen) and OpenAI to generate, edit, outpaint, and manage ad creatives. |

Both tools share a single FastAPI backend (`nbs-api`) and a single Next.js frontend (`nbs-portal`).

---

## 2. Services

| Service | Cloud Run name | Image | Port | Auth |
|---------|---------------|-------|------|------|
| Python backend | `nbs-api` | `Dockerfile.nbs-api` | 8080 | IAM (no public access) |
| Next.js frontend | `nbs-portal` | `Dockerfile.web` | 8080 | Public |

### Cloud Run configuration

```
nbs-api:
  Memory:      2 GiB
  Timeout:     300 s  (long-running image generation jobs)
  Concurrency: 40
  Auth:        --no-allow-unauthenticated

nbs-portal:
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
| Analytics DB | BigQuery (cross-project read) |
| Incept persistence | SQLite (`apps/api/data/incept.db`) |
| Static files | Local filesystem, served at `/static/` by nbs-api |
| Deployment | Cloud Run + Artifact Registry (via `deploy.ps1`) |
| AI — InterSight | Google Gemini API (BQ data summarization) |
| AI — Incept | Vertex AI Gemini / Imagen + OpenAI (image generation) |
| GCP auth (local) | Application Default Credentials (ADC) |
| GCP auth (Cloud Run) | Service Account attached to nbs-api |

---

## 4. System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser                                                          │
│  ├── /supply-smb/...        → InterSight pages                   │
│  └── /incept/...            → Incept workspace pages             │
└────────────────────────┬─────────────────────────────────────────┘
                         │ HTTPS (public)
┌────────────────────────▼─────────────────────────────────────────┐
│  Cloud Run: nbs-portal (Next.js 15)                              │
│  ├── App Router pages + layouts                                  │
│  ├── NextAuth v5: Google OAuth + JWT session                     │
│  ├── /api/[...path]  → proxy to nbs-api (InterSight routes)      │
│  └── /api/incept/[...path]  → proxy to nbs-api (Incept routes)  │
└────────────────────────┬─────────────────────────────────────────┘
                         │ Cloud Run service-to-service
                         │ (x-internal-api-key + x-user-email headers)
┌────────────────────────▼─────────────────────────────────────────┐
│  Cloud Run: nbs-api (FastAPI)                                    │
│                                                                  │
│  InterSight routes:                                              │
│  ├── /api/v1/supply-smb/*      prospect lists, filters           │
│  ├── /api/v1/ai-insights/*     Gemini weekly summaries           │
│  ├── /api/v1/leads/*           lead management                   │
│  └── /health                   health check                      │
│                                                                  │
│  Incept routes (no prefix):                                      │
│  ├── /me, /provider-config, /tools                               │
│  ├── /workspaces, /jobs, /assets                                 │
│  ├── /threads, /sessions                                         │
│  └── /workflows/{image-generation,image-edit,outpaint,...}       │
│                                                                  │
│  Static files:                                                   │
│  └── /static/generated/*    generated images                    │
│      /static/uploads/*      uploaded source images               │
└────────────┬──────────────────────────────────┬─────────────────┘
             │                                  │
             ▼                                  ▼
      BigQuery                          SQLite + Vertex AI / OpenAI
      (InterSight data)                 (Incept jobs/assets/threads +
                                         image generation)
```

---

## 5. Authentication & Authorization

### Auth flow

```
1. User visits nbs-portal → redirected to Google OAuth sign-in
2. NextAuth verifies @moloco.com domain (rejects others)
3. JWT session created: { email, name, role }
4. Every nbs-portal → nbs-api server call includes:
   - x-internal-api-key: <shared secret>    (portal identity)
   - x-user-email:       user@moloco.com     (forwarded identity)
   - x-user-role:        admin | user        (forwarded role)
5. nbs-api validates x-internal-api-key; trusts forwarded headers
```

### Roles

| Role | How assigned | Access |
|------|-------------|--------|
| `admin` | Email in `INCEPT_ADMIN_EMAILS` env var | Full access + Incept admin ops |
| `manager` | Email in `INCEPT_MANAGER_EMAILS` env var | Elevated Incept access |
| `user` | Any `@moloco.com` email | Standard access |

No Firestore or external user database — role is derived from env var email lists at request time.

### Local dev auth bypass

For local development without Google login:

```dotenv
# apps/web/.env.local
AUTH_DEV_SKIP_SIGN_IN=true
```

---

## 6. GCP Projects

| Role | Project ID |
|------|-----------|
| **Deploy + Write** | `ads-bpd-guard-sandbox` — Cloud Run, Artifact Registry, all write BQ tables |
| **Read data** | `ads-bpd-guard-china` — all analytical source tables (cross-project BQ read) |

The Service Account running `nbs-api` in Cloud Run must have `roles/bigquery.dataViewer` on `ads-bpd-guard-china`.

### BigQuery — Read tables (ads-bpd-guard-china)

```
athena.dim1_app_v3                  App metadata, company info, monetization
athena.fact_dsp_core                UA spend history
athena.fact_dsp_publisher           Publisher SDK impressions
athena.fact_app_basis_v3            Monthly downloads by app
gtm.supply_demand_overlap           SDK + UA status (Tier 1/2/3)
gtm.fact_supply_with_tracking_publisher  Supply partner tracking
sensortower.network_analysis        Competitor ad network signals
sensortower.fact_app_basis_v3       ST download data
```

### BigQuery — Write tables (ads-bpd-guard-sandbox)

```
supply_smb.apps                     Weekly prospect list refresh output
supply_smb.companies                Weekly company-level aggregation
supply_smb.manual_input             AM status updates / notes
supply_smb.ai_reports               Gemini weekly summaries
yingzi_uploads.hq_country_triage    GTM-validated HQ country overrides
```

---

## 7. Incept Data Persistence

Incept uses **SQLite** for lightweight local persistence. No Firestore or external DB.

| What | Storage |
|------|---------|
| Generation jobs | `apps/api/data/incept.db` → `jobs` table |
| Generated assets | `apps/api/data/incept.db` → `assets` table |
| Creative threads | `apps/api/data/incept.db` → `threads` table |
| Generated images | `apps/api/static/generated/` (filesystem) |
| Uploaded images | `apps/api/static/uploads/` (filesystem) |

In Cloud Run, the SQLite DB and static files live on the container's writable filesystem. They do **not** persist across container restarts — this is acceptable for the current use case (short-lived creative sessions).

---

## 8. Proxy Architecture

Browser Incept UI calls flow through the Next.js proxy:

```
Browser
  └── fetch("/api/incept/workflows/image-generation", { method: "POST", body })
         │
         ▼
  Next.js route handler: apps/web/app/api/incept/[...path]/route.ts
    - validates NextAuth session
    - strips /api/incept prefix
    - adds x-internal-api-key + x-user-email headers
    - forwards to: API_BASE_URL/workflows/image-generation
         │
         ▼
  nbs-api FastAPI
    - validates x-internal-api-key
    - runs image generation via Vertex AI / OpenAI
    - returns result
```

Backend resolution order in the proxy:

```typescript
const INCEPT_BASE =
  process.env.INCEPT_API_BASE_URL ??   // explicit override (unused in standard setup)
  process.env.API_BASE_URL ??          // unified backend URL
  "http://localhost:8000";             // local dev fallback
```

---

## 9. Directory Structure

```
NBSpark/
├── apps/
│   ├── api/                           → nbs-api (FastAPI)
│   │   ├── app/
│   │   │   ├── main.py                → app factory, router registration, static mount
│   │   │   ├── routers/
│   │   │   │   ├── supply_smb.py      → InterSight supply SMB endpoints
│   │   │   │   ├── ai_insights.py     → Gemini summary endpoints
│   │   │   │   ├── leads.py           → lead management
│   │   │   │   ├── incept.py          → all Incept API routes (24 routes)
│   │   │   │   ├── health.py          → /health
│   │   │   │   ├── admin.py           → admin ops
│   │   │   │   └── internal.py        → internal endpoints
│   │   │   ├── incept/                → Incept business logic
│   │   │   │   ├── config.py          → pydantic settings (Vertex AI, OpenAI, etc.)
│   │   │   │   ├── db.py              → SQLite init + CRUD (jobs, assets, threads)
│   │   │   │   ├── store.py           → in-memory job/asset store + persistence
│   │   │   │   ├── thread_store.py    → in-memory thread store + persistence
│   │   │   │   ├── models.py          → Pydantic models
│   │   │   │   ├── auth.py            → user identity from headers
│   │   │   │   ├── provider*.py       → AI provider clients (Gemini, Vertex, OpenAI)
│   │   │   │   └── workflows/         → image gen, edit, outpaint, remove-bg, add-text
│   │   │   └── services/              → InterSight services
│   │   │       ├── bigquery.py        → BQ client + query runner
│   │   │       └── gemini.py          → Gemini summarization
│   │   ├── static/
│   │   │   ├── generated/             → Incept output images (runtime)
│   │   │   └── uploads/               → Incept upload source images (runtime)
│   │   ├── data/
│   │   │   └── incept.db              → SQLite (runtime, auto-created)
│   │   ├── .env                       → local dev config (both InterSight + Incept)
│   │   └── requirements.txt
│   │
│   └── web/                           → nbs-portal (Next.js 15)
│       ├── app/
│       │   ├── page.tsx               → portal home (InterSight + Incept cards)
│       │   ├── supply-smb/            → InterSight pages
│       │   ├── incept/                → Incept workspace pages
│       │   └── api/
│       │       ├── auth/              → NextAuth OAuth handlers
│       │       └── incept/[...path]/  → Incept proxy route
│       ├── components/                → shared UI components
│       ├── lib/
│       │   ├── auth.ts                → NextAuth config + session helpers
│       │   └── incept-api.ts          → Incept API client
│       └── .env.local                 → local dev config
│
├── sql/                               → BigQuery SQL files (InterSight)
│   ├── list1_2_sdk_no_ua.sql
│   ├── list3_supply_partner_upsdk.sql
│   └── list4_5_6_cold_prospects.sql
│
├── docs/                              → Project documentation
├── Dockerfile.nbs-api                 → unified backend image (includes rembg system deps)
├── Dockerfile.web                     → nbs-portal image
├── deploy.ps1                         → one-click Cloud Run deployment (Windows PowerShell)
└── .env.deploy                        → production secrets (git-ignored)
```

---

## 10. Deployment

Deployment is handled by `deploy.ps1` — no CI/CD pipeline. Run manually when deploying.

```
deploy.ps1 [target]

  api   → build + push Dockerfile.nbs-api → deploy nbs-api to Cloud Run
  web   → build + push Dockerfile.web     → deploy nbs-portal (auto-fetches nbs-api URL)
  both  → deploy api then web (default)
  all   → same as both
```

### Docker build context

```
Dockerfile.nbs-api:
  Base:         python:3.12-slim
  System deps:  gcc libgl1 libglib2.0-0   (required by rembg)
  Copies:       apps/api/app/ + sql/
  Runtime dirs: /app/data  /app/static/generated  /app/static/uploads

Dockerfile.web:
  Base:         node:20-alpine (multi-stage)
  Copies:       apps/web/ (full Next.js build)
```

### Artifact Registry

```
Region:  asia-northeast1
Host:    asia-northeast1-docker.pkg.dev
Repo:    intersight
Images:
  asia-northeast1-docker.pkg.dev/<project>/intersight/nbs-api
  asia-northeast1-docker.pkg.dev/<project>/intersight/nbs-portal
```

### Key environment variables (Cloud Run)

**nbs-api:**

```dotenv
INTERSIGHT_ENV=production
INTERSIGHT_API_MODE=live
INTERSIGHT_INTERNAL_API_KEY=<shared secret>
CORS_ALLOW_ORIGINS=https://nbs-portal-xxxx-an.a.run.app
GCP_PROJECT_DEPLOY=ads-bpd-guard-sandbox
BQ_READ_PROJECT=ads-bpd-guard-china
GEMINI_MODEL=gemini-3.6-flash
GOOGLE_GENAI_USE_ENTERPRISE=True
INCEPT_ENV=production
AUTH_MODE=iap
GCP_PROJECT_ID=ads-bpd-guard-sandbox
GCP_LOCATION=us-central1
VERTEX_GEMINI_ENABLED=true
DEFAULT_IMAGE_PROVIDER=gemini
```

**nbs-portal:**

```dotenv
API_BASE_URL=https://nbs-api-xxxx-an.a.run.app
INTERSIGHT_INTERNAL_API_KEY=<shared secret>   # must match nbs-api
GOOGLE_CLIENT_ID=<oauth client id>
GOOGLE_CLIENT_SECRET=<oauth client secret>
AUTH_SECRET=<nextauth signing key>
NEXTAUTH_URL=https://nbs-portal-xxxx-an.a.run.app
```

---

## 11. InterSight Data Flow

```
Weekly (manual trigger or scheduled):
  1. Run SQL queries in BigQuery (sql/*.sql)
     → writes to ads-bpd-guard-sandbox.supply_smb.{apps, companies}

  2. Gemini summarization agent
     → reads supply_smb.apps → generates AI report
     → writes to supply_smb.ai_reports

On each user request:
  Browser → nbs-portal → /api/[path] → nbs-api → BigQuery (live query)
                                                  ↓
                                           Returns JSON to UI
```

Prospect tiers (P1–P4) are computed at query time from BQ data — no pre-computation needed.

---

## 12. Incept Image Generation Flow

```
User triggers generation in Incept UI
    ↓
Browser POST /api/incept/workflows/image-generation
    ↓
Next.js proxy (strips prefix, adds auth headers)
    ↓
nbs-api: POST /workflows/image-generation
    ↓
WorkflowRunner:
  1. Creates GenerationJob in SQLite + memory store
  2. Dispatches to image provider (Vertex Gemini / Imagen / OpenAI)
  3. Saves result images to /app/static/generated/
  4. Creates Asset records in SQLite
  5. Updates job status: queued → running → completed
    ↓
Browser polls GET /api/incept/jobs/{id} until status = completed
    ↓
Renders images via /api/incept/static/generated/{filename}
  (proxied through Next.js → nbs-api /static/generated/{filename})
```
