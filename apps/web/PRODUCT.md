# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Performance-advertising creators and producers making short commercial videos.
They need to turn a brief and customer-owned assets into reviewable shots,
selected takes, and a traceable delivery without losing creative control.

## Product Purpose

LinglongLab Video Production is a workspace-first AI commercial-video system. A
single project keeps the brief, source assets, plan, generated takes, edit
decisions, QA state, and final delivery together.

## Positioning

Unlike a one-prompt video generator, LinglongLab makes every billable generation a
specific, reviewable shot operation and keeps the selected-take lineage through
to delivery.

## Operating Context

Creators work through a project workspace: brief and references lead to a shot
plan; approved keyframes lead to takes; reviewed takes lead to an edit and QA
delivery. Work may start as a new ad, a repair, or a CTV composition.

## Capabilities and Constraints

- Creating a project, editing its brief, or attaching assets is non-billable.
- Keyframes and video takes require an explicit action on a particular shot.
- A take is never silently selected, replaced, or deleted.
- The final render must remain attached to its originating project and source
  decisions.
- The active product is under `apps/web/app/video-production/`.
- External model IDs, endpoints, and cloud locations are user-owned ground
  truth and must never be guessed.

## Brand Commitments

Use the established Linglong / LinglongLab identity. Video Production uses a
Linglong-owned production control-room interface, branding, code, content,
and assets.

## Evidence on Hand

- Product workflow: `docs/linglonglab-video-production-workspace.md`
- Current boundary: `docs/video-production-product-design.md`
- Maturity baseline: `docs/video-production-maturity-register.md`
- Workspace interaction reference: https://higgsfield.ai/generate

## Product Principles

1. Ingredients and approvals come before motion.
2. The storyboard and selected takes control production; conversation assists
   decisions but does not replace the workspace.
3. Every significant output is inspectable, replaceable, and traceable.
4. A delivery is a checked production result, never the latest generated file.
