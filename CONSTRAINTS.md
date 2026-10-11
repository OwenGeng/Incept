# LinglongLab Agent acceptance contract

Scope: the active `/video` Vue conversation → legacy API adapter →
`video_studio.pi_agent.run_agent` → real Pi SDK runtime. Passing this contract is necessary, not
sufficient, for a production release. Real-provider and deployed-browser tests
are separate gates; simulated responses do not prove model quality or MP4 quality.

## Mandatory gates

- Backend: zero failures, errors, skips or expected failures in the complete API
  test suite. CI checks the JUnit report, not only pytest's exit code.
- Coverage: at least 80% line coverage across Agent routing/context/turn lifecycle
  modules (`pi_agent`, `pi_model`, `pi_process`, `pi_tools`, `pi_sessions`, `pi_permissions`, `pi_runs`, `pi_http`, `pi_business`, `pi_capabilities`, `agent_turns`),
  independently of archived-engine regression coverage; do not omit uncovered branches
  or lower this threshold to obtain a pass. Line coverage does not prove semantic
  correctness; the behavioral scenarios below are independently mandatory.
- Frontend: zero failing or skipped tests and zero Vue/TypeScript type errors;
  production build and static-workspace sync must succeed.
- Changes: zero new test skips, deleted assertions/tests, checker suppressions,
  unfinished production stubs or secret values. Preserve existing user changes.
- Models: no guessed model IDs, locations, endpoints or automatic provider swaps.

## Behavioral release blockers

1. Brand/product → 30-second proposal → short Chinese/English confirmation →
   explicit canvas authorization → actual persisted text nodes must work after
   reloading the conversation from disk, without repeating known intake questions.
2. Long histories preserve the pending/approved draft and current user choices.
   Changed product/customer/duration invalidates prior draft approval. Assistant
   text cannot approve itself; negative statements and questions are not consent.
3. Brief approval alone grants neither canvas mutation nor paid media generation.
   No paid jobs, cloud writes or live website/model calls occur in automated tests.
4. Pi retains conversation text and tool history. Casual chat does not trigger
   historical research validation or replay binary attachments. Media analysis
   reads only the current selected attachment scope. Selected assets are not
   final-film approval. No separate Python stage/context inference is permitted.
5. Valid 5+6+6+6+7-second scripts pass; model years and individual shot durations
   are not total-film changes. Real gaps/overlaps, nonpositive/NaN durations and
   wrong totals return failed structured `validateStoryboard` feedback. Drafts
   remain deliverable with limitations; timing feedback is not final-media or
   advertising approval and must not reject an entire conversation turn.
6. Known inputs are not asked again. Concrete missing rights/evidence may still
   be requested. Research runs only on explicit user intent/skill activation;
   partial sources/assets cannot silently become completed research or imports.
7. Retry/cancel/resend/concurrent edit tests and completion-claim tests remain
   passing; no fabricated imports, generated media or completed canvas actions.

## Reproducible local commands

From `apps/api` (install `coverage` in the development environment only):

```sh
COVERAGE_FILE=/private/tmp/linglonglab-agent.coverage .venv/bin/python -m coverage run --source=app.video_studio.agent,app.video_studio.agent_context,app.video_studio.agent_turns,app.video_studio.pi_agent,app.video_studio.pi_tools,app.video_studio.pi_process,app.video_studio.pi_model,app.video_studio.pi_sessions,app.video_studio.pi_permissions,app.video_studio.pi_runs,app.video_studio.pi_http,app.video_studio.pi_business,app.video_studio.pi_capabilities -m pytest -q --junitxml=/private/tmp/linglonglab-agent-tests.xml
COVERAGE_FILE=/private/tmp/linglonglab-agent.coverage .venv/bin/python -m coverage report --fail-under=80
COVERAGE_FILE=/private/tmp/linglonglab-agent.coverage .venv/bin/python -m coverage report --include='*/pi_*.py,*/agent_turns.py' --fail-under=80
.venv/bin/python ../../scripts/check-agent-test-report.py /private/tmp/linglonglab-agent-tests.xml
```

From `apps/video-vue`:

```sh
node --experimental-strip-types --test $(rg --files apps/web/src -g '*.test.ts')
pnpm --filter '@linglonglab/video-agent-runtime' test
pnpm --filter '@linglonglab/video-agent-runtime' typecheck
pnpm --filter '@linglonglab/video-web' typecheck
pnpm build:web
pnpm sync
```

CI additionally enforces the existing preflight, dependency audits and container
builds. No exceptions are approved by this contract.

## Before deploying

Use the enabled real providers in a staging project to repeat the exact multi-turn
scenario with Chinese and English UI, confirm references and selected media
receipts, and verify the canvas visually after refresh. Check provider 4xx/timeout,
client disconnect and cancellation. Production credentials, permissions, quotas
and paid generation must be verified with owner-approved limits. Final MP4 export
requires separate creative/media QA. Do not describe local test passes as these
external checks having passed.

## Runtime migration boundaries

Pi's official TypeScript runtime owns the Agent loop, session branching,
compaction and retries. Python is the authenticated business/media adapter;
there is no production fallback to the old JSON-agent loop. Legacy tests remain
as regression evidence, not proof of Pi/model behavior. SDK tests must execute
real SDK tools (a `toolResult` containing "Tool not found" is not a passing tool
test). See `docs/pi-agent-runtime.md` for supported hosted tools and release gates.
