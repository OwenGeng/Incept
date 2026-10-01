# LinglongLab local development

LinglongLab has two application services and one embedded video workspace:

| Surface | Directory | Local URL |
| --- | --- | --- |
| FastAPI | `apps/api` | `http://localhost:8000` |
| Next.js | `apps/web` | `http://localhost:3000` |
| Vue video workspace | `apps/video-vue` | built into `apps/web/public/video-app` |

Production deployment is documented only in `DEPLOY.md`. Do not copy deployment
commands from archived design documents.

## Prerequisites

- Node.js 20+
- pnpm 10.18.1
- Python 3.12+
- Google Cloud CLI with Application Default Credentials when testing live GCP integrations

Install dependencies from the repository root:

```bash
pnpm install --frozen-lockfile
python3.12 -m venv apps/api/.venv
apps/api/.venv/bin/python -m pip install -r apps/api/requirements.txt pytest
```

Copy the example files before local development and keep the real files out of Git:

```bash
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
```

Model IDs, API endpoints, project IDs, and Vertex locations are user-owned
configuration. Do not change them based on error-message guesswork.

## Run locally

Start the API:

```bash
cd apps/api
.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

In a second terminal, build/sync the video workspace and start Next.js:

```bash
pnpm dev:web
```

Useful health checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/readyz
```

## Verification

Run the release-quality checks from the repository root:

```bash
pnpm preflight
pnpm lint:web
pnpm typecheck:web
pnpm --dir apps/video-vue typecheck
pnpm --dir apps/video-vue check:i18n
PYTHONPATH=apps/api apps/api/.venv/bin/python -m pytest apps/api/tests -q
pnpm build:web
```

The same checks and both production Docker builds run in
`.github/workflows/preflight.yml`.

## Cloud authentication

Local Vertex AI and BigQuery calls use Application Default Credentials:

```bash
gcloud auth application-default login
```

Cloud Run deployment uses the active gcloud account and Secret Manager mappings
from `.env.deploy`. Run `pnpm preflight:deploy` before creating a release manifest,
then follow `DEPLOY.md`.

## Adding dependencies

Python:

```bash
apps/api/.venv/bin/python -m pip install <package>
# add an explicit compatible requirement to apps/api/requirements.txt
```

Web:

```bash
pnpm --filter @linglonglab/web add <package>
```

Video workspace:

```bash
pnpm --dir apps/video-vue add <package> --filter <workspace-package>
```
