# LinglongLab versus local Toonflow Agent

Current native-host branch vendors Toonflow commit `acdf33ce4ec0c33dac3bccf2d6d7c03f4d2f6807`.
The capability completion figures below describe the preserved earlier baseline;
see [native host architecture and acceptance](toonflow-native-host.md) for this migration.
Both use the actual Pi `0.85.1` SDK. This is not complete desktop backend parity.

| Area | Toonflow | LinglongLab |
| --- | --- | --- |
| Reasoning/tool loop, compaction, retry | Native Toonflow host and Pi SDK | Vendored native host lifecycle and same SDK; no Python loop/fallback |
| Conversation context | SDK journal and tree | SDK journal and tree; UI JSON maps to SDK entry IDs, not context replay |
| HTTP host | Express/TypeScript/Bun server | Existing FastAPI service plus one private long-lived TypeScript native Agent host per API worker |
| Model transport | Configured TS provider protocols | Native Pi OpenAI/Anthropic; Enterprise Gemini uses existing Python transport, not Python orchestration |
| Session storage | Workspace-local journals | Private journals plus authenticated database snapshots for Cloud Run restarts |
| Tools | Desktop workspace/canvas/media, questions, delegation, memory | Scoped document/canvas/media/export tools, safe processing, questions, delegation, memory and configured A2A |
| Runtime UI | Text/tool events, queue/steer, questions, stats | Text/tool deltas, durable replay, steer/follow-up, answer cards and parent/child usage |
| Reasoning setting | Configurable thinking level | Capability-gated selector; Pi native settings and Enterprise Gemini native thinking |
| Resources | Workspace/global AGENTS, skills, optional long-term memory | User/project memory, project rules, skills and team editors with enable/forget/revision guards |
| Canvas commits | Desktop tool execution | Hosted staged changes with ownership, bounds and concurrent-edit checks |
| Product workflow | Includes Seedance-specific production methods | CTV/business policies override unsupported Seedance routing; actual enabled model IDs remain user-owned |

## What was removed from the active path

- Python brand/duration/approval/stage inference and its system-context injection.
- Legacy assistant-prose reconstruction as SDK context.
- End-of-turn prose/timeline regex rejection of entire draft deliveries.
- Automatic Python safety-claim text rewriting in canvas drafts.

Read-only/mutation permissions, explicit research activation, authentication,
current selected media, URL/file boundaries and cancellation are business host
responsibilities. They must not become another planner or chat-memory layer.
Storyboard timing is a structured Pi-callable business tool, not a blanket
response validator. Final export and advertising QA are separate release checks.

The retired `agent.py`/`agent_context.py` and their historical tests remain for
pre-migration regression evidence, but none of the production Agent entries or
Pi modules import them. Do not build new features on those modules. Removing
their source/tests is a separate final retirement after real-provider/browser
acceptance; their presence does not provide an automatic runtime fallback.

## Extension rule

New reasoning/runtime behavior must use Pi sessions, events, queueing, SDK tools
or extensions. New product capabilities become authenticated tools/skills around
that runtime. FastAPI does not need replacement just to satisfy this rule.

## Why the integration exposed bugs; Express migration cost

The checked-out Toonflow server uses Express 5.2.1 with TypeScript on Bun
(`apps/server/package.json`). Its startup code binds port 3000 and loads local
data, tools, nodes, providers and skills. LinglongLab reused Pi and the workspace
UI, but replaced much of the surrounding host: HTTP contracts, renderer loading,
event recovery, answers, child-session identities, storage and cancellation.
The integration bugs observed in browser acceptance came from those changed
contracts. FastAPI is capable of serving them; the Python/TypeScript split adds
boundaries, and framework replacement alone would not preserve upstream behavior.

If ongoing upstream compatibility becomes the priority, retain more of
Toonflow's TypeScript Agent host and let it call FastAPI's authenticated business
APIs. That reduces duplicated host behavior without rewriting existing business
services. This recommendation is implemented on `toonflow-native-host`; the scoped
model, resource, permission and storage adapters remain product-specific.

