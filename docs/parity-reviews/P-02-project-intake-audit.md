# P-02 · Project intake parity audit

**Date:** 2026-09-22
**Scope:** creation of a new Video Production project and its durable intake
state.
**Method:** Black-box observation of the reference new-project workspace, then
inspection of Linglong's active create page, API route, state model and focused
production tests. No reference source is used as implementation material.

## Reference observation

Opening the reference new-project route creates an empty project workspace rather
than a simple detached form. The observable state includes:

| Area | Observable behaviour |
| --- | --- |
| Project identity | A named project selector begins as Untitled Project. |
| Workflow | Four visible phases: Preparation, Script, Production, Completed. |
| Inputs | Source files, characters, scenes and props each begin at zero. |
| Episode work | Episode search is available; adding is disabled before prerequisites are met. |
| Operating controls | Notifications, usage/cost summary, project ZIP export, asset library and settings are reachable from the workspace header. |
| Initial state | The blank project has a clear Overview entry and a zero-episode empty state, rather than implying that production has already begun. |

This describes observable behaviour only. Linglong does not need to reproduce
the reference naming, episode model, ZIP schema, cost presentation, or layout.

## Linglong evidence

| Evidence | What it proves |
| --- | --- |
| NewVideoProduction component | The create surface offers four Linglong-supported modes: commercial, original short drama, repair and CTV composition; title, brief, duration and aspect ratio are collected before navigation. |
| Production create API | A project record is created with title, duration, ratio and resolution. |
| Production update API | Brief and video-setup metadata are written in a second request with optimistic revision checking. |
| Production model | The durable project record holds brief, setup, assets, contracts, script, design, shots, edit plan, audio plan, final asset and history metadata. |
| Production store | Creation persists an initial record and initial copilot context; updates reject stale revisions. |
| Focused API test | Existing test proves a later delivery guard requires an explicit selected take. It does not prove creation or intake reload behaviour. |

## Detailed parity and intake matrix

| Capability | Reference behaviour | Linglong current state | Status | Gap / risk | Smallest next slice |
| --- | --- | --- | --- | --- | --- |
| Durable initial project | New route opens an empty project state | Form calls create API then navigates to persisted project | Partial | Happy path has no browser/reload proof | Add create → reload → open-workspace API/browser test. |
| Project identity | Starts with editable untitled identity | Optional title, with mode title fallback | Partial | Title validation and rename timing not specified | Define blank/duplicate/long-title validation and post-create rename. |
| Supported production types | Reference supports its own story and product modes | Linglong explicitly supports commercial, original short drama, repair and CTV | Partial | No mode-specific intake requirements or downstream gates | Define mode contracts; do not add novel adaptation. |
| Brief and constraints | Empty project separates inputs and later planning | Free-text brief and initial type setup are saved in the create request | Partial | No structured claims, audience, market, platform, source-asset or approval inputs on the create screen | Define minimal non-billable intake fields and validation before direction approval. |
| Duration and format | Observable project setup exists, exact creation controls not inspected | 15/30/60 seconds and 9:16/16:9 choices persist | Partial | Resolution is fixed by UI; no reload proof | Include format fields in create/reopen test. |
| Asset manifest | Source files have an explicit empty state | Creation form only describes approved assets in placeholder copy | Missing | No attach/classify action during intake | P-13: attach customer asset, give it a role, reopen and bind it to a shot. |
| Prerequisite feedback | Add episode is visibly disabled before prerequisites | Form lets every mode create a project with no brief or inputs | Partial | Missing explicit intake readiness and reason | Add direction-readiness checklist, without making project creation billable. |
| Async error recovery | Reference blank workspace remains navigable | Project, brief and initial type setup are written atomically; API errors render text on form | Partial | Network failure after server-side success still has no duplicate-prevention/reopen hint | Add idempotency or recoverable draft lookup if retry behaviour becomes a user need. |
| Cost safety | Reference exposes usage even at zero | Creation itself calls no generation endpoint | Partial | No production-create test proves no job/usage side effect | Add API test asserting project creation creates no generation job or usage event. |
| Initial workspace | Blank state shows overview and empty inputs | Workspace loads project and provides a later copilot-driven storyboard action | Partial | Current workspace initial experience is visually legacy and mixes intake with agent prompts | Freeze the New Project and workspace page masters, then make intake visible before generation controls. |

## Intake contract Linglong needs to own

The durable chain starts with a project record, but a project must not be treated
as ready for planning merely because it exists.

| Hand-off | Owner | Explicit action | Minimum persisted state | Reload proof |
| --- | --- | --- | --- | --- |
| Create draft | Project | Create project | type, title, duration, ratio, resolution, creator | Project appears in library after reload |
| Save intake | Project revision | Save intake | brief, market, audience, goal, platform, language, claims, constraints | Reopen form/workspace shows saved values |
| Attach inputs | Asset manifest | Attach and classify | asset identity, source, role, rights/usage note where needed | Reopen shows role and preview |
| Approve direction | Direction decision | Confirm readiness | required inputs and approval decision | Planning controls unlock after reload |

Project creation and draft saving remain non-billable. Planning/generation may
not begin as a silent side effect of either action.

## P-02 acceptance cases

| Case | Given | When | Then | Current evidence |
| --- | --- | --- | --- | --- |
| Create | Authorized internal user | Create a commercial draft | One persisted draft opens with requested format | Code inspection only |
| Mode | Each of four supported types | Select type and create | Correct Linglong type persists | Code inspection only |
| Reload | Newly created project | Refresh library and workspace | Same title, brief and setup are visible | Not yet run |
| Empty brief | User supplies no brief | Create draft | Draft is allowed but visibly not ready for direction | Incomplete |
| Update failure | Create succeeds, setup update fails | Retry/open draft | User can recover without accidental duplicate | Incomplete |
| No billing | Create and save intake | Inspect jobs and usage | No generation task or usage event exists | Not yet tested |
| Permission | Agency user | Open creation route | Access is denied by parent layout | Route code inspection only |

## Scorecard

| Capability | Status | Evidence | Earliest blocker | Smallest next slice |
| --- | --- | --- | --- | --- |
| P-02 project intake | Partial | Reference empty-workspace observation; Linglong create route/API/model inspection | No executable reload test or structured intake gate | Create a durable draft-and-intake vertical slice with API tests and a browser journey. |
| P-14 New Project visual system | Missing | Current create page uses legacy purple styling; no approved page master | Visual implementation should not proceed from code alone | Produce and approve the New Project page master using the fixed Image-module light system. |
