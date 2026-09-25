# LinglongLab Video workspace

This directory contains the restored Vue video workspace used by the Incept
web application. It is compiled as static assets and served by the existing
Next.js service at `/video-app`; `/video` embeds that build without adding a
third Cloud Run service.

The browser API remains same-origin under `/api/*`. Next.js forwards only the
allowlisted video routes to the FastAPI compatibility router at
`/video-legacy/api/*`. The video entry intentionally has no login screen and
uses the fixed internal workspace identity `local@linglonglab.internal`.

Runtime model names, providers, locations, and credentials are never stored in
the Vue bundle. FastAPI exposes the deployment-managed Vertex model catalog and
executes text, image, and video requests through the existing Incept backend.
In production, the existing Cloud Run deployment mounts the configured video
bucket at `VIDEO_STUDIO_DATA_DIR`, so the Vue filesystem-shaped project API is
durable without a second storage service or duplicate object writes. Project
and canvas JSON metadata also use the existing video-studio metadata
repository/database path.

## Local commands

From the repository root:

```sh
pnpm prepare:video-vue
pnpm dev:web
```

Or from this directory:

```sh
pnpm build
pnpm sync
pnpm typecheck
```

The generated files under `apps/web/public/video-app` and `build/` are ignored;
the production web Dockerfile rebuilds them from source.

The upstream MIT license required for retained third-party source is preserved
in `THIRD_PARTY_LICENSE` and the repository-level `THIRD_PARTY_NOTICES.md`.
