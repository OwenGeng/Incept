# P-01 · Project library parity audit

**Date:** 2026-09-22
**Scope:** Video Production project library and persistent production header
**Method:** Black-box reference observation plus Linglong active-route and
direct-caller inspection. No ArcReel source code, assets, wording, components or
styles were used as implementation material.

## Evidence inspected

### Reference product

- Running ArcReel project library, inspected through its accessibility tree on
  2026-09-22.
- Its public README workflow description.

Observed reference behaviour:

| Area | Observable behaviour |
| --- | --- |
| Persistent header | Brand link, project search, asset-library entry, ZIP import, project creation, external-agent connection, settings with configuration state. |
| Summary | Time-sensitive studio greeting, production summary and five project-state counters. |
| State filter | All, Preparation, Script, Production and Completed can be individually filtered. |
| Resume card | Shows a project cover, style state, workflow phase, progress, episode/character/prop metrics, and an editor deep link. |
| Library | Shows a project count and a clear new-project entry alongside the project collection. |
| Partial data | The observed reference had one Script-stage project with no wrapped or in-production episodes; the resume card still rendered a meaningful 0% state. |

### Linglong active product

| Evidence | What it proves |
| --- | --- |
| apps/web/app/video-production/page.tsx | The Video Production home is the canonical library route. |
| apps/web/app/video-production/layout.tsx | The route requires authentication unless dev bypass is explicit, and denies the agency role. |
| VideoProductionHub | The library reads persisted productions, offers local query and phase filters, renders five counters, featured work, loading/error/empty states and project deep links. |
| VideoProductionShell | Persistent header exposes home, static search field, asset library, project creation and delivery settings. |
| incept-api production functions | The list view reads persisted production records through the production API. |

The Linglong local UI could not be browser-automated in this review because the
host browser extension blocks localhost. Therefore Linglong visual and
click-through claims below rely on active-route code inspection, not a completed
browser run.

## Detailed parity matrix

| Capability | Reference behaviour | Linglong current state | Status | Earliest gap / risk | Smallest next slice |
| --- | --- | --- | --- | --- | --- |
| Canonical library | Dedicated project-listing route | Dedicated authenticated production route | Partial | Browser journey not captured | Run canonical browser test after localhost access is restored. |
| Header brand | Brand reliably returns to project list | Linglong mark links to production home | Partial | No click-through proof | Add browser acceptance case. |
| Project search | Header-level project search is actionable | Header search routes to the canonical library query; main library search filters loaded records | Partial | Browser evidence is still absent | Add search/reopen browser acceptance case. |
| Asset library | Header exposes asset library | Header links to production assets | Partial | Destination not yet audited | Audit P-13 and prove asset attachment/back navigation. |
| Project import | ZIP import appears in reference header | No Linglong import capability | Missing / excluded until specified | A visual placeholder would mislead | Decide if independent project archive import belongs in scope. |
| Project creation | Create action starts a creation workflow | Header and empty state open New Project | Partial | Creation has not been re-opened and proven | P-02 create, save, reload library and open project. |
| Agent/config state | Reference surfaces configuration state | Linglong does not show provider/agent configuration here | Excluded from lobby parity | Configuration is platform-owned | Keep out of lobby unless separately specified for admins. |
| Editorial summary | Greeting and project outcome summary | Editorial headline plus delivered/active counts | Partial | Count semantics not fully defined | Define project count, active, delivery and blocked metrics. |
| Five-phase ledger | Total, Preparation, Script, Production, Completed | Same five categories derived from Linglong fields | Partial | Mapping inferred from stages/shots | Add boundary fixtures for stages and final assets. |
| Phase filter | Individual filters update collection | Filter buttons update local collection | Partial | No browser/no-match evidence | Add filter and no-match acceptance cases. |
| Continue editing | Featured active project and deep link | Featured persisted project opens workspace | Partial | Summary lacks durable progress contract | Define progress from durable production hand-offs. |
| Partial-project card | Meaningful 0% state with phase metrics | Fallback title, brief, phase and shot count | Partial | Missing asset and blocked-task metrics | Add only metrics Linglong can prove. |
| Project collection | Count, cards and new-project entry | Compact archive, metadata, search and deep links | Partial | Missing canonical stage badge/activity event | Derive stage and last activity from durable audit state. |
| Load/error/empty | Partial project observed; other states not inspected | Spinner, error, no-project and no-match UI exist | Partial | Error has no retry action | Add retry, empty and failure acceptance paths. |
| Responsive use | Not observed at second viewport | Responsive CSS exists | Unknown | CSS alone is not evidence | Capture desktop/narrow screenshots and keyboard journey. |

## Page contract

### Production library

- **Entry:** production home, Linglong header logo, workspace back navigation,
  and post-create redirect.
- **Outcome:** find a project, understand state, resume it, or start one.
- **Reads:** project list and summary fields for the active workspace.
- **Writes:** none directly; filters and search are local view state.
- **Primary actions:** create a project; open a project.
- **Secondary actions:** phase filter, search, asset library and delivery.
- **Async states:** list loading and list error are rendered; retry is missing.
- **Empty states:** no projects; no matching projects.
- **Permissions:** authenticated non-agency users.
- **Chain hand-offs:** project record to intake, assets, and workspace.

### Acceptance cases

| Case | Given | When | Then | Evidence |
| --- | --- | --- | --- | --- |
| Load | Authorized user with projects | Open library | Persisted projects, counters and a resume card appear | Code inspection only |
| Search | At least two named projects | Enter unique title | Only matching item remains | Code inspection only |
| Filter | Projects in two phases | Select a phase | Only that phase remains | Code inspection only |
| Open | Listed project | Select open action | Correct project workspace opens | Code inspection only |
| Create | Empty or populated library | Create project | New project appears after return/reload | Not yet run |
| Empty | No records | Open library | Clear start-project state appears | Code inspection only |
| Failure | List request fails | Open library | Error is actionable and can retry | Incomplete: error only |
| Permission | Agency user | Open library | Redirect to unauthorized route | Route code inspection only |

## Scorecard

| Capability | Status | Evidence | Earliest blocker | Smallest next slice |
| --- | --- | --- | --- | --- |
| P-01 project library | Partial | Reference accessibility tree; Linglong active route/callers | No runtime acceptance evidence | Add filter/search/reopen browser test. |
| P-14 lobby visual system | Partial | Approved lobby master and current components | New Project and Workspace retain legacy purple styling | Freeze a New Project master before changing that route. |

## Decisions needed later

1. Is independent project archive import a required Linglong capability, or
   should it be explicitly absent? It should not be added merely to imitate a
   reference header button.
2. Should external-agent/model configuration be an internal admin surface? It
   must not be silently added to the production lobby or inferred from
   providers.
