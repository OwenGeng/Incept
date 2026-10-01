# Linglong Lab AI Committee release review

Use one completed copy of this checklist for every immutable release manifest
under `releases/`. Do not place secrets, API keys, or customer media here.

## Identity and scope

- Release ID:
- Release manifest path:
- Git source commit:
- Review date:
- Engineering owner:
- Product owner:
- AI Committee reviewers:

| Product surface | Included | Evidence |
| --- | --- | --- |
| Image |  |  |
| Video |  |  |
| Gaming Playable |  |  |

## Model and data controls

| Area | Decision / evidence |
| --- | --- |
| Vertex models enabled |  |
| OpenAI models enabled |  |
| Provider credentials | Secret Manager references only; no values recorded |
| User media storage | GCS bucket, retention and access control |
| Cloud SQL | migration Job name and migration result |
| Async execution | Process-local job risks reviewed; no active jobs during rollout |
| Logging and observability | request IDs, task IDs, error alert destination |

## Security and release evidence

- [ ] API Cloud Run service is private; only the Web runtime identity can invoke it.
- [ ] Runtime service account has least-privilege Vertex AI, GCS, Cloud SQL and Secret Manager access.
- [ ] Video Production and Gaming Playable return 404 when excluded by the manifest.
- [ ] Upload, file download, delete and a non-destructive Vertex generation smoke test passed.
- [ ] `pnpm run typecheck:web` and `pnpm run build:web` passed from the release commit.
- [ ] API health and AI Video health passed after Cloud Run deploy.
- [ ] API `/readyz`, Web login, feedback, Image, and Video smoke tests passed.
- [ ] API and Web Artifact Registry image digests were captured below.

| Artifact | Immutable tag | Digest | Cloud Run revision |
| --- | --- | --- | --- |
| API |  |  |  |
| Web |  |  |  |

## Approval and rollback

- Approval decision: Approved / Approved with conditions / Rejected
- Conditions or known limitations:
- Previous approved release ID:
- Rollback command / owner:
- Post-deploy observation window and outcome:
