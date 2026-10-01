# LinglongLab Cloud Run deployment

LinglongLab deploys two services in `asia-northeast1`:

- `incept-web`: public Next.js entry point and Google OAuth session boundary.
- `incept-api`: private FastAPI service. Only the Web runtime service account may invoke it.

The production release profile is `image-video`; Gaming Playable remains disabled.

## Required local tools

- Docker Desktop
- Google Cloud CLI
- Node.js 20 and pnpm 10.18.1
- Git

Set `BUILD_BACKEND=cloud-build` in `.env.deploy` when local Docker Hub access is
unreliable. The deployment script then builds and pushes both immutable images
with Cloud Build. Use `BUILD_BACKEND=local` only when Docker Desktop and Docker
Hub are reachable.

Authenticate before any release check:

```bash
gcloud auth login
gcloud config set project ads-bpd-guard-sandbox
```

## Deployment configuration

Copy `.env.deploy.example` to `.env.deploy`. Never commit `.env.deploy`.

Required Secret Manager mappings:

- Cloud SQL connection JSON
- internal API key shared by Web and API
- Google OAuth client secret
- Auth.js session secret

OpenAI and Anthropic mappings are optional. Set both the secret name and version
for a provider, or leave both empty. Model IDs and Vertex locations are
deployment-owned configuration; do not change them without confirmed source
documentation.

Run the local configuration check:

```bash
pnpm preflight:deploy
```

The API runtime service account requires:

- `roles/run.invoker` on `incept-api`
- `roles/cloudsql.client`
- `roles/aiplatform.user`
- `roles/serviceusage.serviceUsageConsumer`
- `roles/storage.objectUser` on the asset/video bucket
- `roles/secretmanager.secretAccessor` on each configured secret

`deploy.sh` applies these bindings idempotently where the deployer has permission.

## Verification before creating a release

```bash
pnpm preflight
pnpm lint:web
pnpm typecheck:web
pnpm --dir apps/video-vue typecheck
pnpm --dir apps/video-vue check:i18n
apps/api/.venv/bin/python -m pytest apps/api/tests -q
pnpm build:web
docker build --platform linux/amd64 -f Dockerfile.nbs-api -t incept-api:preflight .
docker build --platform linux/amd64 \
  --build-arg INCEPT_ENABLE_GAMING_PLAYABLE=false \
  -f Dockerfile.web -t incept-web:preflight .
```

The checkout must be clean before creating a release manifest.

## Immutable release manifest

Create the manifest from the reviewed source commit:

```bash
node scripts/release-manifest.mjs create image-video linglong-image-video-v1.0.0-rc.1
```

Complete the AI Committee, Engineering owner, and Product owner approval records,
set the rollback release ID, then commit only the manifest as the release-record
commit. The deployment gate requires this exact two-commit shape:

1. reviewed source commit;
2. release-record commit containing only the manifest.

Validate it:

```bash
pnpm release:validate -- releases/linglong-image-video-v1.0.0-rc.1.json
```

## Deploy

```bash
./deploy.sh --manifest releases/linglong-image-video-v1.0.0-rc.1.json
```

Deploy one service only when necessary:

```bash
./deploy.sh api --manifest releases/linglong-image-video-v1.0.0-rc.1.json
./deploy.sh web --manifest releases/linglong-image-video-v1.0.0-rc.1.json
```

The script uses immutable Artifact Registry tags, keeps the API private, grants
the Web service account API invocation permission, mounts Cloud SQL and the GCS
video volume, and configures the public Web origin for OAuth and CORS.

If organization policy prevents the script from granting `allUsers` on the Web
service, an administrator must grant `roles/run.invoker` on `incept-web` only.
Never grant `allUsers` on `incept-api`.

## OAuth

The authorized Google OAuth redirect URI must match the public Web origin:

```text
https://<public-web-origin>/api/auth/callback/google
```

When `CUSTOM_DOMAIN` is configured, use that domain rather than the generated
`.run.app` URL.

## Post-deploy smoke test

Before broad use:

1. Confirm both Cloud Run revisions show `Ready=True`.
2. Open the public Web URL and complete Google sign-in.
3. Confirm `/api/incept/readyz` returns a healthy PostgreSQL result through the authenticated proxy.
4. Create and reload an Image workspace.
5. Create and reload a Video project from the GCS-mounted workspace.
6. Run one non-destructive image generation and one short Video agent request.
7. Submit feedback and verify the request succeeds.
8. Check Cloud Run error rate, p95 latency, Cloud SQL connections, and GCS errors.

Do not deploy while media jobs are running. They execute in the API process and
an old revision can be terminated after traffic moves.

## Rollback

Use Cloud Run revision traffic management to move 100% traffic back to the
previous approved API and Web revisions. The release manifest must record that
previous release ID before deployment. Do not reuse or overwrite an immutable
image tag.
