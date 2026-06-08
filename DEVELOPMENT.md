# NBSpark — Local Development Guide

Two services to run locally:

| Service | Directory | Port |
|---------|-----------|------|
| nbs-api (InterSight + Incept backend) | `apps/api` | 8000 |
| nbs-portal (Next.js frontend) | `apps/web` | 3000 |

---

## First-time Setup

### 1. Required tools

```powershell
node --version    # 20+
pnpm --version    # 10+
python --version  # 3.12+
gcloud --version  # authenticated
```

### 2. GCP Application Default Credentials (ADC)

Both InterSight (BigQuery) and Incept (Vertex AI / Gemini) authenticate via ADC:

```powershell
gcloud auth application-default login
```

Verify it works:

```powershell
gcloud auth application-default print-access-token
# → outputs ya29.xxx
```

> If the token expires, just re-run the login command. No need to restart services.

### 3. Install dependencies

```powershell
# From repo root — installs all Node workspace packages
pnpm install

# Python deps for nbs-api
cd apps/api
pip install -r requirements.txt
```

---

## Configuration Files

Both env files already exist and are pre-filled for local development. You normally don't need to touch them.

| File | Service | Key fields |
|------|---------|-----------|
| `apps/api/.env` | nbs-api | BQ projects, INTERSIGHT_INTERNAL_API_KEY, Gemini model, Incept provider config, GCP project for Vertex AI |
| `apps/web/.env.local` | nbs-portal | Google OAuth credentials, API_BASE_URL, INTERSIGHT_INTERNAL_API_KEY |

**Critical relationship**: `INTERSIGHT_INTERNAL_API_KEY` must match in both files. The portal attaches this key to every server-side API call; nbs-api validates it to trust the forwarded user identity.

---

## Starting Services

### Two terminals (recommended for active development)

**Terminal 1 — nbs-api**

```powershell
cd apps/api
uvicorn app.main:app --reload --port 8000
```

Successful startup:

```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

> On first startup, `rembg` downloads its background-removal model (~170 MB). Subsequent startups are instant.

---

**Terminal 2 — nbs-portal**

```powershell
cd apps/web
pnpm dev
```

Successful startup:

```
▲ Next.js 15.x.x
- Local:  http://localhost:3000
✓ Ready in x.xs
```

---

### Background jobs (quick smoke test)

If you just want everything running without watching logs:

```powershell
# From repo root
Start-Job -ScriptBlock { Set-Location apps/api; uvicorn app.main:app --port 8000 }
Start-Job -ScriptBlock { Set-Location apps/web; pnpm dev }

# View output
Get-Job | Receive-Job
```

---

## Verifying Services

### nbs-api

```powershell
# Health check
Invoke-RestMethod http://localhost:8000/health
# → { "status": "ok", "mode": "mock" }

# Open Swagger docs in browser
Start-Process http://localhost:8000/docs
```

### nbs-portal

Open http://localhost:3000 — you should see the NBSpark portal with InterSight and Incept.

### Quick access URLs

| Destination | URL |
|-------------|-----|
| Portal home | http://localhost:3000 |
| InterSight | http://localhost:3000/supply-smb/no-sdk-no-ua/weekly-brief |
| Incept workspace | http://localhost:3000/incept |
| API Swagger docs | http://localhost:8000/docs |

---

## InterSight: mock mode vs live mode

`INTERSIGHT_API_MODE` in `apps/api/.env` controls data source:

| Value | Behavior | When to use |
|-------|----------|-------------|
| `mock` | Returns static hardcoded data, no BQ queries | UI layout development, fast iteration |
| `live` | Runs real BigQuery SQL | Feature validation, data verification |

Switch the value and restart nbs-api. ADC must be configured for `live` mode.

---

## Frequently Asked Questions

### Q: Incept page loads but image generation does nothing / errors

The Incept UI calls `/api/incept/...` which proxies to nbs-api. Verify nbs-api is running:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

If nbs-api is up, check the browser Network tab for failed requests and look at the nbs-api terminal for error output.

---

### Q: InterSight shows no data / BQ query errors after switching to live mode

ADC is not configured or has expired:

```powershell
gcloud auth application-default login
```

Then restart nbs-api.

---

### Q: Incept image generation fails with Vertex AI errors

Check in order:

1. **ADC not configured**: run `gcloud auth application-default login`
2. **Wrong project ID**: check `GCP_PROJECT_ID` in `apps/api/.env`
3. **Vertex AI API not enabled**: enable `aiplatform.googleapis.com` in GCP Console
4. **Switch to OpenAI instead**: set `DEFAULT_IMAGE_PROVIDER=openai` and fill in `OPENAI_API_KEY=sk-...` in `apps/api/.env`

---

### Q: nbs-api starts but crashes immediately with SQLite errors

The Incept SQLite DB initialises on first startup. If you see table errors, delete the stale DB and restart:

```powershell
Remove-Item apps/api/data/incept.db -ErrorAction SilentlyContinue
# Restart nbs-api — it recreates the DB automatically
```

---

### Q: `pnpm dev` fails with `Cannot find module '@incept/shared'`

Workspace links aren't set up. Re-run from repo root:

```powershell
pnpm install
```

---

### Q: Browser redirects to sign-in page, want to skip Google login locally

Add to `apps/web/.env.local`:

```dotenv
AUTH_DEV_SKIP_SIGN_IN=true
```

Restart `pnpm dev`. This allows anyone to access without auth — **local dev only, never in production**.

---

## Adding New Features

### Add an InterSight API endpoint

1. Create or edit a router file in `apps/api/app/routers/`
2. Register the router in `apps/api/app/main.py` if it's new
3. With `--reload`, uvicorn hot-reloads on save

### Add an Incept API endpoint

1. Edit `apps/api/app/routers/incept.py` — add the route directly
2. If the logic is complex, extract it into a new module under `apps/api/app/incept/`
3. Update imports accordingly

### Add a new portal page or tool

```
apps/web/app/
├── incept/          → Incept workspace  (/incept)
├── supply-smb/      → InterSight analysis  (/supply-smb/...)
└── <new-tool>/      → new tool entry
    ├── layout.tsx   → auth guard + provider wrapper
    └── page.tsx     → renders the main component
```

Add a card for the new tool on the portal home page: `apps/web/app/page.tsx`.

### Add a new Python dependency

```powershell
# Add to apps/api/requirements.txt, then install
cd apps/api
pip install -r requirements.txt
```

Update `Dockerfile.nbs-api` if the package requires system libraries (e.g., `libssl`, `libgl1`).
