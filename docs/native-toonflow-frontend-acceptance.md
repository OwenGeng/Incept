# Native Toonflow frontend acceptance

This plan verifies LinglongLab's existing interface against the native Toonflow
agent host. It uses five isolated test identities and hermetic model/tool
responses. These are test accounts, not a claim that five human users tested the
product. Do not make paid model calls or contact external services as part of the
hermetic suite. Browser interaction and screenshots are coordinated by the root
agent after the host and frontend bundles are ready.

## Native event contract

Source of truth is the local Toonflow-app checkout, specifically
`apps/server/src/agent/runtime/{index,types,sessions,delegation}.ts`,
`apps/server/src/agent/tools/subAgent.ts`, and
`apps/server/src/agent/bridge/question.ts`.

The current chat stream already follows those original public events. Keep
`tool.blockId` (assistant content slot such as `1:0`) distinct from `tool.id`
(model call ID). Questions address `toolCallId`, not `blockId`. The native
`subAgent` tool returns incremental JSON `{tasks:[...]}` through `tool.result`;
`inputRequired`, `limited`, `error` and `cancelled` are outcomes to display, not
successful completion. A child `done` or `error` inside `subAgentEvent` ends only
that child. The parent's stream stays open until its own terminal event.

The hosted boundary adds canonical session IDs, run IDs, question ownership,
and replay sequence numbers. Canonicalize `session.file`, `subAgent.agent.file`
and `parentFile`, `subAgentEvent.file`, `report.file` and `parentFile`, and question
`sessionFile` consistently. Active snapshots retain `entryId`, `replyTo`, grouped
`parts`, `streaming`, and pending question call IDs. Native statistics already
include delegated tool-result usage; do not add child token totals twice.

`accepted` terminates the separate steering request response; it does not finish
the primary run. The separate control API can keep the current interface's
steering/follow-up choice while forwarding to the native Pi session.

## Five isolated browser scenarios

| Test identity | Setup through the hermetic API | Browser actions | Required observations |
| --- | --- | --- | --- |
| Author A | Project A; native text/thinking/subAgent events; one local child and one task with `inputRequired` | Send a story brief, inspect tool cards, select child, inspect report, continue the completed child directly | Incremental tool arguments/results appear; original child task survives reload; report appears once; `inputRequired` is visible; direct continuation and stop act on the selected child only |
| Director B | Project B; native askUser event with choice and form fields; fake generation result owned by B | Answer a question, append an immediate correction while running, then stop | Correct question/run identity is submitted; text remains editable; native accepted acknowledgment does not close the live run; answer produces one continuation; stopping does not stop A |
| Editor C | Project C; native follow-up queue and compaction start/end, then image/video artifacts from business APIs | Queue a second instruction, refresh during compaction, inspect final assets and token usage | Both user messages persist; no duplicated delta after replay; compaction indicator clears; artifacts remain attached to C's project; known token counts and unknown price render without a blank popover |
| Producer D | Project D; hosted memory/rules/skills/team resources with revision conflicts | Edit project memory and rules, toggle an individual skill, configure team role, provoke a revision conflict, reload | Memory/rules remain scoped; personal skills explicitly say they are shared across projects; no ineffective catalog enable switch; conflict preserves the draft; native team task uses the saved role |
| Client E | Project E; attachment and file tools; one paused pending question | Upload an image/video, send an attachment-only request, refresh while waiting for an answer, then answer or skip | One explicit inspection request is submitted; original private attachment references persist; question remains actionable after refresh; renderers=[] still yields the built-in question form; files and conversation are inaccessible under A–D identities |

## Evidence and isolation checks

For each identity retain the project/session IDs, source event fixture, test log,
and relevant browser screenshot. Use the real production frontend bundle served
from `apps/web/public/video-app`; fake only external model/media responses. Check
that another identity cannot read session snapshots, event replay, pending
questions, memory, canvas files, assets or exported deliverables by guessing an
ID. A file/canvas mutation must retain the existing concurrency protection.

For Author A, inspect both parent and child after completion and after direct
child continuation. Native parent broadcasts must not overwrite the independent
child stream. For Client E, stop and restart explicitly, and verify that an old
call ID cannot answer a question belonging to the new run. Document unavailable
checks separately; do not describe hermetic model success as paid-model or
external-A2A production acceptance.

