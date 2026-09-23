# P-03 · Workspace stages and resumability audit

**Date:** 2026-09-22
**Scope:** active production workspace, project stages and reloadable state.
**Method:** Black-box observation of a reference Script-stage project plus
inspection of Linglong's canonical project route, workspace caller, API and
persisted project model. No reference source is used as implementation material.

## Reference observation

The observed reference project workspace is not a single prompt page. It
visibly presents:

| Area | Observable behaviour |
| --- | --- |
| Project header | Return to Projects, project identity/type/format, four phases, notifications, usage record, project export, asset library and settings. |
| Project phases | Preparation, Script, Production and Completed are all visible; Script is visibly the active phase for the inspected project. |
| Left workspace index | Overview, Source files, Characters, Scenes, Props and a domain-specific asset category each expose zero-count states. |
| Work inventory | The project video appears as a named Draft in a Video section. |
| Workspace controls | Sidebar can collapse and an agent panel can open. |
| Blank script state | The active Script phase renders editable content controls rather than pretending the project has produced media. |

The reference phase names and exact panels are not copied into Linglong. The
observable contract is that an operator can tell what phase is active, what
inputs are missing, what durable work items exist, and where to resume.

## Linglong evidence

| Evidence | What it proves |
| --- | --- |
| Canonical project route | A persisted production ID is passed to the workspace component. |
| Workspace refresh function | Project record and workspace assets are fetched together; selected shot is restored if it still exists, otherwise first shot is selected. |
| Project model/store | Brief, setup, contracts, script, design, shots, audio, edit and final output are persisted under one production record. |
| Stage model | Internal stage values cover direction, script, design, storyboard, generate, audio, edit and deliver. |
| Workspace UI | Header renders six derived phases; side index renders overview, source assets, creative direction, design system and shot list; central view renders storyboard/takes/review; copilot panel remains visible. |
| Existing tests | Focused API tests cover keyframe/take constraints and selected-take rendering gate; no workspace reload/browser tests exist. |

## Detailed parity and state matrix

| Capability | Reference behaviour | Linglong current state | Status | Gap / risk | Smallest next slice |
| --- | --- | --- | --- | --- | --- |
| Deep-linked project workspace | Project-specific URL restores a named project | Project ID route fetches persisted production and assets | Partial | No runtime deep-link/reload evidence | Add API/browser project reload test with one seeded project. |
| Visible phase map | Four clear operator phases with active state | Four operator phases now derive from persisted project fields; the phase strip is not interactive | Partial | Entry/exit criteria are still partly inferred from legacy stage/shot fields | Define and test one owned phase-transition contract. |
| Current state accuracy | Script-stage project shows Script, empty inputs and Draft video | Current stage is inferred from final asset, render job, shots and stage field | Partial | Heuristic can report Generate/Deliver without an explicit reviewed phase decision | Persist or derive status only from documented durable hand-offs. |
| Missing inputs | Counted source files, characters, scenes and props | Side index has source asset count and shot count; other entries call copilot prompts | Partial | Counts/actions are uneven and some menu actions mutate through opaque agent conversation | Make each surface a real read/write page contract before it is advertised. |
| Work inventory | Named draft in Video inventory | Selected shot list; no explicit project-level edit revision inventory | Partial | Project-level work and shot-level candidates are conflated | Add durable revision/timeline inventory after selected takes. |
| Blank state | Script work remains editable before generation | No-shots state can ask copilot to build storyboard | Partial | Agent action may blur plan creation and review; no explicit approve-plan state in visible UI | Add editable plan draft and explicit approval before keyframes. |
| Asset continuity | Dedicated source/character/scene/prop surfaces | Design system is an agent-prompt entry; current workspace has no direct asset role editor | Partial | Cannot inspect or correct the bound inputs on a shot in this UI | P-05/P-13: role-based asset manifest and shot bindings. |
| Job state after refresh | Reference exposes notifications and usage controls | Linglong refreshes after queueing but does not show a persistent jobs/notification surface in workspace | Partial | A queued job can outlive local busy state without clear progress/retry/cancel feedback | Add a persisted job drawer / per-shot job status and polling or explicit refresh. |
| Desktop layout | Dense header/sidebar/canvas structure | Approved white workspace master is implemented with a project header, index, editor and assistant; minimum width remains 1060px | Partial | Narrow viewport/collapsed-sidebar contract is still absent | Add a responsive/collapsed-sidebar acceptance case. |
| Agent assistance | Panel is a secondary contextual tool | Persistent copilot can issue planning/review prompts | Partial | Some sidebar navigation is implemented as agent prompt rather than a stable information surface | Separate navigation/read views from mutating assistant operations. |
| Project export | Header exposes project export | Delivery page exists; independent project archive export not implemented | Missing / excluded until specified | Do not mimic ZIP button without owned archive and audit schema | Decide delivery manifest vs independent archive export in P-10. |

## Required Linglong stage contract

Linglong may keep richer internal stages than the reference, but the workspace
must present an operator map with explicit durable gates:

| Operator phase | Owned records | Entered when | Must be true before next phase |
| --- | --- | --- | --- |
| Preparation | project, brief, asset manifest | draft created | intake saved and required inputs classified |
| Script | direction and script revision | direction approved | scene plan is editable and then explicitly approved |
| Production | design assets, storyboard, keyframes, takes | approved plan exists | every included shot has an explicitly selected take |
| Completed | edit revision, QA report, delivery record | render and QA eligible | delivery result and source manifest are reloadable |

This four-label operator map can contain Linglong's internal Direction, Design,
Storyboard, Generate, Audio and Edit states, but those states must have clear
criteria and must never be changed by a tab click alone.

## P-03 acceptance cases

| Case | Given | When | Then | Current evidence |
| --- | --- | --- | --- | --- |
| Deep link | Existing draft project | Open project URL | Same project identity, phase and work items appear | Code inspection only |
| Reload | Draft with a selected shot | Refresh workspace | Same selected state or deterministic fallback appears | Code inspection only |
| Empty project | Project with no shots | Open workspace | Clear plan-draft action; no generation enabled | Partial |
| Stage gate | Unapproved plan | Attempt keyframe/take action | UI explains prerequisite and does not queue work | Not proved |
| Queued job | Keyframe or take queued | Refresh after request | Job status, target shot, exact inputs and recovery action are visible | Incomplete |
| Failure | Generation fails | Reopen workspace | Error and retry/cancel/remediation are visible | Incomplete |
| Narrow viewport | Open workspace on narrow viewport | Use navigation and editor | Usable collapse or alternate layout | Unknown |

## Scorecard

| Capability | Status | Evidence | Earliest blocker | Smallest next slice |
| --- | --- | --- | --- | --- |
| P-03 stages and resumability | Partial | Reference workspace observation; Linglong route/component/API/model inspection | Async job recovery is not surfaced and phase transition gates are not yet independently tested | Define durable gates and add one reloadable draft-project acceptance test. |
| P-14 workspace visual system | Partial | Approved Image-light master and rebuilt workspace component | Browser visual comparison and responsive contract are not yet proven | Run desktop/narrow screenshot and keyboard acceptance checks. |
