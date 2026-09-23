# ArcReel → Incept independent implementation coverage matrix

> Status: audit baseline — implementation is **not** complete.
> Started: 2026-09-22
> Purpose: make every ArcReel capability traceable to an independently designed
> Incept contract, implementation, and acceptance test. This is an engineering
> coverage ledger, not a source-code porting guide.

## 1. Rules of use

- The ArcReel repository is analysed for observable responsibility, data flow,
  state transitions, failure handling, and integration boundary only. No code,
  string, CSS value, visual asset, tool schema, prompt, or component tree is
  copied into Incept.
- Every executable source file under the inventory roots below must have exactly
  one audit disposition: `mapped`, `excluded`, `merged`, or `pending`.
- A `mapped` file must link to an Incept-owned requirement, target module, and
  automated or browser acceptance evidence. A file can never be marked complete
  solely because a similarly named screen or endpoint exists.
- `excluded` is permitted only for an explicitly out-of-scope operator outcome
  (for example novel ingestion). It is not a shortcut for a missing capability.
- `merged` means multiple reference files map to one deliberate Incept module;
  all source paths, tests, and responsibilities must be named on that module's
  row.
- The final comparison is behavioural: create, edit, approve, queue, recover,
  select, render, QA, deliver, refresh. It must not be a textual or structural
  similarity target.

### Three-layer audit method

The reference repository is too large for indiscriminate, file-by-file deep
reading to be a reliable way to find product gaps. This audit therefore keeps
the exact per-path denominator but separates classification from deep semantic
review:

1. **Automatic complete classification.** Every executable path is assigned a
   product module, responsibility cluster, audit tier and cluster anchor using
   path taxonomy plus the local CodeGraph dependency index. This catches
   unclustered paths immediately; it is not an implementation-equivalence
   claim.
2. **Anchor deep review.** Only files that define an externally observable
   contract, state transition, persistence boundary, task runner, auth rule,
   provider adapter, router or client state boundary are `deep`. The remaining
   runtime files are reviewed as part of their explicit responsibility cluster,
   with the anchor and call paths used to detect exceptional behaviour.
3. **Evidence and reverse-gap audit.** Tests, mocks and fixtures are retained
   as `evidence`, not silently discarded. For every cluster, Incept must show
   owned UI, API, persistence, authorization, refresh and failure/retry
   evidence. A reverse scan of routes, models, stores, task handlers, types
   and tests flags capabilities that appear in ArcReel but have no Incept
   target.

The generated [`arcreel-audit-clusters.tsv`](arcreel-audit-clusters.tsv)
contains the 79 responsibility clusters, their anchors and CodeGraph node
counts. It is an audit work queue, never evidence that a cluster is complete.

## 2. Complete inventory boundary

This boundary makes omission measurable. At audit start the repository contains
1,282 Python files and 617 TypeScript/TSX frontend files. Counts are a snapshot,
not a completion claim. The file list is obtained with:

```sh
rg --files ArcReel/server ArcReel/lib ArcReel/alembic -g '*.py'
rg --files ArcReel/frontend/src -g '*.ts' -g '*.tsx'
```

| Inventory root | Files | Required disposition | Audit owner area |
| --- | ---: | --- | --- |
| `ArcReel/frontend/src/components/canvas/**` | 120 | every file | project workspace, storyboard, timeline |
| `ArcReel/frontend/src/components/pages/**` | 89 | every file | library, intake, assets, settings |
| `ArcReel/frontend/src/components/{ui,layout,shared,workflow,assets,agent,copilot,usage}/**` | 192 | every file | shared interaction and task surfaces |
| `ArcReel/frontend/src/{api,stores,hooks,types,actions,utils,i18n}/**` | 216 | every file | client contracts, state, realtime, localisation |
| `ArcReel/frontend/src/{main.tsx,router.tsx,app-routes.ts,branding.ts}` | 4 | every file | application shell and route policy |
| `ArcReel/server/routers/**` | 43 | every file | HTTP API contract |
| `ArcReel/server/{agent_runtime,media_tools,services}/**` | 85 | every file | agent, tools, presentations and task orchestration |
| `ArcReel/server/{app.py,remote_mcp.py,auth.py,dependencies.py,sse_channel.py,error_handlers.py,cors_config.py,draft_workflow.py,text_generation.py,tool_runtime.py}` | 10 | every file | host lifecycle, auth, SSE and MCP boundary |
| `ArcReel/lib/{project,script,generation,workflow,artifacts,episode,references}/**` | 136 | every file | production domain and durable hand-offs |
| `ArcReel/lib/{db,config,infra,billing,agent}/**` | 84 | every file | persistence, settings, telemetry, queues |
| `ArcReel/lib/{backends,custom_provider,prompts,speech,market,i18n}/**` | 180 | every file | provider abstraction and supporting services |
| `ArcReel/alembic/**` | 55 | every file | schema/migration decision record |

