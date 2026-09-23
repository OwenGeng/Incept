# Moloco IAA SMB Program
## Q3 2026 Operating Overview and Working Plan

> **Purpose:** This document is the shared operating reference for the Moloco IAA SMB program in Q3 2026. It explains the program objective, the working model, the responsibilities of each team, and the rules used to move an opportunity from a data signal to a verified business outcome.

## 1. Program objective

The program identifies high-potential small and medium-sized mobile developers and creates a repeatable path to develop both sides of the Moloco flywheel:

- **Supply:** help suitable publishers evaluate and adopt the Moloco Publisher SDK, creating additional IAA supply; and
- **Demand:** identify suitable user-acquisition opportunities where the same developer may use Moloco DSP.

Q3 is an operating-validation quarter. The aim is to run a disciplined, repeatable joint motion across Intelligence, Moloco Sales, GatherOne, and Supply—not simply to add more names to a list.

The program is successful when the team can reliably identify qualified opportunities, assign clear ownership, move customers through the appropriate commercial path, and verify SDK or UA progress with evidence.

## 2. The operating model

The program uses a simple two-lane coverage model.

- **Moloco Sales** owns strategic relationship judgment, introductions, and accounts that should remain under direct Moloco coverage.
- **GatherOne** owns scalable SMB outreach, day-to-day follow-up, customer updates, and execution after an opportunity is released or assigned.
- **Supply** provides enablement, technical guidance, and escalation support when an opportunity requires it. Supply does not own routine SMB prospecting.
- **Intelligence** provides the candidate pipeline, data context, prioritization, and result validation.

The operational unit is a **Bundle**. Company-level relationships remain visible, but every active Bundle must have one current execution owner and one clearly defined next action.

```text
Intelligence signal
        ↓
Internal qualification and route selection
        ↓
Moloco relationship review / GatherOne assignment
        ↓
Customer outreach and opportunity confirmation
        ↓
SDK and/or UA progress
        ↓
Launch or spend evidence and quarterly learning
```

## 3. What enters the Q3 working pipeline

The program focuses on Chinese-origin mobile developers with a credible IAA, SDK, UA, or co-win opportunity that is not already fully covered by Moloco.

The monthly Intelligence pipeline combines market, download, UA, Moloco-history, publisher, and Supply context. Candidates are reviewed before they enter the quarterly execution queue.

### Priority and route

- **P1** opportunities receive the earliest relationship review and Agency-routing attention. They have the strongest current data signals for an IAA or Hybrid opportunity.
- **P2** opportunities enter the normal quarterly review queue when the data supports a credible commercial path.
- **P3** records remain for observation or additional validation; they do not enter the active P1/P2 execution queue by default.

For every qualified Bundle, the owner records one primary route:

- **IAA-first:** prioritize Publisher SDK / IAA activation.
- **UA-first:** prioritize Moloco DSP / user-acquisition discussion.
- **Co-win:** pursue both paths where the customer context supports them.
- **Observe:** retain the record for a later review instead of starting active outreach.

Priority is a starting point for review, not a substitute for business judgment. Relationship coverage, customer fit, product mix, reachability, and existing Moloco context are considered before a Bundle is released for execution.

## 4. Team responsibilities

| Workstream | Primary owner(s) | Working responsibility |
|---|---|---|
| Program coordination and data closure | Owen | Own program cadence, prioritization, pipeline quality, cross-team coordination, escalation, and reporting. |
| Non-Gaming opportunity review | Daniel | Provide opportunity and relationship input for Non-Gaming prospects. |
| Gaming opportunity review | Clara | Provide opportunity and relationship input for Gaming prospects. |
| Agency coordination | Michael / Anita | Coordinate GatherOne, facilitate Moloco introductions, and route commercial support needs. |
| Supply enablement and escalation | Owen / Daniel / Morden / Jim / assigned SME | Provide publisher context, SDK guidance, and support for material or complex issues. |
| Agency execution | GatherOne | Match and assign sales owners, conduct outreach, progress customer conversations, and keep customer-facing status current. |

The role boundary is deliberate: a Moloco relationship owner may retain responsibility for an introduction, while GatherOne remains responsible for the daily execution that follows. A transfer is complete only when the receiving owner is known and the next action is recorded.

## 5. End-to-end workflow

### Step 1 — Discover and refresh

Intelligence refreshes the monthly candidate data and reviews new P1/P2 signals. The review considers Bundle identity, Publisher context, download scale and trend, monetization signals, active UA signals, Moloco history, and relevant Supply context.

GatherOne may also submit self-sourced opportunities. These are validated using the same Bundle-level review before being added to the working pipeline.

### Step 2 — Qualify and select the route

Owen completes the internal qualification for candidates that may enter the quarter. The result is one of four outcomes:

| Outcome | Meaning |
|---|---|
| **Qualified** | Ready for the quarterly execution queue and relationship review. |
| **Needs Review** | Potentially relevant, but a material fact or relationship decision is still missing. |
| **Hold** | Retained for a future refresh without current execution effort. |
| **Exclude** | Not suitable for the program or already sufficiently covered. |

