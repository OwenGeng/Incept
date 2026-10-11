# LinglongLab Video Agent hardening

## Conversation and task contracts

- Persist the user message, its identity and attachments before invoking a provider; send the conversation/run identity before work begins. A failed request remains reloadable and retryable.
- Edit-and-resend truncates the abandoned branch using the persisted user-message identity. Deleting a user turn also deletes its associated replies; the UI uses the server's returned conversation.
- Only one run may own a conversation. Cancellation targets that exact run, prevents subsequent tool calls and commits, and cannot cancel a newer retry. Running conversations reject rename/delete mutations.
- Cancellation does not recall an already-dispatched provider request or guarantee that provider charges stop. Files already successfully imported before cancellation remain available.
- Durable duration, SKU, direction and approval come from user messages, not model summaries or draft files. Changing the customer or production choices invalidates the appropriate old approvals.
- Route the current question first: capability questions do not restart a creative proposal; website research precedes a website-based proposal; importing materials requires an import request.

## Delivery and canvas safety

- Reject action responses consisting only of `Done` or a capabilities introduction. Give bounded repair attempts; if validation still fails, retain the user turn and report failure instead of a fabricated completion.
- Script delivery includes structured shot durations and a visible timeline consistent with the selected total. Sensitive physical-performance claims require supported evidence and explicit attribution or an unverified label.
- Tool completion claims must agree with actual imported files or effective canvas operations. Discovery/import retrieves files and metadata; it does not inspect image pixels, audio or video frames and does not establish advertising rights.
- Long prompts use bounded sections, current-task priority and newest-first tool results, staying below the Agent's 160,000-character request limit.
- Canvas changes require an explicit edit request, target the original requested canvas, preserve existing Vue groups/unknown nodes/layout, and use conditional writes. Concurrent human edits or switching canvases must not be silently overwritten.
- Conversation and project mutations use short locks; provider/network requests do not hold those locks. Tests use isolated temporary storage, not production data.

## Customer-confirmed Moloco CTV profile

MP4; recommended 1920×1080, accepted 1280×720; maximum 450,000,000 bytes;
at least 24 FPS; duration 6–180 seconds; recommended 15/30/60 seconds.
Passing these technical checks is not platform approval or advertising-rights clearance.
See [website assets and CTV integration](linglonglab-website-assets-and-moloco-ctv.md).

## Verification and remaining release checks

Final local verification: **341 API tests passed**, **14 Agent frontend tests passed**,
canvas safety runtime checks passed, all Vue workspace type checks passed, and the production
web build passed. The generated frontend was synced into the local application's public assets.
The existing large-bundle build warning remains a separate performance follow-up.

API regression tests cover task routing, attachments, retry/cancel lifecycle, concurrent writes,
evidence/duration validation and CTV specs. Frontend tests cover attachment inputs, stream handling,
conversation deletion and canvas safety. Vue type checking and production build are required.
An isolated real-browser check exercises synthetic attachments, progress, retry, stop and reload
using mocked API responses. A deliberately inverted canvas conflict guard makes its regression
test fail; restoring the guard makes it pass. Inverting the new missing-audio guard also fails
the Chinese/English audio-only false-claim tests; restoration returns them to green.

Live provider calls were not used for this verification. Before release, smoke-test the configured
Gemini service and a real authorized customer website under production authentication. Do not change
model IDs, endpoints or cloud locations to work around provider errors.

Gemini, OpenAI and Claude receive actual image inputs. Image analysis copies preserve transparency,
normalize orientation and may reduce resolution; originals remain intact. Videos up to 450 MB and
180 seconds enter local preprocessing: Gemini receives native small MP4, a bounded proxy retaining
audio, or an owned temporary reference in the existing configured private GCS bucket. OpenAI/Claude
receive 2–12 timestamped frames per clip, without audio or exhaustive frame coverage. Replies include
the actual input range; clear false audio/exhaustive-inspection claims get bounded repair attempts.

Application safety budgets, not vendor hard limits: image sources 100 MiB/40 MP, prepared images
1536-pixel longest edge/2 MiB, at most 64 images including sampled frames, 20 attachments,
raw prepared payload totals Gemini 24 MiB/OpenAI 16 MiB/Claude 12 MiB. Video proxy budget is 8 MiB;
local preparation has two workers and a 180-second total time budget. Invalid, unsupported or
over-budget inputs remain metadata-only with specific reasons. Gemini audio/PDF retain an 8 MiB
budget; OpenAI/Claude audio/transcription are not implemented on this route.