A separate Express/Bun container is a routine Cloud Run deployment. The work is
adapting the original local host for user isolation, durable journals/assets,
job ownership, restart recovery and streaming controls across instances. It
must listen on `0.0.0.0:$PORT`; container filesystem writes are temporary, and
background Agent execution needs an explicit CPU/task lifecycle design.
See the [Cloud Run container contract](https://docs.cloud.google.com/run/docs/container-contract)
and [deployment guide](https://docs.cloud.google.com/run/docs/deploying).

## Capability completion — 2026-10-12

The approved gap list is implemented through Pi tools, SDK sessions/events and
host business adapters. Python still provides no planner, automatic summary,
long-term-memory inference or separate model loop.

- Browser refresh reconnects to a durable event cursor. Text and tool cards,
  active instructions, pending questions and interrupted progress persist.
- Questions are bound to user/project/conversation/run/call. Built-in cards
  serve ordinary choices and exact paid/external request confirmations.
- Delegated and configured-team work uses separate SDK journals and durable
  child snapshots. Child continuation preserves real SDK IDs; cancellation is
  scoped, and stopping a parent also stops its children and pending answers.
- Memory is explicit, editable, scoped, disableable and forgettable. Rules,
  skills and team roles are versioned resources, not host-home scans.
- Agent tools can read/edit bounded documents with revisions, manage canvases,
  submit/query/cancel generation and export jobs, attach real results and run
  fixed media operations. Exact approved generation requests bind input asset
  hashes; changed frames fail before reaching the provider. Durable receipts
  prevent repeated paid/outbound requests after an uncertain submission.
- External collaboration uses explicitly configured HTTPS A2A 0.3 endpoints,
  public-address validation and request approval. There is no arbitrary shell
  or automatic access to desktop credentials.
- Usage reports real tokens and parent/child budgets. Unavailable monetary
  prices remain unknown. Gemini's default setting retains the provider default;
  supported low/medium/high choices use native thinking configuration.

Remaining differences are platform and release acceptance: hosted authenticated
resources replace desktop filesystem/global plugins; desktop shell and arbitrary
browser-control tools are not part of this product scope. Remote teams require
configuration. Deployment, real-provider quality, Cloud Run process-loss checks,
actual paid generation and final exported-media quality still require release
acceptance; local SDK/mock-provider tests do not prove those external outcomes.

Verification: 517 API tests, 22 actual Pi SDK tests and 63 frontend tests passed,
with zero failures/errors/skips. Active Pi host coverage is 88%. Vue/runtime
types, translation checks, production web build/sync and diff checks passed.
Isolated browser acceptance verified question reload/answer, steering, queued
follow-up, delegated completion, direct child continuation/cancel, parent report
reload and usage/budget display. The model transport was synthetic, with the real
SDK/session/tool path. Browser-discovered renderer, child observation, local-only
snapshot and usage-shape bugs have regression coverage; these tests do not prove
the absence of further bugs. [Browser acceptance screenshot](/private/tmp/linglonglab-pi-capabilities-browser.jpg).

## Reset and release scope

Local pre-Pi histories were moved to a private recoverable archive; production
cloud history was not deleted. Model configuration, production identifiers and
project/canvas/media data are unchanged. No deployment occurred.
Local browser acceptance uses the real Pi SDK with a synthetic model transport;
it does not establish real-provider or deployed Cloud Run behavior. Container
build remains a release gate: the local attempt failed while fetching the Python
base image from Docker Hub with a TLS handshake timeout, before application build.

## Creative, research and media tool corrections (2026-10-12)

Enabled skill instructions can be read for the requested task without implicitly
activating external research. Creative strategy can use existing verified material
for a preliminary proposal. Research skills retain explicit invocation metadata;
selecting an ordinary `/skill:` does not automatically enable web search.

When all attempted search providers fail, the Agent receives a structured
`research_incomplete` receipt with an empty source list and per-provider error
codes. Both English and Chinese tool cards display the incomplete state, including
restored history. The Agent is instructed to disclose the gap, continue with
verified workspace material or user-provided links, and never invent sources or
claim a completed competitor audit. Search challenges are classified separately
from empty results. The current default remains DuckDuckGo HTML; this change does
not provision another external search provider or guarantee search availability.

Media tools default to the deployment-configured model for the requested media
type. The Agent supplies production parameters without looking up or inventing
model IDs. The host resolves and validates the exact provider/model before paid
approval and request hashing. Explicit configured pairs remain compatible with
existing sessions. Partial pairs and absent defaults fail before approval. Model
configuration and enabled media capability are provided as context, without keys;
configured availability is not evidence of a successful live generation call.

Acceptance includes the real Pi SDK callback path with simulated provider
responses: failed search followed by reading a project document and fetching a
supplied URL, and creative skill reading without external research permission.
Browser acceptance verifies incomplete search status in both interface languages.
No paid provider calls or production deployment were performed in this correction.

Correction validation: 591 backend tests, 53 native runtime tests and 86 frontend
tests passed, with zero failures or skips. Workspace type checks, the Vue
translation audit, production web build/sync and diff checks passed. Browser
model/search responses were synthetic; no live search or paid-generation
availability was asserted.
