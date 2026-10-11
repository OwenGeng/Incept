# LinglongLab Video Agent runtime

The production Agent entry points use the official Pi TypeScript SDK. Python
remains the authenticated business backend; it does not implement an LLM/tool
turn loop or fall back to the retired JSON Agent.

## Sources and version

- SDK: `@earendil-works/pi-coding-agent` and `pi-ai`, pinned to `0.85.1`, matching
  the local Toonflow integration. Node 24 is required by development/CI/images.
- Toonflow source: commit `72a895c26aab3f54c5a914517615362208fa6008` in
  `HBAI-Ltd/Toonflow-app`; prompt, workflow and references are vendored under
  `apps/video-vue/apps/agentRuntime`. Its MIT license is included.
- Official [SDK documentation](https://github.com/earendil-works/pi/blob/v0.85.1/packages/coding-agent/docs/sdk.md)
  describes TypeScript embedding. The [RPC documentation](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md)
  includes a Python subprocess example. No equivalent official Python SDK was
  established in this audit. This host uses private JSONL IPC around the SDK,
  not a Python port and not the Pi CLI RPC command schema.

## Ownership

Pi owns session/context construction, tool turns, branching, automatic
compaction and retry. The hosted adapter disables filesystem/global extension
discovery and exposes no shell, arbitrary read/write, SDK home credentials or
provider-switch fallback. OpenAI/Anthropic use Pi's native transports. Enterprise
Gemini uses native `google-genai` function calls in the existing Python provider
transport, retaining deployment-owned model/project/location values.

The upstream prompt/workflow is not an authorization boundary. Deployment
policies override its Chinese default and Seedance-specific routing: this
deployment must use the UI language and its actual enabled models. The host
also preserves user-selected media scope, private paths, extension permissions,
explicit canvas authority and existing cancellation/concurrent-edit checks.
Unsupported safety claims are marked in draft text, not promoted to approved
advertising copy and not used to reject an unrelated chat turn.

## Persistence and migration

Importing legacy conversations into Pi as retained user/assistant messages was
the initial compatibility approach; it is now disabled. Start new
Pi conversations instead of reconstructing old custom-Agent history. Historical
binary attachments are not replayed. Project/media paths remain unchanged.
Conversation JSON is a UI projection, not model context: each displayed message
maps to a real Pi journal entry ID. Edit/resend navigates the SDK tree, retaining
earlier tool receipts and excluding abandoned branches. UI message deletion
records journal IDs; before the next prompt, a forked journal redacts those turns
and affected summaries using Toonflow's storage-edit pattern. Pi then builds the
context. This is not Python text-history replay or a second summary algorithm.

Each attempt forks the last successful SDK session. Failure/cancellation cannot
mutate that successful source. Canonical conversation metadata records the
committed SDK filename and UI message IDs. Successful JSONL snapshots are stored
privately in the existing metadata database under `pi-sessions/<user>/<project>/`
when database persistence is enabled. They are restored into a disposable cache
on another Cloud Run instance, with checksum and 64 MiB size validation. They
are not public workspace assets. After a successful canonical save the previous
database snapshot can be released; local JSONL source/attempt files remain.
Conversation/project deletion also removes corresponding private persistence.

The database is authoritative in production; a local-only deployment retains
atomic private committed snapshots under each conversation's own identity,
independent of a delegated child's execution folder. Existing local child logs
can be recovered from the owned parent's folder. A missing/corrupt committed snapshot fails closed rather than
silently replacing tool history with a short UI summary. UI conversation listing
also restores database-backed metadata on a fresh instance.

## Hosted tool boundaries

Supported: scoped canvas inspection and draft creation/movement/rename/connections,
explicit deletion, structured storyboard validation, safe website/research tools,
versioned workspace document read/create/edit/search and canvas create/switch/rename.
Legacy workspace-canvas-file turns lock their selected target until completion;
children inherit that target. Staged node changes commit against the original
revision; concurrent user edits prevent that commit. Mounted external textPath
nodes are edited through versioned documents, not silently replaced inline.

Pi tools also manage media/export jobs, probe assets and run fixed trim/resize/
audio/frame operations without arbitrary commands. Paid generation and outbound
A2A tasks require a scoped exact-request question before submission. Receipts
bind the request and idempotency key; uncertain submissions are not retried.
Frame hashes bind approved bytes and fail before provider invocation if edited.
Real completed results can be attached to the canvas; queued work is not reported
as completed. Final media quality and advertising evidence remain business QA.

Research skills remain user-invoked, without automatic permission cards. Website
collection remains available independently in the asset library. Selection/import
is not media analysis, advertising-rights approval or final-film approval.
Only the current message's selected media is prepared. Binary media stays outside
SDK JSONL and is omitted from compaction requests. Provider preparation retains
the existing truthful coverage/processing limits and original files.

## Interactive runtime and resources

SDK text/tool start/update/end events use stable IDs. Native OpenAI/Anthropic
streams and Enterprise Gemini generate_content_stream produce visible deltas;
private reasoning and binary/credential fields are excluded from display events.
Run journals persist ordered events and commands in the existing authenticated
metadata store. Browser disconnect only ends observation; refresh resumes after
its cursor. Explicit stop prevents later host mutations and cancels child runs
and unanswered cards. Lost host leases report interruption without replaying
unknown paid work. Failed progress is retained as a display projection; it never
reconstructs model history.

The active UI provides immediate Pi steering, queued follow-up, built-in question
cards, thinking selection, resources and context/usage details. Questions validate
fields and use single-use scoped answers; skip is never consent. Reasoning choices
are exact-model capability gated. For the configured Gemini 3.8 deployment,
low/medium/high map to native settings, while off means the provider default, not
an unsupported disable mode. The [official model guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/guides/gemini-3-8-flash)
documents the native levels. Model names, endpoints and locations are unchanged.

User/project memory, project rules, skills and teams are explicit versioned
resources with editors, enable flags and forget support. SDK tools can use them;
Python does not infer memory or run an automatic summary/model loop. Configured
team roles and delegateTask create independent child SDK journals, persist reports
and real message IDs, continue from saved snapshots and share finite budgets.
Child cancellation cannot commit later business results or revive its status.
Explicitly configured external teams use HTTPS A2A 0.3 with public-address
validation and outbound approval; no shell/global credentials are exposed.

## Operating budgets

`VIDEO_AGENT_CONTEXT_BUDGET` defaults to 65536 tokens and
`VIDEO_AGENT_OUTPUT_BUDGET` to 16384. They are local operating limits, not claims
about a provider's actual context window. Each run permits at most four children and 40 shared SDK model
calls, 30 minutes of host orchestration and 64 MiB per IPC record/saved snapshot.
Provider requests already sent cannot be recalled by cancellation; subsequent
tools/commits stop. Size memory/storage for SDK subprocesses, media and retained
local branch caches in staging. Zero cost placeholders are unknown pricing, not
free execution or a verified "$20/million output" selector.

## Verification and release gates

`CONSTRAINTS.md` is the standing release contract. Tests use the real SDK and
replace only provider/network boundaries. Native-provider tests intercept fetch;
Python tests forbid unmocked Pi provider calls. SDK tests prove successful tool
execution, persistent continuation, automatic compaction, native current-image
contracts and failure without provider swaps. Python tests cover lazy migration,
selected-media scope, partial tool failure, current-turn permissions, durable
snapshot restoration/deletion, structured timing feedback, cancel, retry and concurrent edits.
Historical-engine regression tests remain, but do not count as Pi/model-quality
evidence. CI independently gates active host coverage at 80%, zero failures/skips,
SDK/Vue types, frontend build and production dependency audit.

Local API/SDK tests do not establish real-provider quality, deployed browser
behavior or completed media production. Before release, repeat the exact
3W/Bronco → 30-second plan → short confirmation → explicit draft-node creation
scenario against each enabled real provider, in both UI languages, after reload.
Check native tool schemas, media receipts, actual node/document display,
stop/retry, timeout and instance-restart persistence. Confirm owner-approved
model-call budgets and Cloud Run database/storage configuration. Container build
and staging browser checks must pass; registry/npm connectivity failures are
release blockers, not successful image verification.

Rollback is a reviewed code/image revision plus intact canonical conversations
and committed SDK snapshots. Never silently restore the old Agent on provider
failure, change a model/region, or delete production data as a rollback shortcut.

## Local history reset — 2026-10-11

Two non-running pre-Pi conversations were removed from the local active store
`apps/data/video-studio`. Their recoverable private backup is in
`apps/data/.agent-history-archive-20261011-pi-native` (directory mode 0700, Git-ignored).
Projects, canvases and media were not removed. No cloud database was changed;
cloud cleanup requires identifying the deployment/user/project scope first.
See [remaining upstream differences](pi-toonflow-differences.md).
