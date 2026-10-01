# Linglong Lab · Studio — Progress Tracker

> Weekly-update file. Add new dated entries to the **Progress Log** (newest on top, don't delete history). Update the **Feature Status** table in place when something ships or changes state. Sources this file is grounded in: `apps/web/app/docs/studio/page.tsx` (in-app docs, code-derived), `docs/linglonglab-current-state.md` (deeper implementation notes), `apps/api/app/incept/*`, `apps/web/components/incept/*`.

## What it is

Studio is LinglongLab's creative-generation workspace inside the Linglong platform: image generation, video generation, and the Kakao Bizboard compositor. Users upload source material, pick a flow, and get generated ad creative saved into a shared asset Library.

## Architecture

- **Frontend:** Next.js (`apps/web`), main surfaces under `apps/web/app/incept/` and `apps/web/components/incept/` (`CreateImageView.tsx`, `Workspace.tsx`, `KakaoFlow.tsx`).
- **Backend:** FastAPI (`apps/api`), LinglongLab-specific logic under `apps/api/app/incept/` (`store.py`, `prompt_builder.py`, `composite.py`, `gif_generator.py`, `models.py`), exposed via `apps/api/app/routers/incept.py`.
- **Shared types:** `packages/linglonglab-shared/src/index.ts`.
- **Models in use:** Gemini 3.1 Flash / GPT Image 2 (image), Veo 3.1 Fast (video).
- **Jobs:** generation runs as background jobs, polled by the frontend every 2.5s; each generation belongs to a resumable thread.

## Feature Status

| Feature | Status | Notes |
|---|---|---|
| Create Image — Resize | Live | Per-size Gemini generation, direct prompt-per-size pipeline. `728x90` is special: generated on a hidden `728x180` canvas then split into two `728x90` outputs. Max 10 source images. |
| Create Image — Theme Create | Live | 2 active sub-modes: **Style Modify** (keep Image 1 layout, change style) and **Style Transfer** (Image 1 = content, Image 2 = style reference). A third mode, Asset & Text Replace, was removed from the live UI; a backend enum value remains for historical records only. Selected outputs can be saved as a reusable preset. |
| Create Image — Kakao | Live | Entry point into the full Kakao Bizboard flow (see below). |
| Create Image — Remediation | Live | Upload a flagged/risky creative, generate compliant variants. Max 10 source images. |
| Create Video — Image to Video | Live | Veo 3.1 Fast, 16:9 or 9:16, 4/6/8s duration, 1–2 variants, audio on/off toggle. Budget check blocks submit if request would exceed configured budget. |
| Create Video — Video Remediation | Live | Same control surface as Image to Video, source is a flagged video. |
| Kakao Bizboard compositor | Live | Fixed `1029×258` output. 4-step flow: Upload & Clean → Confirm → Builder (icon/subtitle/main copy/gacha-disclosure) → Create. Composition is deterministic (not freeform AI layout), done client-side via `kakao-compositor.ts`. |
| GIF generation | Live | Deterministic Python animation pipeline (not AI frame-by-frame). Subtle full-frame cinematic sweep / breathing motion from one base image. `320x480` supported. |
| Asset Library | Live | Generated vs Uploaded tabs; filters by media type + video-specific filters (mode/aspect/duration/audio) + text search; grid (drag-select) and list views; multi-select batch download/GIF/Kakao/delete. |

## Key Files

- `apps/web/components/incept/CreateImageView.tsx`
- `apps/web/components/incept/Workspace.tsx`
- `apps/web/components/incept/KakaoFlow.tsx`
- `apps/web/lib/incept-api.ts`
- `apps/web/lib/kakao-compositor.ts`
- `apps/api/app/incept/store.py` — per-flow generation branching (`run_generation_background()`)
- `apps/api/app/incept/prompt_builder.py` — prompt templates per flow/size (`build_theme_create_style_modify_prompt`, `build_theme_create_style_transfer_prompt`, resize size-family templates)
- `apps/api/app/incept/composite.py` — `728x180 → two 728x90` split logic
- `apps/api/app/incept/gif_generator.py`
- `apps/api/app/incept/models.py`
- `apps/api/app/routers/incept.py`

## Known Caveats / Open Questions

- `728x90` yielding two outputs per request is non-standard — some downstream UX may still assume 1 requested size = 1 output.
- Full end-to-end browser QA of all 3 Theme Create modes, Kakao clean+compose, and GIF output has not been recently re-verified (per `docs/linglonglab-current-state.md`); Python syntax/targeted checks were done, not full TS compilation.
- Whether Theme Create should keep the small helper fields for a future "Asset & Text Replace"-style mode, or stay compressed to 2 modes, is still an open decision.
- Whether GIF should stay GIF-first or start exposing animated WebP/MP4 is still an open decision.

## Progress Log

_(newest first — add new entries above the previous one, don't rewrite history)_

### 2026-07-24 — baseline snapshot
- No Studio code changes made in this session; this entry establishes a baseline snapshot of Studio's current state (Create Image w/ Resize/Theme Create/Kakao/Remediation, Create Video, Kakao Bizboard compositor, GIF generation, Asset Library) as documented in `apps/web/app/docs/studio/page.tsx` and `docs/linglonglab-current-state.md`.
- Note: `docs/linglonglab-current-state.md` predates the Create Video and Remediation flows — those two are documented here for the first time based on current in-app docs and should be treated as the more current source going forward.