The complete individual-path index is generated at
[`arcreel-source-file-coverage.tsv`](arcreel-source-file-coverage.tsv). A
module can only change from `pending` when every path in its inventory row has
an audit entry. New reference files added during the audit reopen the relevant
row. Regenerate it with:

```sh
python3 scripts/generate_arcreel_coverage_matrix.py
python3 scripts/generate_arcreel_coverage_matrix.py --verify
```

The generator deliberately writes only relative file paths and Incept-owned
audit fields. It does not copy source, strings, schemas, prompts, or visual
assets out of the reference repository.

### Quantified audit snapshot — 2026-09-22

| Measure | Count | Meaning |
| --- | ---: | --- |
| executable reference paths in the inventory | 2,127 | fixed denominator for the audit; not a count of product gaps |
| executable reference paths in active product/test scope | 1,899 | total inventory minus explicit local-tooling exclusions |
| automatically classified paths | 2,095 | have tier, cluster and anchor; classification is not equivalence |
| individually responsibility-audited paths | 32 | paths whose behavior and Incept mapping have been recorded by a human |
| deep responsibility nodes awaiting semantic review | 352 | contract-owning anchors: router/state/store/task/auth/provider/persistence boundaries |
| clustered runtime implementation paths | 649 | audited through their owning cluster after its anchors are read |
| retained test/mock/fixture evidence paths | 898 | reverse-check evidence; not a reason to infer a runtime implementation |
| explicitly excluded non-product local tooling | 228 | `.agents`, `.claude` and website tooling; retained in ledger with an explicit exclusion |
| target modules marked partial | 16 of 22 | capability exists in part but has a stated implementation, verification or policy gap |
| implemented but awaiting UAT | 4 of 22 | A-03, A-04, A-14 and A-18 have code/tests but lack the required canonical browser/deployed proof |
| unstarted target modules | 2 of 22 | A-21 interaction primitives and A-22 localisation/onboarding/config states |

The TSV keeps active paths at `pending` while implementation and acceptance
evidence are incomplete. A source path cannot be promoted to `mapped` or
`merged` until the relevant module's entire path group, owned implementation
and acceptance evidence are complete. Its `audit_status` now distinguishes
`auto_classified` from the 32 manually responsibility-audited files. The
non-product exclusions are explicit ledger rows, not omissions.

The verifier fails if the ledger has a missing, duplicated, orphaned, or
unclassified source path. It accepts `pending` during audit, but a release gate
must fail until the relevant path groups have a non-pending disposition and
their mapped requirements have acceptance evidence.

## 3. Incept target boundary

The independent product remains the active Next route family:

```text
/video-production
/video-production/new
/video-production/projects/[productionId]
/video-production/assets
/video-production/delivery
```

Its production chain is:

```text
brief → project asset manifest → approved script / storyboard revision
→ approved keyframe → shot take candidates → selected take → edit revision
→ QA report → delivery + source manifest
```

No model ID, endpoint, credential, or Google Cloud location is changed as part
of this audit. Those values remain configuration owned by the platform team.

## 4. Target module map

