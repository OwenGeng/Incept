# LinglongLab Pi capability completion

Approved in chat on 2026-10-11: all six runtime capabilities and the additional
production/workspace gaps in the reviewed comparison. This is an application
change, not deployment authorization or authorization to spend on test generation.

## Capability map and order

| Module | Responsibility | Depends on |
| --- | --- | --- |
| events | Pi text/tool stream, durable event replay, run identity | existing Pi sessions |
| controls | Pi steering/follow-up, questions, cancellation | events |
| resources | scoped memory, project rules, skills and team configuration | authenticated store |
| reasoning | model-supported thinking setting and truthful usage | events |
| delegation | child Pi sessions, reports, continuation and shared budgets | controls, resources |
| production | authorized media jobs, processing, exports, document/canvas tools | controls, resources |
| acceptance | integrated API/SDK/UI and browser verification | all |

Build events/controls first; resource business tools and UI may be developed in
parallel against the agreed contract. Then integrate delegation and production.

## Behavior and acceptance

- Real provider text deltas and tool start/update/end events reach the UI, with
  stable IDs, arguments, receipts, errors and cancellation. No keys, binary
  attachments, internal provider payloads or private reasoning are displayed.
- Events carry monotonic per-run sequence numbers, survive cache loss using the
  existing metadata database, and can be replayed after a cursor. Browser
  disconnect does not authorize cancellation. Explicit stop still prevents
  future tools/commits. Interrupted host processes are reported accurately;
  unknown paid requests are never blindly reissued.
- Active instructions use Pi steer/followUp, never a Python planner. Questions
  bind user/project/conversation/run/call identity; answers are single-use and
  validated. Skipping is not approval. Pending cards survive reload.
- Thinking options derive from configured provider capability, preserve model
  IDs/endpoints/regions, and persist. Unsupported levels fail before calling.
- Child sessions use the real SDK, scoped inherited tools, independently saved
  journals, parent reports, continuation and cancellation. Shared finite budgets
  prevent recursion/concurrency from bypassing host limits.
- User/project memory can be viewed, edited, forgotten, disabled and versioned.
  Pi receives stored explicit resources; Python does not generate summaries or
  infer creative stages. Project rules and enabled skill configuration have the
  same revision guards. Remote teams require explicit configuration and safe
  outbound URLs; no discovery of arbitrary host credentials or filesystem.
- Workspace tools expose bounded documents and safe paths; edits require current
  revisions. Canvas tools expose implemented file/node actions and preserve
  concurrent edits. No shell or unrestricted FFmpeg commands.
- Paid jobs require a visible exact-request confirmation; idempotency retains
  receipts across retries. Agent can query/cancel jobs and attach real results.
  Probe/processing/export tools reuse existing authenticated business services.
- Usage distinguishes token counts and unknown monetary prices. Parent/child
  accounting and configured budgets are visible. Zero placeholders are not free.

## Contract

`POST /api/agent` accepts thinkingLevel and streamingBehavior. Active prompts
may also use `POST /api/agent/control` with directory, sessionFile, runId,
action (`steer`/`followUp`), prompt. `GET /api/agent/events` takes the same scope
plus after (sequence cursor). `POST /api/agent/answer` takes callId and
answer/values/skipped. `GET /api/agent/capabilities` returns configured models
with thinkingLevels and budgets. `GET/PATCH /api/agent/resources` uses resource
memory/rules/skills/team, scope project/user, content, enabled, expectedRevision.
Resource responses have content, enabled, revision, scope, resource.

## Source, style, verification and boundaries

API business adapters live in `apps/api/app/video_studio`, routes in routers,
tests in `apps/api/tests`. Actual SDK runtime lives in
`apps/video-vue/apps/agentRuntime/src`; Vue UI and helper tests in
`apps/video-vue/apps/web/src/components/agent`. Preserve existing formatting,
typed JSON boundaries and `store.safe_asset_path`/`document_lock` patterns.

Use the full commands and mandatory zero-failure/zero-skip/80% coverage gates in
`CONSTRAINTS.md`. Add regression evidence for replay, isolation, single-use
answers, cancellation, version conflicts, paid denial/idempotency and actual SDK
continuation/delegation. Run Vue/runtime types, frontend production build/sync,
isolated browser checks and a final correctness/security review.

Keep all existing user changes and production identifiers. No deployment,
production-history deletion, guessed provider configuration or fallback Agent.
Live providers, Cloud Run process loss, paid generation and final media quality
remain explicit release acceptance; local mocks cannot establish those results.
