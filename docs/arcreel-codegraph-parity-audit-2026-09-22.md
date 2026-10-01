# ArcReel → LinglongLab Video Production CodeGraph parity audit

> Date: 2026-09-22
> Method: static responsibility audit using the local CodeGraph indexes and the
> source-coverage ledger. This is not a runtime/UAT result and must not be read
> as a claim of full product equivalence.

## Decision

**No — Video Production is not yet functionally aligned with all applicable
ArcReel capabilities, and a zero-omission claim would be false.**

The useful target is an independently implemented LinglongLab commercial-video and
original-short-drama workspace. Novel adaptation and Jianying/CapCut export are
excluded by product decision. This document records behavioural responsibilities
only; it is neither a source porting guide nor permission to copy ArcReel code,
copy, visual assets, prompts, schemas, or component structure.

## Audit evidence and bounds

The two local indexes were current at audit time:

| Indexed repository | Files | Nodes | Edges |
| --- | ---: | ---: | ---: |
| `ArcReel` | 2,182 | 50,922 | 170,343 |
| `LinglongLab` | 3,997 | 77,205 | 256,129 |

The reference inventory contains 2,127 executable source paths. Of those, 228
are explicitly excluded local/reference tooling and 1,899 remain active
product/test scope. The coverage ledger has automatically classified 2,095
paths, but only 32 paths have a recorded human responsibility audit. Automatic
classification and graph connectivity find files and dependencies; they do not
prove that the target has the same user-visible contract.

Reproduce the inventory check with:

```sh
python3 scripts/generate_arcreel_coverage_matrix.py --verify
codegraph status ArcReel
codegraph status .
```

The complete denominator and work queue are in
[`arcreel-to-linglonglab-coverage-matrix.md`](arcreel-to-linglonglab-coverage-matrix.md),
[`arcreel-source-file-coverage.tsv`](arcreel-source-file-coverage.tsv), and
[`arcreel-audit-clusters.tsv`](arcreel-audit-clusters.tsv).

### Terms used below

- **Present:** an LinglongLab-owned UI/API/domain path implements the core operator
  outcome. It is not a runtime-verification statement.
- **Partial:** the core outcome exists but important state, recovery, scale, or
  operator controls are missing.
- **Absent:** no corresponding LinglongLab-owned capability was found.
- **Deliberate divergence:** a difference is acceptable only if the product
  scope intentionally limits it; it is still a parity gap if the goal is
  literal ArcReel feature parity.
- **Excluded:** explicitly outside this product, not silently counted as done.

## Capability findings