| ID | Reference responsibility | Incept-owned target | Current status | Acceptance proof required |
| --- | --- | --- | --- | --- |
| A-01 | app host, auth, route guards, shell | Next route/layout + FastAPI auth boundary | partial | unauthenticated, authenticated, refresh and back navigation |
| A-02 | project library, search, filters, recent work | `video-production/page` + project query contract | partial | search/filter/reopen persisted project |
| A-03 | project creation and intake | `video-production/new` + create contract | implemented — UAT pending | validate, save, refresh, intent-specific state |
| A-04 | project settings, branching, archive | project workspace settings and revision domain | implemented — browser UAT pending | save conflict, fork, archive/recover |
| A-05 | source documents and script review | script revision domain + human review UI | partial | draft, structure, lock, invalidate, reopen |
| A-06 | asset library, upload, provenance, derivatives | asset manifest + object-storage adapter | partial | attach/role/provenance/failure/reopen |
| A-07 | reference video and originality constraints | reference-analysis contract | partial | analysis record, keep/change rules, audit |
| A-08 | workflow plan, episode/scene/shot state | storyboard revision and Shot Card domain | partial | reorder/edit/approve/reopen/history |
| A-09 | keyframes, grids, bridge/end frames | visual-development job contract | partial | explicit target, candidate selection, retry/cancel/lineage |
| A-10 | video tasks, take candidates and recovery | motion job + take review contract | partial | queue/fail/retry/select/reopen |
| A-11 | edit plan, captions/audio/overlays/presentation | non-destructive edit revision | partial | deterministic render inputs and revision history |
| A-12 | QA, delivery and export manifest | delivery record + QA report | partial | gate/failure/remediation/download/reopen |
| A-13 | usage, cost and project event stream | audit ledger + SSE/read model | partial | exact input/output attribution and refresh |
| A-14 | provider catalog/custom endpoints | provider capability adapter | implemented — browser UAT blocked | capability gate, project selection, configuration error state and audit |
| A-15 | authentication, API keys, permissions | Incept role policy | partial | forbidden, delegated-operator and cross-project access tests |
| A-16 | agent sessions and project memory | scoped copilot session | partial | apply/dismiss/action attribution/reopen |
| A-17 | in-process MCP tools | Incept MCP tool service | partial | schema, authorization, idempotency and audit tests |
| A-18 | remote MCP transport and bearer auth | authenticated `/video-production/mcp` transport | implemented — HTTP UAT pending | discovery/auth/tool invocation/error tests |
| A-19 | worker lease, queue, restart recovery | durable job runner abstraction | partial | crash/restart/lease/retry/cancel tests |
| A-20 | database schema/migrations | Cloud SQL-compatible persistence migrations | partial | clean migrate, upgrade, rollback/read compatibility |
| A-21 | operator UI primitives and motion | shadcn/ui components plus Incept tokens | pending | keyboard, disabled, loading, error and responsive states |
| A-22 | localisation/onboarding/system config | Incept product operations surfaces | pending | locale/fallback/first-run/config error states |

## 5. Required appendix row format

Every individual source path receives one row using this schema. The first
appendix is the active audit queue; later appendices close files by module.

| Source path | Symbol(s) read | Responsibility | Inputs / outputs / side effects | Disposition | Incept requirement | Target file(s) | Tests / UAT | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

Status values:

- `pending` — not yet read;
- `auto_classified` — assigned an audit tier, cluster and anchor by the
  reproducible taxonomy/CodeGraph pass; no semantic-equivalence claim;
- `audited` — responsibility recorded, no implementation claim;
- `specified` — mapped to an Incept-owned contract;
- `implemented` — code exists but does not yet prove the contract;
- `verified` — canonical UI/API path, refresh proof, and applicable failure
  path are recorded;
- `excluded` — linked to an approved scope exclusion.

## 6. Module audit order

The order follows the earliest durable hand-off and prevents a polished screen
from hiding a missing production contract.

1. **A-01–A-03:** active shell, library and New Project states.
2. **A-05, A-06, A-08:** script, asset manifest and storyboard revisions.
3. **A-09–A-10:** keyframe and take jobs, selection and recovery.
4. **A-11–A-12:** edit revision, QA and delivery manifest.
5. **A-13, A-19–A-20:** events, audit, durable jobs and persistence.
6. **A-14–A-18, A-22:** provider configuration, auth and MCP surfaces.
7. **A-21:** visual/page-state parity pass at fixed viewports.

## 7. Initial file-level audit queue — A-01 to A-03

