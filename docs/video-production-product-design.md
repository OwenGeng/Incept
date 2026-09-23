# Video Production product design

## Product boundary

Video Production is the one product for creating, repairing, reviewing, and
delivering video. It replaces all user-facing Video Workflow, legacy Video
Production, and OpenVideo entries. Image and GamingPlayable remain separate
products.

The legacy video modules remain internal compatibility adapters: they retain
existing project records and generation endpoints, but do not define the new
navigation or terminology.

## Information architecture

- **My videos** — the project hub. It lists real Video Projects and their
  status, and provides the only primary creation entry.
- **New video** — a short, non-billable setup flow with three outcomes:
  Generate a new ad, Repair an existing video, or Compose for CTV.
- **Project workspace** — the single place to edit the brief, attach project
  assets, speak with Copilot, review the Shot Plan, queue keyframes/takes, and
  inspect delivery state.
- **Assets** — a read-only view of shared workspace assets. Project-specific
  attachment happens in the Project workspace so the relationship is explicit.
- **Delivery & QA** — a real project-status view that separates delivered
  projects from projects still needing review.

There is intentionally no Template item yet. A navigation item is only shown
when the product can save and fork a real Video Project template without
sharing a creator's private assets.

## Creation flow

1. The creator selects an outcome and provides title, duration, format, and a
   brief. This creates a real Video Project but does not call a model.
2. In the Project workspace, the creator attaches references. They become
   Project Assets and are sent with later Copilot requests.
3. The creator asks Copilot to build an editable Shot Plan. Copilot updates
   the existing project state; the creator can review every shot.
4. The creator requests a keyframe, then explicitly requests a video take for
   a particular shot. These are the first billable generation actions.
5. The creator reviews takes and proceeds to Delivery & QA. A final delivery
   remains linked to its source project.

## Safety and quality rules

- Creating a project, saving a brief, or attaching assets never starts a
  generation job.
- Generation controls describe the precise action and target shot. They remain
  disabled until their prerequisites exist.
- Copilot updates the current Video Project only. It does not delete or replace
  a Take automatically.
- The Repair and CTV modes are first-class project intents. Their specialized
  rendering/composition tools must be wired to the same project record before
  being advertised as a finished export capability.

## Acceptance checklist

- `/` exposes exactly Image, Video Production, and GamingPlayable.
- `/incept` is Image-only; it exposes neither Video Workflow nor the legacy
  Video Production workspace.
- `/openvideo` redirects to `/video-production`.
- A creator can create a Video Project, reload it, save its title and brief,
  attach an image/video/WebP reference, and see it in My videos.
- A creator can ask Copilot to build a Shot Plan and can queue a keyframe or
  video take only from a selected shot.
- My videos, Assets, and Delivery & QA each use real API data and give an
  explicit empty or failure state.
- Frontend type-check/build and targeted video API tests pass before release.
