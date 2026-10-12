# LinglongLab additions to pinned Toonflow

Reviewed 2026-10-12 against Toonflow commit
`acdf33ce4ec0c33dac3bccf2d6d7c03f4d2f6807`. This inventory covers the active
native Agent host and its business boundaries, not every unrelated application
feature or the retired Python Agent. No production deployment is implied.

## Corrected deviations

- **Python intent/permission classifier** (`pi_permissions.py`, now deleted):
  classified only the newest sentence and hid canvas, document, media and research
  operations. Polite requests and short continuations could become read-only.
  Native upstream `apps/server/src/agent/tools/index.ts:createAgentTools` instead
  loads enabled plugins, validates their configuration, and registers definitions
  with Pi. The hosted catalog now follows that pattern.
- **Default prompt replacement** (`native/adapters.ts:conf`): the adapter supplied
  hosted policies as `agentSystemPrompt`, causing upstream `buildSystemPrompt` to
  skip `defaultSystemPrompt`. The original default is now retained and compiled
  by the upstream builder, with hosted deployment notes appended afterwards.
- **Global campaign-rule injection** (`pi_agent.py`): Moloco CTV specifications
  were appended to every session. The identical customer profile now belongs to
  the matching builtin CTV creative strategy skill, read on demand; generic
  workflow and custom skill instructions are not rewritten.

- **Missing native file-cache contract** (`video_legacy.py`): pinned upstream
  `apps/server/src/routes/workspaces/files/read.ts` uses `Cache-Control: no-store`.
  The FastAPI port omitted it, allowing a browser to reuse an old empty canvas
  even after the Agent saved nodes. Full, ranged and snapshot reads now prohibit
  storage; the workspace client revalidates existing caches. No alternate canvas
  state machine or rendering rewrite was retained.

## Remaining additions and their effect

| Addition | Active source | Difference and user effect |
| --- | --- | --- |
| Deployment prompt overlay | `apps/api/app/video_studio/pi_agent.py` | Interface language, configured model/region restrictions, unsupported Seedance routing, staged writes, media coverage, truthful failure/completion messages, explicit research intent and exact paid approval. Some duplicate native rules; the overlay still exists and is not upstream code. |
| Advertising/research skills | `apps/api/app/video_studio/store.py` | CTV reference research, brand/product intake and creative strategy prescribe source-backed claims, sample tables, manifests, an approved brief, rights and proof checks. These are LinglongLab business skills, not Toonflow's generic workflow. |
| Evidence and delivery checks | `research_tools.py`, `creative_specs.py`, `pi_tools.py` | Persisted fetched-source snapshots and exact claim excerpts, incomplete-search receipts, structured shot timing and Moloco technical checks. A technical pass never grants advertising rights or proves final quality. |
| Model/media adapters | `pi_model.py`, `pi_business.py`, `agent_media.py` | Enterprise Gemini transport; server-configured default media models; scoped attachment preparation and coverage; media/export jobs with idempotent receipts. Business tool names and schemas differ from desktop plugins. |
| Exact request approval enforcement | `pi_business.py` | Native Toonflow already instructs confirmation before compute. Our host additionally enforces approval on the resolved provider/model, full request and reference hashes; skipped or cancelled answers cannot submit. A2A external transmission also requires approval. |
| Shared-cloud resource boundaries | `store.py`, `workspace_documents.py`, `agent_turns.py`, `native_host.py`, `pi_sessions.py`, `pi_runs.py` | Account/project ownership, bounded owned paths, private Node callbacks, version checks, staged canvas commits, cancelled-run checks, durable events and database SDK snapshots. Desktop-local storage is not copied unchanged. |
| Capacity and delegation limits | `native_host.py`, `nativeRuntime.ts`, `native/adapters.ts`, `pi_agent.py` | Default five active parents, four simultaneous children per parent, no recursive delegation, at most forty shared model calls, thirty-minute host deadline, operating context/output limits and bounded callbacks. These can interrupt work and are hosting limits, not creative decisions or model-spec claims. |
| Resource/tool compatibility | `pi_business.py`, `native/adapters.ts` | User/project memory, project rules and team/catalog editors; authenticated A2A, fixed local media operations, canvas management, and compatibility delegation aliases. Native memory/report/sub-agent lifecycle is retained; arbitrary desktop shell/browser/global plugin access is not provided. |

## What is native, not an invented restriction

The pinned default prompt already asks the Agent to read workflow skills, continue
known work, avoid unrelated edits, treat external content as untrusted, distinguish
started/completed/adopted outputs, and obtain concrete compute confirmation.
Do not attribute these native instructions to Python keyword gating. The eleven
vendored lifecycle/tool modules remain unchanged except the recorded module-link
rewrites; provenance tests verify their original executable bodies.

The user-owned settings prompt, project rules, memory and custom skill contents
are also distinct from rules shipped by this integration. They remain user-owned
and have not been deleted or rewritten during this correction.

## Acceptance boundary

Regression tests exercise the real SDK with synthetic model responses: retained
native prompt, stable enabled-plugin catalogs, context-dependent Chinese/English
node creation, polite generation reaching exact approval, disabled-plugin refusal,
no jobs after cancelled approval, and unchanged ownership/concurrency boundaries.
This does not establish real-model instruction following, live search reliability,
paid-media quality or deployed Cloud Run behavior. Capacity defaults still need
production load measurements. Remaining business skills and the deployment
overlay mean this integration is not complete desktop Toonflow parity.