| Source path | Responsibility observed | Disposition | Incept target / gap |
| --- | --- | --- | --- |
| `ArcReel/frontend/src/main.tsx` | React bootstrap, auth state restore, locale readiness, global UI setup | audited | Next root/layout uses a different bootstrap; verify equivalent loading and error states. |
| `ArcReel/frontend/src/router.tsx` | client route ordering, protected routes, project workspace route policy | audited | map each creator route to a Next route; current New Project and workspace have no file-level route-state matrix. |
| `ArcReel/frontend/src/components/layout/StudioLayout.tsx` | application chrome, workspace responsive layout and persistent regions | pending | `VideoProductionShell.tsx` needs an explicit shell parity specification. |
| `ArcReel/frontend/src/components/layout/GlobalHeader.tsx` | global search, asset entry, import/create/settings actions | pending | `VideoProductionShell.tsx` has search/assets/create/delivery but lacks a documented action-state comparison. |
| `ArcReel/frontend/src/components/pages/ProjectsPage.tsx` | project library read model and operator actions | pending | `VideoProductionHub.tsx`; compare normal, empty, search and status-filter states. |
| `ArcReel/frontend/src/components/pages/ProjectCard.tsx` | project-card identity, progress and resume actions | pending | `VideoProductionHub.tsx`; current card is an independent design but not yet state-complete. |
| `ArcReel/frontend/src/components/pages/CreateProjectModal.tsx` | project creation input, validation and submit transition | pending | `NewVideoProduction.tsx`; first implementation slice. |
| `ArcReel/frontend/src/stores/projects-store.ts` | project list/query mutation state | pending | `lib/incept-api.ts` plus a dedicated client query/store boundary. |
| `ArcReel/frontend/src/api/transport.ts` | authenticated request, error and streaming transport | pending | `app/api/incept/[...path]/route.ts` and `lib/incept-api.ts`; audit retry/error semantics. |
| `ArcReel/server/app.py` | FastAPI lifespan, routers, worker and transport host | audited | `apps/api/app/main.py`; target a Cloud-ready startup boundary without copying host structure. |
| `ArcReel/server/routers/projects.py` | project CRUD, project-specific data and request validation | pending | `apps/api/app/routers/incept.py` and video-production store; extract a separate owned project API contract. |
| `ArcReel/lib/project/project_manager.py` | central project state operations | pending | `video_production_store.py`; identify missing revision, archive and conflict contracts. |
| `ArcReel/lib/db/models/project.py` | durable project model | pending | `models.py` + persistence migration plan; verify Cloud SQL portability. |

## 8. Implementation gate

No capability is called complete until its matrix row includes:

1. Incept-owned requirement and data contract;
2. active UI/API implementation link;
3. normal, refresh, empty and failure/recovery proof where applicable;
4. source/decision lineage where it produces production media;
5. a tested status of `verified`.

The first implementation slice after this baseline is **A-03: New Project**.
It will be rebuilt only after the `CreateProjectModal`, project store, project
router and project manager paths have appendix entries and an Incept page
contract. This prevents another visually plausible but contract-incomplete
creation flow.

### A-03 implementation record — 2026-09-22

- **Implemented:** `apps/web/components/video-production/NewVideoProduction.tsx`
  now owns a four-step, non-billable intake: delivery outcome and project
  identity; server-owned model catalogue; creative/market constraints; review
  and explicit create. Project-level model selections are saved separately from
  deployment-level provider configuration.
- **Safety controls:** inline client validation, browser unload warning for an
  unsaved draft, one-request submit guard, disabled create state, and retained
  form values after transport failure.
- **Validation performed:** `apps/web/node_modules/.bin/tsc --noEmit` passed.
- **Still required before `verified`:** canonical-browser happy path, reload,
  validation and mocked transport-failure proof; an API test proving project
  creation did not enqueue a job.

## Appendix A — A-03 New Project contract

### Reference file coverage

