# Linglong Video Production rebuild

## Product boundary

Linglong Video Production is an internal production system for commercial video,
original short drama, video remediation, and CTV composition. It is not a novel
adaptation product. It is implemented from Linglong-owned code and design work;
external products may inform capability research but their source, copy, visual
assets, provider configuration, and branding are not imported.

## Locked operating rules

- Output types: commercial ads, original short drama, video remediation, and CTV.
- Deliverables: final MP4, QA report, and project source manifest. External-editor project drafts are out of scope.
- Expensive actions: batch generation and final delivery require an explicit human
  confirmation. A review recommendation can never select a take or deliver a cut.
- Existing Video Production projects remain readable. New projects use the rebuilt
  workflow and are never silently migrated or overwritten.
- Product identity: Linglong branding and the existing Linglong light-workspace UI.
- Provider configuration: model IDs, endpoints, credentials, and cloud locations
  remain owned by the existing configuration. The UI must never infer or change
  them. The intended generation stack is Google Gemini OmniFlash 1.1 and Veo 3.1,
  subject to the exact values already configured by the platform owner.

## Workflow contract

1. **Intake** — define audience, market, objective, output specification, claims,
   constraints, and source assets.
2. **Creative** — create and approve the concept, beat map, copy, and production
   contract before irreversible media generation.
3. **Design system** — build reusable product, character, location, logo, and
   lighting references. Approved assets become continuity inputs, not decoration.
4. **Storyboard** — maintain an editable, ordered shot plan whose frame, camera,
   action, copy, transition, and asset bindings are inspectable.
5. **Generate** — generate keyframes before motion; preserve all takes and their
   lineage; never replace a selected take on regeneration.
6. **Review & edit** — review takes as advice, make the human take selection
   explicit, add deterministic subtitle/logo/store overlays, and make non-
   destructive trim decisions.
7. **Deliver** — run delivery checks, create the final MP4 with its QA report and source manifest,
   then retain the full project lineage for revisions and audits.

## Definition of functional parity

The rebuilt product is functionally comparable in the supported boundary only if
an operator can complete each workflow above after a refresh, cancel an in-flight
task where the provider supports it, inspect a failed task and its recovery path,
reuse approved assets across shots, and deliver an auditable final cut without
losing historical takes or prior project state.

Features specific to novel ingestion, chapter extraction, and novel-to-episode
adaptation are intentionally excluded.
