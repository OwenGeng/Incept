# Video Production maturity register

> Status baseline: 2026-09-11
> Purpose: evidence-backed implementation register, not a second product spec.

## Source of truth

- Desired workflow and data contract: [LinglongLab Video Production Workspace](linglonglab-video-production-workspace.md).
- Current navigation and product boundary: [Video Production product design](video-production-product-design.md).
- Active project route: `apps/web/app/video-production/projects/[productionId]/page.tsx`.

Status vocabulary:

- **Verified** — an active route and tested behavior prove the user outcome.
- **Partial** — a real path exists, but a required hand-off, control, or
  durable record is absent.
- **Planned** — specified but not proven in the active product.
- **Unknown** — needs targeted code or runtime verification.

## Baseline scorecard

| Capability | Status | Evidence | Smallest meaningful completion slice |
| --- | --- | --- | --- |
| Canonical project workspace | Partial | The active route renders `VideoProductionWorkspace`; a separate legacy `components/incept/VideoProductionView.tsx` also remains. | Establish the active workspace as the sole user-facing surface; migrate or explicitly isolate legacy code. |
| Create project, edit brief, attach a reference | Partial | The active workspace saves title/brief and lets the creator attach media as Reference, Product, Brand, Logo, Character, Background, or Audio. | Add explicit per-shot asset binding/review rather than relying on the project-level asset pack alone. |
| Editable shot plan and gated generation | Partial | Copilot can build shots; the UI exposes Keyframe and, after a keyframe exists, Generate for a shot. | Persist and surface approval state, job progress/failure/retry, and an immutable input manifest. |
| Take review and selection | Partial | The active workspace now previews each generated take, runs the advisory Edit Reviewer, persists an explicit `selected_video_asset_id`, and only enables a first-cut render after every included shot has a selection. Generation no longer auto-selects its first candidate. | Persist producer-authored rejection/approval notes and selection history alongside the existing advisory review. |
| Non-destructive editing | Partial | The active workspace persists selected takes, inclusion, trim boundaries, transitions, and deterministic subtitle/logo overlays before rendering. | Add storyboard reordering and a visible edit revision/history view. |
| QA and delivery | Partial | The workspace exposes final delivery preview plus the backend’s persisted QC status/issues after assembly. | Add per-check remediation links, render progress/polling, poster export, and an attached delivery manifest. |
| Repair and CTV | Planned | New-project intents are represented in UI, while the product design requires their specialized renderer/compositor before they are called a finished export. | Wire one intent end-to-end to the canonical project, then expose accurate readiness. |
| Prompt/orchestration quality | Unknown | Active role prompts and a dedicated prompt-review skill exist; no fresh runtime audit is included in this register. | Run the dedicated prompt review only before changing active prompts or orchestration. |

## Priority order

### P0 — Select takes as durable production decisions

This is the earliest missing hand-off after generation. Implement a take record
with preview, generation input provenance, review state, rejection reason, and
one explicit selected take per shot. A reload must retain the selection.

**Acceptance path:** create a project → make a shot plan → generate two takes
for one shot → review them → select one → reload → see the selected take and
its source/keyframe/prompt manifest.

**Slice 1 implemented:** the active workspace provides preview and explicit
selection controls, uses the existing `selected_video_asset_id` persistence,
and blocks the renderer from substituting the first generated candidate. The
remaining work is durable producer-authored review notes and a targeted
end-to-end API/UI test of the acceptance path.

### P1 — Edit revision and deterministic first cut

Create a durable edit revision from selected takes. Its source should make
shot order, trim bounds, audio/overlay references, and output preset explicit;
the renderer must consume this revision rather than infer a result from the
latest generated assets.

**Acceptance path:** select takes for all required shots → arrange/trim them →
render a first cut → reload → reproduce the same render inputs.

**Slice 1 implemented:** the active Edit view can persist trim bounds,
transitions, and deterministic subtitle/logo overlays before it queues a
selected-take first cut. Delivery preview surfaces the saved QC result once the
renderer has completed. Remaining work is explicit reordering and a revision
history view.

### P2 — QA gate and delivery record

Add a human-readable and machine-readable QA report. It should test source
availability, duration, ratio, valid output, black/duplicate-frame signals,
and visibility/legibility checks where deterministic analysis is possible.
Delivery is eligible only when required checks pass or an authorized override
is recorded.

### P3 — Asset pack and continuity enforcement

Classify attachments as Brand, Product, Character, UI, Reference, Generated,
or Audio. Bind approved assets/keyframes to shot cards and record their exact
revision. This is the prerequisite for reliable brand and character
continuity.

### P4 — Specialized outcomes

Build Repair, CTV, and Playable-to-Video as explicit project intents with
dedicated but shared manifests, jobs, QA, and delivery records. Do not create
parallel project stores or a separate delivery path.

## Review cadence

Run `$video-production-continuous-review` before a Video Production slice,
after its implementation, and before release. It should update this register
only with verified evidence and choose the next earliest blocking hand-off.

Use `$video-production-prompt-review` only for role-prompt or active
orchestration changes; it does not substitute for this product review.