| Source path | Symbol(s) read | Responsibility | Disposition | Incept-owned requirement |
| --- | --- | --- | --- | --- |
| `frontend/src/components/pages/CreateProjectModal.tsx` | `CreateProjectModal`, `StepIndicator`, `handleCreate` | Multi-step, keyboard-safe creation; create only after local validation; surface server failures; then navigate to the saved project. | audited | A dedicated, non-billable creation route with staged validation and a clear review step. |
| `frontend/src/components/pages/create-project/WizardStep1Basics.tsx` | `WizardStep1Basics` | Collect and validate project identity, outcome, duration and format before advancing. | audited | Step one owns identity and delivery constraints. No generation setting is exposed or mutated here. |
| `frontend/src/components/pages/create-project/WizardStep2Models.tsx` | `WizardStep2Models` | Load provider capabilities with loading/error state; selection is separate from core identity. | audited / specified | New Project must load a server-owned capability catalogue and persist explicit per-project text, image, video and audio selections. It may never accept an unverified model ID, endpoint, credential or location from the browser. |
| `frontend/src/components/pages/create-project/WizardStep3Style.tsx` | `WizardStep3Style` | Optional visual direction followed by an explicit create confirmation. | audited | Step two collects creative and market constraints; step three is a review-and-create confirmation. |
| `frontend/src/stores/projects-store.ts` | create-modal and project-refresh state | Keep creation state distinct from project list/detail state; clear transient state after success. | audited | Incept route state owns only its form; post-create navigation reads the persisted project rather than a client-only draft. |
| `frontend/src/api/transport.ts` | request error boundary | Convert transport failure into an actionable form error. | pending | `createVideoProduction` must expose typed error text; browser UAT covers request failure. |
| `server/routers/projects.py` | create project HTTP contract | Validate a creation request and return a persisted project identity. | audited | `POST /video-productions` returns the persisted production; no provider or generation job can be created. |
| `lib/project/project_manager.py` | project creation service | Create the durable project record and its initial state. | pending | `create_video_production` must create initial audit/revision evidence and a durable default stage. |
| `lib/db/models/project.py` | project persistence model | Store project identity and metadata. | pending | Video project persistence must become Cloud SQL migration-ready before production deployment. |

### Incept page contract — New Project

- **Route / entry points:** `/video-production/new`; main hub CTA; keyboard-accessible direct URL.
- **Outcome:** create a persisted commercial, original short-drama, repair, or
  CTV project draft without calling a model or generation job.
- **Reads:** static outcome metadata plus a safe server-owned provider capability catalogue; no credentials or raw endpoints are sent to the browser.
- **Writes:** `POST /video-productions` exactly once after explicit review.
- **Fields:** title, outcome, duration, aspect ratio, market, audience,
  platform, conversion goal, visual direction, spoken/subtitle language,
  brief, required constraints and explicit server-validated provider/model
  selections for text, image, video and audio operations.
- **Primary actions:** continue/back through steps; create production from the
  review step only.
- **Async / error states:** submitting state, validation error, transport
  error with retry, and destination project not found after navigation.
- **Non-billable invariant:** all four steps and the create request cannot
  enqueue an image, video, audio, render, or agent job.
- **Reload / back:** a page reload resets unsaved local inputs with a visible
  draft-loss warning once fields have changed; successful creation lands on the
  persisted project route; browser back returns to the hub.

| Case | Given | When | Then | Required evidence |
| --- | --- | --- | --- | --- |
| Happy path | a signed-in creator | completes required fields and confirms | one persisted draft opens in its workspace | browser UAT + API assertion |
| Validation | incomplete identity/brief | attempts to continue/create | focus moves to an actionable inline error | browser UAT |
| Reload | changed, unsubmitted draft | reloads route | warns before loss or resets deliberately | browser UAT |
| Failure | API returns failure | confirms create | inputs remain; retry is possible; no duplicate project | mocked API/browser test |
| No generation | any valid creation payload | creates project | no generation or render job exists | API/unit test |

## Appendix B — A-04 Project lifecycle contract

- **Implemented:** project records now persist `archived_at` and `archived_by`;
  the active library hides archived records by default, while the library's
  Archived view can restore them. The existing copy-on-write branch endpoint
  now has a visible “Variant” entry point in the project library.
- **Safety rule:** archive is reversible and preserves the project, all source
  assets, approvals, selected takes, render history and audit revisions. It is
  distinct from the existing permanent delete endpoint.
