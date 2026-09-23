# P-04 through P-13 · Production-chain audit

**Date:** 2026-09-22
**Scope:** script, continuity assets, storyboard, generation, audio/edit,
review, delivery, recovery, audit and shared assets.
**Method:** Linglong active UI/API/persistence inspection, plus the reference
product's public end-to-end workflow description and observable workspace
surfaces. No reference source is used as implementation material.

## Reference baseline

The reference's published user-facing workflow establishes this observable
production shape:

input or approved script/product materials → content planning → reusable
characters/scenes/props → structured script/episodes → storyboard → video and
audio candidates → final composition, QA and owned delivery.

Linglong retains the same broad operator chain only for commercial ads,
original short drama from an original brief or supplied script, repair and CTV.
Novel ingestion and novel-to-episode adaptation are excluded.

## Evidence-backed ledger

| ID | Capability | Linglong evidence | Status | Earliest blocker / risk | Smallest viable fix |
| --- | --- | --- | --- | --- | --- |
| P-04 | Editable script and scene plan | Persisted script model has revision, draft/locked status, beats/scenes, brand rules and risks; the workspace now exposes assistant draft, editable working copy, explicit save and confirmed lock-to-storyboard | Partial | The visible revision number is not yet a browsable/forkable revision history; hand edits to the raw working copy do not regenerate the structured scene data automatically | Add a revision timeline and an explicit “restructure this edited draft” action before lock. |
| P-05 | Reusable visual continuity assets | Design packs persist roles, source modes, selected/approved assets, status and failure reason; the workspace now shows every reusable pack with preview, role, linked-scene count, approval count and durable failure reason | Partial | The board is inspection-first: creating, selecting and recovering a pack still live outside this active surface | Add direct pack creation, candidate selection and retry/recovery controls to the board. |
| P-06 | Ordered storyboard and shot plan | Shots persist order, timing, prompts, continuity, transitions, modes and asset bindings; the workspace now creates, edits, moves and deletes storyboard frames through the durable shot APIs | Partial | No dedicated approval checkpoint or drag board yet; continuity/state bindings are still not directly editable in the active plan | Add a plan-approval checkpoint and direct continuity binding controls. |
| P-07 | Keyframe and video generation | Explicit shot-level keyframe and take endpoints exist; exact source signatures, variants and stale-take flags persist; workspace now re-reads persisted job IDs and shows status/progress | Partial | Retry/failure remediation is still the original shot action rather than a dedicated operation history | Add explicit failure reason and retry history per operation. |
| P-08 | Audio, captions and deterministic overlays | Audio plan, cue sheet, soundtrack generation, edit overlays and timeline fields persist; active workspace lets the team prepare a reviewable audio plan, separately queue soundtrack generation, and add/remove timed deterministic text overlays | Partial | Cue-by-cue audio editing and asset-backed logo/image overlays remain absent | Add cue-level audio editing and asset-backed overlay attachment; keep all overlays separate from generative video. |
| P-09 | Human take review and non-destructive edit | UI renders candidates and explicit Select take; review endpoint advises but does not select; the active workspace now saves selected-take inclusion and non-destructive trim in/out decisions | Partial | Stale-take decision and detailed review findings are not yet made visible as structured editing prompts | Render take-staleness and review findings in the edit decision panel. |
| P-10 | QA and delivery | Final asset/render job, QC fields, delivery route and render endpoint exist; delivery exposes selected-take count, QA issues, final-file link, source manifest and downloadable machine-readable QA report | Partial | There is no canonical UI QA acceptance path or rendered-project reopen evidence yet | Add an owned QA acceptance checklist and canonical UI reopen test. External-editor project drafts are explicitly out of scope. |
| P-11 | Failure, cancellation and resume | Copilot and design-generation cancellation endpoints exist; persisted keyframe/take/render job IDs rehydrate as workspace operation cards with progress and Cancel; selected-shot failures now expose durable job messages and retry the same explicit target | Partial | Retry lineage and remediation are not yet rendered for every operation type (design, audio and render) | Add operation-specific retry lineage and remediation for every remaining job owner. |
| P-12 | Usage, lineage and audit | Production record retains revisions, conversation, design/shot bindings and render linkage; global usage API exists; delivery manifest exports selected takes, source assets and QA state | Partial | No project-scoped activity/usage surface or immutable decision log | Add project activity log and usage summary derived from persisted task/asset lineage. |
| P-13 | Shared asset library and project attachment | Shared asset page lists assets and now attaches an asset to a chosen project with an explicit role in one project update | Partial | Project usage and source/right notes are not yet visible; no reopen proof | Add usage list/source metadata and an attach/reopen acceptance test. |

## Chain health

| Hand-off | Current state | Why it is not complete |
| --- | --- | --- |
| Brief → asset manifest | Partial | Assets can be attached/classified in the shared library; usage and reopen proof are still missing. |
| Asset manifest → approved script/shot plan | Partial | Durable models and agent APIs exist, but no explicit UI approval journey joins them. |
| Approved plan → keyframe → take | Partial | Backend targets a concrete shot, but UI does not make plan approval/preflight/recovery durable and visible. |
| Take → selected take → edit revision | Partial | Selection is explicit, but edit decisions and review findings are not operable in the active workspace. |
| Edit → QA → delivery | Partial | Delivery exposes final-file link, QA state, QA report and source manifest, but an owned QA acceptance/reopen path is not yet proven. External-editor project drafts are excluded. |

## Prioritized fixes

1. **P-13 asset manifest vertical slice.** It is the earliest missing hand-off:
   select a shared asset → assign an owned role → save to project → reopen →
   bind it to a shot.
2. **P-04/P-06 approved plan vertical slice.** Edit script and shots → save
   revision → explicitly approve → unlock keyframe operation.
3. **P-07/P-11 operation recovery.** Every queued generation must survive
   refresh with target, progress, failure, retry and cancel.
4. **P-09/P-10 edit and delivery.** Select takes → save edit revision → QA →
   final artifact and manifest.
5. **P-12 audit.** Add the project activity and usage view once the above
   actions produce durable events.

## Release gate

No row in this document can become Verified from server models or a visible
button alone. Each requires a canonical UI happy path, refresh/reopen proof,
empty/failure proof, permission proof where relevant, and retained lineage to
the next hand-off.
