# Agent production handoff audit — 2026-10-11

## Confirmed causes

The reported restart was not evidence of a small model context window. The
application treated short confirmations as isolated chat and passed only the
latest message to the model. User-only choice replay also omitted the assistant's
pending draft; long histories retained URLs/duration but lost plan content.
Unrestricted number-range parsing interpreted vehicle model years as shot
intervals, and the total-duration parser mistook a five-second opening shot for
a five-second film. The local Toonflow runtime persists SDK session context;
LinglongLab's Canvas Agent originally used a separate Python runtime, not that
SDK. The active HTTP/MCP entries now use Pi through the authenticated host adapter;
see [runtime/persistence boundaries](pi-agent-runtime.md).

## Historical pre-Pi fixes and boundaries

- Persist validated storyboard metadata with the assistant turn and replay a
  bounded pending draft from conversation history. Legacy plans explicitly offered
  for confirmation remain usable. Approval comes only from user statements.
- Resolve production continuation before chat isolation. Chinese/English short
  confirmations and long-history follow-ups retain current choices and plan text.
- Preserve ordinary conversational text memory, while excluding previous research
  turns, evidence, product claims and attachment reads from independent chat.
- Repair duplicate requests for known brand/product/duration. Missing commercial
  rights remain a legitimate blocker; approval never invents those rights.
- Distinguish model-year/specification ranges and per-shot durations from an
  actual time axis and total runtime. Invalid shot structures/timelines still fail
  before canvas mutation. No safety validator or test was disabled.
- Keep research explicitly user-invoked and media limited to the current attachment
  selection. A brief confirmation grants neither canvas changes nor paid jobs.
- Add independent persisted multi-turn acceptance tests and CI gates for failures,
  errors, skips, coverage and frontend regressions. See [contract](../CONSTRAINTS.md).

## Evidence

The independent initial test run reproduced the failures before implementation;
additional tests reproduced duplicate intake, contradictory task labeling and
English confirmation failures. The run uses real routing, store reload and canvas
commits; only external model/network/media boundaries are mocked. Coverage is line
coverage, not a guarantee of model semantics or production quality.

This audit does not claim real-provider, staging-browser, Cloud Run or final-MP4
acceptance. No model IDs, cloud regions, endpoints, production data or infrastructure
were changed. The Prompt Reviewer skill's legacy targets/model do not match the
active Canvas runtime; its remote review was not invoked or reported as passing.

Pre-migration local run: 418 backend tests, 46 frontend tests, no failures/errors/skips;
33 production-handoff acceptance cases are included in the backend suite. Core
Agent line coverage is 90% overall (routing 88%, context 97%, lifecycle 91%). Vue
typecheck, production build/static sync and whitespace checks pass. CI changes
were made locally; a hosted CI run has not been observed.

Pi ownership cleanup local run: 460 backend tests, 7 actual-SDK tests and 49 frontend
tests, with zero failures/errors/skips. Active host/lifecycle line coverage is
93% (Pi host 92%, model adapter 97%, process bridge 83%, snapshots 100%, business
tools 98%, tool permissions 100%, turn lifecycle 91%). SDK native OpenAI/Anthropic transport tests
intercept HTTP; long-context tests execute Pi's automatic compaction. A permission
mutation was rejected by the create-without-delete regression test. Successful
SDK snapshots restore after simulated instance-cache loss. Vue and runtime
typechecks, frontend build/static sync and whitespace checks pass. The UI
translation audit and its two inline-translation checker tests pass; missing
document/image-control English copy was added without translating file names.
Production
dependency audit has no moderate/high/critical findings; it retains one low
KaTeX advisory (GHSA-238p-pmpm-9mq7). Its patched version requires a cross-minor
0.x upgrade, outside this runtime migration; do not claim a clean audit or
rendering acceptance. AWS Bedrock remains removed from the runtime dependency graph.

The active runtime no longer infers task state or rejects drafts through a Python
timeline prose parser. Structured timing checks return explicit local feedback.
SDK-entry mapping, native branching and Toonflow-style journal deletion retain
tool receipts without assistant-prose reconstruction. Legacy-history import is
disabled. Two non-running local old conversations were recoverably archived;
projects/canvases/media and cloud data were untouched. The new permission-boundary
mutation was caught by the ordinary-chat regression. Historical-engine tests
remain evidence about the retired code, not current model-quality acceptance.

Neither API Docker image nor isolated Pi Linux image has been accepted locally:
Docker Hub timed out while fetching Python; the isolated Node-stage attempt
failed downloading pnpm from npm. Dockerfiles include Node/Pi and fail the image
build if SDK import fails. These network failures are not bypassed or counted as
passes. No live-provider model/paid-generation or deployed-browser acceptance
was completed by these hermetic tests.

## Remaining release checks

Repeat the full Chinese/English production handoff on staging with the deployment's
enabled Gemini/OpenAI/Claude configurations and owner-approved usage limits. Verify
material selection, HTTP failures/retry, refresh, cancellation and canvas display.
Validate actual media and final exports separately. Frontend build passes but
reports a large workspace bundle; this pre-existing performance warning is not
evidence of Agent correctness and should be tracked separately.