- **API:** `POST /video-productions/{id}/archive`, `POST
  /video-productions/{id}/restore`, and `GET /video-productions` with
  `include_archived=true`.
- **Automated proof:** `tests/test_video_production_whitepaper.py` verifies
  archive hides an owned project from the default read model, retains it in the
  archive read model, and restore returns the same record to the active list.
- **Still required before `verified`:** canonical-browser archive, restore,
  branch navigation, page refresh, and a forbidden cross-project action test.

## Appendix C — A-19 Interrupted-operation recovery

- **Implemented:** on API bootstrap, persisted Video Production jobs that were
  `queued` or `running` under a request-scoped executor are marked failed with
  explicit retry guidance. Their project inputs and any completed output
  candidates are retained; no candidate is selected or replaced.
- **Automated proof:** the contract test simulates a persisted in-flight visual
  development job and verifies it becomes retryable without output mutation.
- **Still missing:** a durable leased worker, cross-instance ownership,
  cancellation acknowledgement and automatic restart recovery. These remain
  required before A-19 can be called verified.

## Appendix D — A-14 project model selection

- **Implemented:** `GET /video-production-capabilities` exposes only safe,
  server-confirmed provider/model pairs. `NewVideoProduction.tsx` loads this
  catalogue in a dedicated Models step with loading, unavailable and retry
  states. `create_video_production` and `update_video_production` reject a
  browser-supplied provider/model pair not present in the live catalogue.
- **Persistence and execution:** each `VideoProductionSetup` stores text,
  image, video and audio selections. Production text roles, visual-development
  images, Veo takes, soundtrack requests and usage records resolve the stored
  choice rather than silently using an unrelated default. Older empty project
  selections are safely backfilled from server configuration.
- **Security boundary:** this surface deliberately has no endpoint, location,
  credential, project ID or arbitrary model editor. Adding a new provider is a
  platform-owned deployment/configuration change and requires user-supplied
  official integration details; it is not accepted from a project form.
- **Automated proof:** `tests/test_video_production_whitepaper.py` verifies the
  safe catalogue/default selection, rejection of arbitrary model values and
  an actionable `422` create response and persisted project-model updates; all 18 tests pass. `apps/web` TypeScript type checking passes. A local `GET`
  against the live API returned the currently configured four operation
  choices without invoking a model.
- **Still required before `verified`:** canonical browser create → reload →
  reopen proof, a browser-visible create transport failure, and a forbidden
  cross-project provider-selection update test. The Computer Use browser is
  currently isolated from host `localhost:3001` (`ERR_CONNECTION_REFUSED`), so
  this remains an explicit UAT blocker rather than a passing claim.

## Appendix E — A-15 production authorization

- **Implemented:** Video Production keeps an owner-or-manager access rule on
  individual production reads and mutations. The project-list `scope=all`
  path is now restricted to manager/admin roles; regular users receive a
  deliberate `403`, rather than receiving another creator's project metadata.
- **Automated proof:** the production-chain test suite creates separate owner,
  regular-user and manager identities. It proves an owner-only list, rejected
  unprivileged full-workspace list, rejected cross-project archive, allowed
  manager review, and the `403` router response. All 18 tests pass.
- **Still required before `verified`:** HTTP integration tests through the
  Next proxy for unauthenticated/IAP identity handling, an owner/manager
  browser UAT, and an explicit policy for manager mutations versus review-only
  access. Those deployment/auth decisions are platform-owned and must not be
  guessed from this audit.

## Appendix F — A-20 persistence migration baseline

- **Observed implementation:** Incept already has a PostgreSQL/Cloud SQL
  connection adapter and a one-time SQLite-to-PostgreSQL importer with dry-run,
  apply and row/checksum verification modes. The normal runtime still evolves
  its schema through `CREATE TABLE IF NOT EXISTS` and additive column checks;
  it does not have a versioned migration ledger or rollback plan.
- **Decision:** retain this as **partial**, not complete. A deployment must not
  be called migration-safe until clean PostgreSQL initialization, an ordered
  versioned upgrade, read compatibility and a documented recovery/rollback
  procedure have all been exercised against the operator-owned Cloud SQL
  configuration. No database URL, secret, instance, location or migration was
  invented or run by this audit.