Each Qualified Bundle must have a priority, a primary commercial route, an owner recommendation, and a next action with a date.

### Step 3 — Review relationships and assign execution ownership

Moloco Sales and the relevant relationship owners determine whether an account should be retained, introduced, or released to GatherOne. Existing Moloco or Supply coverage is checked before outreach begins.

Once GatherOne accepts a Bundle, it assigns one sales owner and records the first action. A Bundle must not have two competing daily execution owners.

### Step 4 — Conduct customer outreach and confirm the opportunity

GatherOne leads the customer conversation and records meaningful progress. An effective update includes the outreach date, the customer response, the current status, and a specific next action.

The objective is to confirm whether the customer has a viable IAA/SDK, UA, or co-win opportunity—not merely whether an initial message was sent.

### Step 5 — Progress SDK and/or UA work

When a customer is interested, the appropriate commercial path is progressed. GatherOne continues customer coordination; Moloco teams provide the necessary relationship, business, or technical support.

Support requests are routed with enough context to act on them: Bundle, platform, integration or commercial stage, issue description, support owner, and customer deadline where relevant.

### Step 6 — Verify results and close the loop

SDK launch, coverage, tests, publisher performance, and UA progress are recorded with a traceable fact wherever possible. Closed or paused opportunities also retain a clear conclusion so that the next review does not restart the same work without context.

## 6. Working rules for the quarterly tracker

The quarterly tracker is the working record for ownership, customer progress, next actions, support requests, and outcome evidence. It is not a replacement for the underlying Intelligence data sources.

The following rules apply to every active Bundle:

1. Use `quarter + normalized bundle` as the duplicate-control key.
2. Maintain one current execution owner.
3. Record a specific next action and its due date; “follow up” alone is not sufficient.
4. Update the record after each material customer action or conclusion.
5. Preserve manual workflow fields—owner, stage, feedback, next action, and support notes—when monthly Intelligence data refreshes.
6. Record blockers with a category and a named support owner.
7. Use evidence, dates, or an agreed data definition for launch and spend outcomes.

Records without an owner, a next action, or a recent update are reviewed before the next pipeline meeting. A record that has not been updated for more than 14 days requires a clear next step, a return to review, or a Hold/Closed decision.

## 7. Tools and data responsibilities

| Tool or data layer | Purpose in the workflow |
|---|---|
| **Intelligence pipeline** | Produces refreshed candidate signals and data context for qualification and prioritization. |
| **Bundle Lookup** | Supports a focused review of one or more Bundles; it informs decisions but does not automatically add a customer to the quarterly queue. |
| **Quarterly tracker** | Records ownership, stage, customer actions, support needs, and verified outcomes for the active quarter. |
| **Quarterly source sheet** | Provides the current-quarter working context and is updated as the quarter changes. |
| **BigQuery facts** | Supplies read-only source facts and supports evidence-based validation of launch and spend outcomes. |

Monthly data refreshes may update Intelligence fact fields for an existing Bundle. They do not overwrite the manual execution record maintained by the team.

## 8. Operating cadence

### Monthly Intelligence refresh

- Refresh the candidate data and review new P1/P2 opportunities.
- Validate new Bundles before they enter the active quarterly queue.
- Refresh existing Intelligence facts without duplicating records or replacing manual execution fields.

### Biweekly pipeline review

Participants review active opportunities, missing ownership, stale updates, support blockers, and actions that require cross-team coordination. The discussion focuses on decisions and next steps, rather than re-reading every row.

### Ongoing support escalation

- Relationship, introduction, and commercial coordination: Michael and Owen.
- Priority, data, and pipeline questions: Owen, Daniel, and Clara.
- SDK integration, mediation, and technical issues: Supply team.
- Issues that materially affect a customer launch or exceed the expected response window: escalated by Owen with the relevant owners.

## 9. How progress is assessed

The program tracks the full conversion path rather than only the size of the prospect list:

- qualified P1/P2 Bundles;
- Bundles accepted and assigned for execution;
- effective customer contacts and confirmed opportunities;
- SDK and UA opportunities in progress;
- Bundles with launch or spend evidence; and
- blocker resolution and update quality.

The same review also captures practical learning: which data signals identify the most actionable customers, which handoffs are effective, and which recurring customer questions should be addressed through reusable enablement.

## 10. Detailed operating references

The following documents provide the detailed rules behind this working plan:

1. [Prospect Identification & Prioritization SOP](prospect-identification-and-prioritization-sop-en.md) — the monthly qualification, priority, routing, and queue-entry rules.
2. [Demand & Supply Co-win List Field Specification](co-win-list-field-spec-en.md) — tracker fields, fixed statuses, ownership rules, and update-quality checks.

This document is the program-level reference. The quarterly tracker remains the source of truth for customer-level status and actions.
