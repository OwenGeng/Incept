# Linglong Lab release management

## Release model

Keep all product source in `main`; do not create permanent code forks for each
product combination. A versioned release manifest is the release module's
interface: it fixes the Git SHA, enabled product surfaces and immutable image
tag for one reviewable deployment.

Profiles are intentionally small:

- `image-ai-video`: Image and AI Video only. Video Production and Gaming
  Playable are unreachable from Web and API.
- `full`: all four products. Use only after a separate approval.

Feature work can continue in short-lived `feature/video-production` and
`feature/gaming-playable` branches. Freeze a reviewed candidate in a short
`release/<release-id>` branch, merge it after approval, and create the matching
annotated Git tag.

## Create and review a release

From a clean, committed release checkout:

```bash
node scripts/release-manifest.mjs create image-ai-video linglong-ai-video-v1.0.0-rc.1
pnpm run release:validate -- releases/linglong-ai-video-v1.0.0-rc.1.json
```

Replace `rollback_release_id` and add approvals in the generated manifest, then
commit **only that manifest** as the release-record commit. It records the
preceding clean source commit; deployment verifies that no product code changed
between that source commit and the release-record commit. Attach a completed
[AI Committee review](ai-committee-release-review.md) to the release process.

Before deploy, add one `approvals.records` entry for each required role, for
example `{ "role": "AI Committee", "reviewer": "name", "decision": "approved", "date": "YYYY-MM-DD", "evidence": "docs/..." }`.
Deployment refuses a manifest without all required approvals.

## Deploy and roll back

Deploy only from the manifest's exact clean checkout:

```bash
./deploy.sh --manifest releases/linglong-ai-video-v1.0.0-rc.1.json
```

The deploy script validates the manifest and checkout, builds/pushes API and
Web images with the release ID tag, and refuses to overwrite an existing image
tag. Capture Artifact Registry digests and Cloud Run revisions in the review.

To roll back, check out the prior approved release tag and deploy its manifest.
Cloud SQL migrations must be backwards-compatible until the observation window
for the new release ends.