## Appendix G — A-17/A-18 authenticated automation transport

- **Implemented independently:** `video_production_mcp.py` builds a real
  Streamable HTTP MCP host with stateless transport. It exposes project list,
  read, create/update, branch/archive/restore, script and storyboard gates,
  Design Pack and Shot edits, bridge-frame promotion, agent planning, durable
  generation submission, model capability discovery and job polling. Each tool
  calls the existing Video Production store instead of a parallel automation
  database, so its ownership checks, `expected_revision` conflict rule,
  approval gates and restart recovery remain the same as the web workspace.
- **Authorization and safe activation:** the host is absent unless deployment
  config supplies both `INCEPT_VIDEO_MCP_PUBLIC_URL` and a non-empty
  `INCEPT_VIDEO_MCP_API_KEYS` JSON principal map. Tokens are opaque bearer
  credentials and are never returned or logged. Each principal has a required
  Incept id, allowed-domain email and role; no anonymous, browser-session or
  deployment-secret fallback exists. The public URL and credentials are
  operator-owned configuration, not a project setting.
- **Spend and failure contract:** planning-agent and generation tools require
  `confirm_spend=true` on every call. Async submissions return a durable job
  record and direct callers to `get_video_project_operations`; an unavailable
  provider, invalid request, forbidden project or workflow gate is returned as
  an MCP tool error without selecting or replacing project output.
- **Automated proof:** the 26 Video Production contract tests pass. They prove
  disabled-by-default mounting, an ASGI `401` for an anonymous Streamable HTTP
  request, an authenticated MCP initialize handshake, tool discovery,
  inherited principal identity for project creation and rejection of a
  generation call without spend confirmation; a non-HTTPS public endpoint is
  also rejected. The test suite makes no model request.
- **Deliberately still open:** request-id idempotency records for automation
  mutations, a durable cross-instance worker/lease, deployed HTTP client
  handshake/401 tests through the reverse proxy, IAP coexistence validation and
  a human-approved credential rotation/runbook. Therefore A-17 remains
  **partial** and A-18 is implemented but not browser/deployment verified.

## Appendix H — A-16 agent session/runtime audit

- **Observed reference responsibilities:** the runtime separates persistent
  session metadata from a live per-session actor, serializes turns and
  interrupts, keeps an ordered event-log projection for replay, provides
  idempotency for accepted messages and supports reversible transcript
  branching. Its access policy is a separate single source for filesystem,
  credential and tool restrictions.
- **What Incept already has:** a project-owned synchronous Copilot conversation
  with a per-production lock, cancellation marker, persisted message list,
  project fork/lineage, server-side provider selection and store-level
  authorization. This is suitable for the current request/response workflow.
- **Unclosed gap:** it is not a durable streaming agent runtime. There is no
  session/event table with monotonic entries, message idempotency key,
  project-scoped reconnect stream, transcript branch/rewrite flow, durable
  actor lease or formal agent tool/sandbox policy. A later implementation must
  be built around those owned contracts; it must not reuse a general-purpose
  filesystem agent merely to claim feature parity. A-16 therefore remains
  **partial**.

## Appendix I — A-13 durable project activity

- **Implemented:** every Video Production save now creates a small immutable
  `VideoProductionEvent` receipt in `video_production_events`, including its
  state revision, production stage and approval state. Project creation,
  direct project updates and forks retain an explicit actor/action summary;
  internal/background saves remain visibly labelled `system` rather than being
  misattributed to a human. `GET /video-productions/{id}/events` reuses the
  normal owner-or-manager read guard, has bounded paging, and survives a
  reload because it is stored separately from in-memory state.
- **Workspace behavior:** the canonical project workspace fetches durable
  activity on revision changes and consumes the owned `events/stream` SSE
  endpoint. Snapshot and activity messages trigger a safe refresh; the UI
  still shows retained activity, an empty state, a loading indicator and an
  inline retry on read failure.
- **Automated proof:** the contract suite now has 26 passing tests, including
  create → update → event read, ordered revisions, owner identity, denied
  cross-project event read, the router's `403` response and the initial SSE
  snapshot. No model call was made.