| Responsibility cluster | ArcReel responsibility surfaced by CodeGraph | LinglongLab evidence found | Status | Remaining gap / decision |
| --- | --- | --- | --- | --- |
| Project library and intake | Project search, filtering, creation, project state and workspace routing | `/video-production`, `/new`, persisted project create/update/fork/archive/restore contracts | Partial | Dedicated query/store semantics, full empty/search/status/error state matrix, project health/repair read model and import/export state remain incomplete. |
| Project archive package | Versioned project archive export/import with archive validation and recovery protections | Archive/restore of an LinglongLab project exists; generic asset ZIP download exists | Partial | Asset ZIP download is **not** project archive parity. There is no project package export/import, archive manifest migration, or safe import/recovery path. |
| Asset library | Asset create, metadata, derivatives, previews, conflict handling, multi-select and attachment workflows | Upload, project attachment, asset role and rights/provenance notes | Partial | No complete metadata edit/delete lifecycle, derivative/version lineage, duplicate-conflict resolution, server-paginated/multi-select attach flow, or equivalent previews. |
| Original short-drama planning | Episode-aware scripts, episode/scene/shot sequencing and dependency plans | Original short-drama mode, scripts and shots are represented in the production domain | Partial — priority | Novel adaptation is excluded, but retained short-drama production still needs explicit episode planning/state, episode-to-shot progression and durable dependent-job sequencing. |
| Script review | Structured draft editing, review gates, revision safety and formal confirmation | Editable script, lock, script checkpoints and restore endpoint/UI | Partial | No established concurrent-review/OCC policy, rich review state, script-source import pathway, or equivalent reload/conflict/retry behaviours. Script import is a product choice for original scripts, not novel adaptation. |
| Reference-video analysis | Provider-aware reference projections, duration/reference/audio constraints and analysis state | Reference asset selection and creative-direction fields | Partial | No equivalent reference-video analysis record, capability projection, constraint explanation, or reference-specific recovery/audit workflow. |
| Storyboard and canvas | Scene/shot planning, dependency-aware storyboard generation and interactive workspace controls | Shot CRUD, storyboard approval, design-pack/keyframe-related actions and workspace UI | Partial | No demonstrated equivalent timeline/canvas interaction model, bulk selection/reorder workflow, dependency plan visualization, or recovery of interrupted storyboard batches. |
| Generation operations | Task batches, cancellation, retry, candidate selection, durable task lifecycle and recovery | Per-shot generation controls, candidate/selected-take concepts and cancellation endpoints | Partial | Cancellation alone is not batch parity. Missing an equivalent batch queue/read model, durable lease/restart recovery, operator batch controls and complete retry/failure lineage. |
| Edit, QA and delivery | Non-destructive edit plan, presentation outputs, QA/remediation and delivery records | Edit plan, QA and delivery-oriented production state | Partial | No complete immutable delivery manifest, source artifact/package workflow, remediation lifecycle or demonstrated delivery recovery path. Jianying/CapCut export remains excluded. |
| Usage and event stream | Usage records, task cancellation surfaces, cost attribution and realtime updates | Project event list and EventSource stream, generic job/cancel concepts | Partial | No dedicated per-project model usage/cost ledger, task-batch accounting, subscriber fan-out/backpressure policy or documented reconnect/overflow behaviour. |
| Provider configuration | Provider/model capability selection, provider configuration and safe failure states | Server-owned project model catalogue; browser cannot set credentials, endpoints or regions | Deliberate divergence / partial | This is appropriate if LinglongLab will only use the approved Google providers. It is not ArcReel-equivalent custom-provider/endpoint/credential management. Do not change Google model or location configuration without platform-owner confirmation. |
| Agent runtime | Scoped sessions, action attribution, durable transcripts, replay/reconnect and project memory | Copilot and role endpoints with project actions | Partial | No durable session identity/idempotency model, transcript/replay store, reconnectable execution state, or clear agent-session lineage. |
| MCP | In-process and remote MCP tools with authenticated project-scoped operations | LinglongLab MCP service/transport and a limited production-tool suite | Partial | MCP is present, not absent. Tool coverage, durable job controls, remote operation parity, and deployment/auth proof are incomplete. |
| Persistence and migrations | Durable domain models, migrations and operational recovery rules | Video-production models/store and local persistence paths | Partial | Cloud SQL clean-upgrade/rollback/read-compatibility evidence and migration/recovery policy are not complete. |
| Shared interaction and operations surfaces | Locale readiness, onboarding, global settings, keyboard/loading/error states | LinglongLab shell and component set | Partial | Import ZIP/global usage/settings parity, locale/onboarding, and a formal responsive/accessibility/error-state matrix remain unclosed. |

## What is already available

These should not be reported as missing: project creation with server-owned
model selection, project update/fork/archive/restore, structured script work
and checkpoint restoration, shot creation/editing, storyboard approval,
production role actions, provider capability loading, event-list/stream
endpoints, selected-take/edit/QA/delivery domain fields, and an LinglongLab MCP
surface.

Their presence does not close the partial entries above: each needs the
remainder of its lifecycle and contract before it can be considered comparable
to the corresponding reference responsibility.

## Closure order

For the stated product (commercial video plus original short drama), close the
following before claiming practical capability parity:

1. **Original short-drama production state:** explicit episodes, progression,
   dependencies and recovery between episode, script, shot and generation.
2. **Asset and project portability:** asset lifecycle/selection plus an owned
   project package format if operators must move or recover productions.
3. **Storyboard/generation operations:** batch creation, status, retry/cancel,
   candidate selection, durable restart recovery and lineage.
4. **Workspace review and delivery:** usable storyboard/timeline interaction,
   revision-safe review, immutable delivery manifest and QA remediation.
5. **Operational reliability:** usage ledger, SSE reconnect policy, durable
   agent sessions and task-worker/migration recovery semantics.
6. **Scope decision:** either explicitly retain the Google-only provider
   limitation or build the separate provider-configuration product. The former
   is sensible for LinglongLab, but it must be called a deliberate divergence.

## Completion gate

The product may be called “feature aligned within the agreed scope” only when:

1. Every active responsibility cluster is `present` or explicitly `excluded`.
2. Every one of the 1,899 active source paths has a non-pending disposition in
   the coverage ledger (`mapped` or deliberate `merged`; not merely
   `auto_classified`).
3. Each retained production chain proves LinglongLab-owned UI, API, persistence,
   authorization, refresh and failure/retry behaviour.
4. The two deliberate exclusions (novel adaptation and Jianying/CapCut export)
   remain written down and no unrelated reference capability is silently
   treated as excluded.

Until then, the honest status is **partially implemented, with known material
gaps** rather than “all ArcReel functions are complete.”
