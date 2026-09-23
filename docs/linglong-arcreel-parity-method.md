# Linglong Production · High-fidelity parity method

## Decision

Linglong Production will be a **clean, independently implemented internal
product**. ArcReel is a product-behaviour reference for the supported production
workflow; it is not a source-code template.

The target is high fidelity in:

- information architecture and operator flow;
- interaction states, review gates, recovery and export results;
- functional completeness within Linglong's agreed scope;
- visual density and hierarchy, expressed through Linglong's Image-module light
  design system.

The target is not pixel-identical visual expression, copied product wording,
ArcReel branding/assets, or source-level equivalence.

## Why the comparison is not a line-by-line code diff

A code diff tells us how ArcReel implemented a feature, not the observable
contract an operator needs. Using it as an implementation recipe would also
undercut the clean-room boundary for Linglong's own code.

Instead, the team will record a **black-box capability contract** for each
operator journey:

1. Start with an observable action in the reference product or its user-facing
   documentation.
2. Write Linglong's own requirement, data contract, screen state and acceptance
   criteria in this repository.
3. Implement only from that Linglong-owned specification.
4. Run the same scenario in both products and compare the resulting state,
   rendered output, recovery behaviour and export.
5. Save evidence (screenshots, test fixtures and output manifests) under
   Linglong's project records.

The implementation owner must not copy ArcReel source, translations, icons,
logos, fixtures, prompts, CSS values, component structure, or data migrations.
ArcReel's AGPL license and NOTICE remain attached to its repository; this is a
product-research workflow, not a relicensing mechanism. This document is an
engineering policy, not legal advice.

## Scope lock

| Included | Explicitly excluded |
| --- | --- |
| Commercial advertising production | Novel ingestion and chapter extraction |
| Original short drama from an original brief or supplied script | Novel-to-episode adaptation |
| Video remediation | ArcReel code, visual assets, branding and copy |
| CTV composition and delivery | Changing user-owned model IDs, endpoints or cloud locations |
| Approved asset reuse, generation, review, export and audit history | Automated take selection or delivery without human confirmation |

## The parity ledger

Every row becomes an issue-sized unit with a linked implementation PR, test
fixture, Linglong screenshot and evidence from the reference workflow.

| ID | Operator capability to match | Linglong status | Definition of done |
| --- | --- | --- | --- |
| P-01 | Project library: search, status filters, recent work and project creation | In progress | Library lists persisted projects, filters are data-driven, and every result opens the correct project. |
| P-02 | Project intake and production brief | Partial | Operator can define commercial/short-drama/remediation/CTV intent, audience, market, duration, aspect ratio, claims, constraints and source assets. |
| P-03 | Production stages and resumable progress | Partial | A project visibly advances through direction, script, design, storyboard, generate, edit and delivery; refresh never loses state. |
| P-04 | Script and scene plan | Partial | Scenes can be inspected, reordered and corrected before media work; original short drama is supported without novel adaptation. |
| P-05 | Reusable characters, environments, props, product and brand assets | Partial | Approved visual state can be bound to multiple shots and provenance is visible. |
| P-06 | Storyboard and shot planning | Partial | Ordered shots expose frame intent, camera, action, dialogue/copy, transition, timing and bound assets. |
| P-07 | Image/keyframe and video generation | Partial | A generation has explicit inputs, provider job status, result lineage, retry/failure state and no silent overwrite. |
| P-08 | Audio, captions and deterministic overlays | Partial | Voice, subtitle, logo and store overlays are reviewable and separable from generative media. |
| P-09 | Human review, take selection and non-destructive editing | Partial | All takes remain visible; an operator explicitly selects a take and can revise without destroying prior outputs. |
| P-10 | Delivery and final handoff | Partial | Deliverable status, final MP4, QA report and source manifest are discoverable with a delivery checklist. External-editor project drafts are excluded. |
| P-11 | Failure, cancellation and resume | Needs audit | Cancel/retry/recover paths expose enough task state for an operator to act after refresh. |
| P-12 | Usage and production auditability | Needs audit | Project history records task inputs, outputs, selection decisions, operator confirmation and relevant costs/usage. |
| P-13 | Asset library and reuse | Partial | Assets can be found, previewed, traced to origin and attached to a project or shot without copying files. |
| P-14 | Visual system | In progress | Lobby, workspace, new-project, library and delivery share the approved white / light-gray / charcoal Image-module system. |