Uploads stream into owned temporary files and atomically publish only on success. Cancellation
terminates local subprocesses and cleans temporary files; GCS cleanup uses owned generation IDs
and logs an operator alert on failure. Already-dispatched provider/storage requests cannot be recalled.
Live model/GCS calls and actual 450 MB upload stress tests were not performed.

Release boundary: [Cloud Run HTTP/1 requests are limited to 32 MiB](https://docs.cloud.google.com/run/quotas).
An application 450 MB allowance does not bypass ingress limits. Verify the entire deployed upload
path before release; large uploads need an approved chunked/direct-storage or end-to-end HTTP/2
transport change. No deployment settings/IAM were changed here. FFmpeg/FFprobe must be available.
Website crawling remains public/static only: login, DRM, dynamically loaded content and inaccessible
video require authorized user-provided files or links.

These safeguards reduce known failure modes; they do not establish universal factual accuracy,
provider availability or a completed production deployment.

## 2026-10-09 active Agent re-review

Reviewed the active `/video` Vue entry and Video Studio orchestration, not retired
Video Production prompt/caller paths. Small application fixes, no prompt/model/cloud migration:

- Verified: negated choices and duration questions no longer change duration, direction,
  customer/SKU or approval. Latest affirmative choice wins; full user constraints remain visible.
- Verified: explanatory/negative node requests cannot authorize canvas edits. Permission now
  uses the same intent predicate as routing, not a bare `node` keyword or generic skill prefix.
- Verified: negative download requests never enable the import tool; instructional download
  questions are capability requests, not permission to retrieve files.
- Verified: current-SKU evidence controls research stages and answer validation. Old-SKU facts
  cannot prematurely close recording or be appended to a blocked new-SKU report.
- Verified: storyboard/node follow-ups no longer restart historical research. Explicit new
  research requests remain separate from a follow-up inferred only from history.

Regression tests reproduced each fault before its fix; the deliberately inverted canvas guard
fails the no-edit integration test and passes after restoration. Full isolated API suite: 341;
Agent frontend checks: 14. This slice changes only Python orchestration/context and tests/docs;
no frontend code/build assets changed. Real provider/GCS and large-file ingress smoke tests remain
unknown, not promoted to verified; deployment and paid calls were not performed.

Evidence files: `agent_context.py`, `agent.py`, `test_video_agent_context.py`,
`test_video_agent_boundaries.py`, `test_video_agent_product_scope.py` under `apps/api/`.

## 2026-10-10 Gemini Agent HTTP 400 repair

- Live comparison on the unchanged `gemini-3.8-flash` / `global` configuration:
  the old Agent schema returned `400 INVALID_ARGUMENT`, while a minimal object
  schema succeeded. Removing `additionalProperties` made the full schema accepted
  but lost requested tool arguments and canvas operations. Replacing the boolean
  with an empty schema also returned 400. Do not use these as silent fallbacks.
- The Agent now uses `application/json` without a provider-side response schema
  for its open tool-argument and node-data payloads. Existing response parsing,
  bounded invalid-response repair, round-specific tool checks, evidence validation
  and canvas permission checks remain in force. This is JSON mode, not a guarantee
  of schema compliance; validation must precede execution. See the
  [official structured-output guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/control-generated-output).
- API-boundary regression tests first failed on the old request and passed on
  the fix, including unspecified, empty and non-empty round tool lists.
  The complete isolated API suite passed: **343 tests**.
- Live JSON-mode output retained the requested URL argument and nested node data
  and position. The actual Agent greeting also succeeded using temporary project,
  conversation and SQLite storage. PostgreSQL/metadata persistence was disabled;
  GCS database access and SQLite connections outside the temporary directory were
  explicitly blocked. No customer website tools or production data were used.
- No model ID, endpoint, cloud region, thinking configuration, dependency or
  deployment change. Production rollout, authorized website research, real media
  analysis and large-file ingress tests remain separate release checks. Earlier
  no-live-call notes describe the preceding verification slices, not this repair.