- **Still open:** reference functionality uses a real SSE snapshot/change
  stream with heartbeats, reconnect and overflow semantics. Incept's stream
  is deliberately database-poll-backed: it has snapshots, activity receipts,
  heartbeats and permission rechecks, but not a shared broker/fanout layer,
  explicit client reconnect/backpressure contract, reverse-proxy browser UAT,
  or event-level model input/output lineage. A-13 remains **partial** until
  those capabilities have independent contracts and tests.

## Appendix J — A-15 project authorization policy

- **Implemented:** Video Production has a framework-free, single policy for
  project ownership and delegated workspace operators. A normal user can only
  discover or mutate a project they created. A manager or administrator is an
  accountable operator and may list the workspace, inspect a project by id,
  recover it, or mutate it when a production hand-off requires continuity.
  Routes, durable jobs and MCP tools enter through the same store guard.
- **Automated proof:** the contract suite proves a non-owner cannot list the
  workspace-wide scope or archive another user's project; a manager can list
  the workspace and archive that same project. Event reads reuse the same
  policy and reject another ordinary user with a router-level `403`.
- **Still open:** this does not introduce a reviewer-only role, scoped API-key
  records, a team-membership ACL, IAP reverse-proxy UAT, or an administrator
  role-change audit trail. Those need an explicitly approved organization
  policy and deployment evidence; A-15 remains **partial**.

## Appendix K — A-20 additive schema migration baseline

- **Implemented:** Video Production's durable activity table is now owned by
  an additive migration ledger rather than only by bootstrap DDL. Startup
  creates `schema_migrations`, applies each named migration once, and provides
  the expected/applied/missing migration ids to an operator health check. The
  event-table migration is safe for a new database and for an existing project
  database that predates activity receipts.
- **Automated proof:** the contract suite now has 26 passing tests. A local
  test opens a deliberately legacy SQLite database, upgrades it, verifies the
  activity table and migration row, then restarts the initializer and proves
  no second migration row is created. No cloud service or model is called.
- **Still open:** this is not a substitute for a Cloud SQL deployment
  rehearsal. Clean Cloud SQL migrate, upgrade from a production snapshot,
  rollback/read compatibility, migration locking under multiple deployers and
  a deployment runbook still require the platform-owned database configuration
  and an approved maintenance window. A-20 remains **partial**.

## Appendix L — A-06 shared production asset slice

- **Implemented:** the Video Production asset library now has an owned upload
  entry point, refresh/error state and local search. Uploading is deliberately
  separate from attaching: after upload, a team member selects the production,
  production role, source note and rights note, then saves that association as
  a revisioned project change; detaching preserves the shared source file.
  Image, video, audio and nonvisual uploads have
  media-appropriate library states; audio is no longer classified as an image.
- **Automated proof:** the 26-test contract suite verifies audio classification
  alongside the existing production safety tests. The web type checker accepts
  the upload, typed-media preview and search surface. No model call is made.
- **Still open:** asset-library metadata editing, duplicate conflict review,
  paginated/server-side search, multi-select attachment, derivatives and a
  browser upload/reload/failure UAT are not implemented. A-06 remains
  **partial**.

## Appendix M — A-05 working-script checkpoints

- **Implemented:** the production record keeps a bounded, durable script
  checkpoint whenever a human saves a working script, the Screenwriter creates
  a draft, or a script is locked as the production baseline. Each receipt has
  an opaque ID, revision, author, reason, full structured-script snapshot,
  scene/beat counts and the exact reading copy. The workspace shows the latest
  receipts and lets an editor restore a snapshot only as a new editable draft;
  this clears storyboard approval and never rewrites a current baseline in
  place. Locking advances the script revision before recording its baseline.
- **Automated proof:** the script-edit gate test proves a manual save revokes
  stale approval and writes an attributed receipt. The checkpoint-restore test
  proves the restored copy receives a new revision, keeps its structured
  content, revokes approval, and records a new receipt. These tests make no
  model invocation.
- **Still open:** structured scene-level diff/review, source-document
  ingestion and browser lock/edit/restore UAT remain unimplemented. A-05
  remains **partial**.