“Partial” is not a parity claim. It means existing code or data has some
foundation, but has not passed the scenario below.

Detailed, evidence-backed reviews are stored in `docs/parity-reviews/`. P-01
through P-03 cover the project library, project intake and workspace state;
P-04-through-P-13-production-chain-audit.md covers the remaining supported
production hand-offs and their current blockers.

## Required evidence for each ledger row

Each row must carry all of the following before it is marked complete:

- **Scenario:** a short numbered operator flow with an explicit starting state.
- **Linglong spec:** owned terminology, screen fields, API/data fields and
  permitted error states.
- **Acceptance checks:** deterministic expected result after each action.
- **Reference notes:** only observable behaviour, screenshots and public
  documentation links; no copied code or source-derived implementation notes.
- **Automated test:** API/unit test where applicable, plus a browser journey for
  user-visible flow.
- **Visual evidence:** matching viewport screenshots for the Linglong page master
  and final implementation.
- **Recovery evidence:** refresh during an in-flight or failed operation, if the
  feature performs a task.

## Comparison order

The order prevents a polished UI from hiding a broken production chain.

1. P-01 and P-14 — library, navigation and page-master fidelity.
2. P-02 and P-03 — intake, project state and resumability.
3. P-04 through P-06 — script, assets and storyboard as the production source
   of truth.
4. P-07 through P-09 — generation, review and edit control.
5. P-10 — delivery output and handoff.
6. P-11 through P-13 — recovery, audit and asset reuse hardening.

At the end of each group, run the complete supported production scenario:

```
Create project → confirm brief → plan scenes → approve reusable assets
→ approve storyboard → generate keyframes/video → review and select takes
→ apply overlays/edit → run delivery checks → export → reopen project
```

## Visual high-fidelity procedure

Visual parity is measured screen-by-screen, not by subjective recollection.

1. Freeze a Linglong page master before implementing a screen.
2. Capture the reference screen at the same viewport and state.
3. Compare hierarchy, section order, density, spacing rhythm, responsive
   breakpoints, empty/loading/error states and interaction feedback.
4. Apply Linglong's fixed visual rules: white canvas, `#FAFBFC` secondary
   surfaces, `#F6F8FB` muted fills, `#171A20` primary buttons,
   `#E6E8EC` borders, and blue only as a secondary status accent.
5. Do not copy reference logos, illustrations, fonts, text, gradients or visual
   assets. When a reference uses a branded visual, substitute a Linglong-owned
   component with the same information role.
6. Record the resulting screenshot in `docs/page-masters/` and link it from
   the relevant ledger item.

## Current implementation checkpoints

- The approved production-lobby visual master is
  `docs/page-masters/LINGLONG-PRODUCTION-LOBBY-IMAGE-LIGHT-v1.png`.
- The current lobby implementation is
  `apps/web/components/video-production/VideoProductionHub.tsx`.
- The production header is
  `apps/web/components/video-production/VideoProductionShell.tsx`.
- The approved New Project master is
  `docs/page-masters/LINGLONG-PRODUCTION-NEW-PROJECT-IMAGE-LIGHT-v1.png`.
- The approved Project Workspace master is
  `docs/page-masters/LINGLONG-PRODUCTION-WORKSPACE-IMAGE-LIGHT-v1.png`.

## Change-control rules

- No external API/model/location configuration changes are part of parity work.
- Every expensive generation or delivery step keeps an explicit human
  confirmation.
- A new capability may not be marked complete solely because the screen exists;
  it must meet its scenario, recovery and evidence requirements.
- If a reference capability depends on novel adaptation, it is recorded as
  excluded rather than recreated under a new name.