## Observed browser evidence — 2026-10-12

The agent operated a dedicated Chrome test tab against the isolated service at
`http://localhost:8037`. The production Vue bundle was used, with the real native
Toonflow lifecycle and Pi SDK; only external model responses were synthetic.
Five cookie identities were switched using `/qa/login/0` through `/qa/login/4`.
No paid generation or external A2A call was made.

| Identity | Visible owned project ID | Browser observation |
| --- | --- | --- |
| 1 | `40d9e3ecc4ae46d9ae22f8b36096c7b1` | Only project 原生宿主验收账户 1; pending askUser survived full reload and accepted 自然生活; native child opened with original task and completed history; stop then direct continuation succeeded; project memory saved and reloaded |
| 2 | `125f34e3572e40a29e16464c40a51e83` | Only project 原生宿主验收账户 2 |
| 3 | `214ca854ea4a4e7db3b45d4906e861df` | Only project 原生宿主验收账户 3 |
| 4 | `1ac789d55c1a43c598606f13afbdf72f` | Only project 原生宿主验收账户 4 |
| 5 | `3cd11c03329c412c91cc0b3fb7f090be` | Only project 原生宿主验收账户 5; memory did not contain identity 1's text; per-skill switch persisted off; no global skill enable switch; canonical disposable conversation removal completed |

Native `askUser` tool rendered the built-in question form with the empty external
renderer catalog. The populated usage popover displayed input 100/output 40
tokens, context/output budgets and “Price unknown”. Thinking choices were Default,
Low, Medium and High; High was selectable. An active steering submission kept
Stop generation visible, and the added user message and response persisted.

Browser validation exposed a session identity issue: the second native session
acknowledgment omitted runId and overwrote the authenticated initial run identity.
The frontend now retains that identity, clears an old turn identity before a new
owned request, and preserves the draft until a fresh run is ready. The corrected
bundle accepted Queue next with “Queued for the next turn” while the original
stream remained active.

Stopping immediately after queue acceptance initially omitted the queued text
after reload. The corrected durable command projection passed browser retesting:
the exact text “精确保留：中断后重新发送海边结尾” remained with
“Interrupted; resend this instruction to continue.” and a Copy to message button.
There was no historical edit/delete action for this synthetic receipt. Copy to
message filled the exact composer text; explicit Send completed a normal new
turn. Acceptance alone does not imply model execution.

A separate normal queue case completed through the native SDK. After full reload,
“海边结尾：正常队列验收完成” appeared once as a user message, its actual final
response appeared once, and there were zero Stop generation buttons and zero
interrupted badges. This distinguishes normal execution from an interrupted
acceptance receipt.

An actual native child `report` tool delivered “原生子代理报告：五秒开头需要清楚展示产品。”
to the parent. The first report fixture then repeatedly delegated new children
until the shared 40-call budget stopped it. Each report belonged to a distinct
child. After fixing the synthetic parent's receipt recognition, final browser
retesting showed one native child, the parent completion text, and one actual
report. Full reload still showed exactly one report and one parent final reply;
the report scenario passed.

Screenshots saved under `/private/tmp/linglonglab-native-browser/`:

- `question-recovered-usage.jpg`
- `native-child-completed.jpg`
- `child-stop-continue.jpg`
- `project-memory-saved.jpg`
- `account-2-projects.jpg` through `account-5-projects.jpg`
- `followup-accepted-stream-alive.jpg`
- `skills-shared-per-item.jpg`
- `conversation-removed.jpg`
- `native-report-budget-guard.jpg`
- `native-report-completed.jpg`
- `followup-normal-active.jpg`
- `followup-normal-completed.jpg`
- `queued-stop-retained-labelled.jpg`

Console inspection found repeated icon custom-element warnings originating from
the installed Chrome React DevTools extension (`chrome-extension://.../installHook.js`),
with no application exception in that captured interval. No clean-console claim
is made for the extension's warnings. Browser list isolation is distinct from
direct cross-account API permission checks, which require separate API evidence.

Final frontend verification: 75 Web tests passed with zero failures or skips;
Vue typecheck, i18n validation, Vite production build and sync all passed. The
final browser bundle was `workspace-DjU17TDw.js`. Browser work stopped after this
verification so the remaining host transport work could be validated and frozen
independently. Paid production models and external A2A endpoints remain outside
this hermetic browser evidence.
