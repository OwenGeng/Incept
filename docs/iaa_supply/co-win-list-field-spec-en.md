# Demand & Supply Co-win List Field Specification

> English version

> **Purpose:** The tracker records customer-level facts and progress; the operating model records the workflow; supporting materials provide reusable knowledge.

## 1. Field groups

### A. Identification fields

| Field | Rule |
|---|---|
| Quarter | Use a fixed format, for example `2026 Q3`. |
| Snapshot date | Date on which the quarterly list was generated. |
| Company name | Name used to group the company. |
| China entity | Chinese legal entity. Use `Unknown` when unavailable; do not leave it blank. |
| Publisher name | Publisher name from the source data. |
| Bundle | Primary duplicate-control key; keep it as complete as possible. |
| Base | City / location; mark for validation if unknown. |
| Gaming / Non-Gaming | Fixed dropdown value. |

### B. Source and priority

| Field | Rule |
|---|---|
| Lead source | `SensorTower` / `GatherOne self-sourced` / `Moloco referral` / `Other` |
| Priority | Use the program priority, such as `P1`, `P2`, or `P3`, and retain the recommendation rationale. |
| UA signal | Record the source or basis for the UA assessment. |
| IAA / SDK signal | Record the basis for the IAA monetization or SDK-potential assessment. |
| Moloco history | `No` / `Existing` / `Historical` / `Unknown` |

### C. Ownership and execution

| Field | Rule |
|---|---|
| Moloco sales owner | Populate only when the account is actually claimed or an introduction is required. |
| GatherOne sales owner | Populate after GatherOne assigns a sales owner. |
| Claim status | `Pending` / `Claimed` / `Released to GatherOne` / `Reserved` |
| Stage | Use a fixed stage value; see the definitions below. |
| Last update | Most recent material action or conclusion. |
| Next action | A specific next action; do not enter only “follow up.” |
| Next action due | Due date for the next action. |
| Last updated date | Date the record was most recently updated. |

### D. Support and closure

| Field | Rule |
|---|---|
| Support needed | `None` / `Sales intro` / `Business` / `SDK technical` / `Data` / `Other` |
| Blocker category | `No contact` / `No response` / `Technical` / `Commercial` / `Ownership` / `Other` |
| Support owner | Michael, Supply, or another named owner. |
| SDK status | `Not assessed` / `Evaluating` / `In progress` / `Live` / `Not applicable` |
| UA status | `Not assessed` / `Evaluating` / `In progress` / `Live` / `Not applicable` |
| Launch / spend evidence | A link, date, or data definition. Use data where actual spend is available. |
| Update | Record the current change in a short sentence; do not use this field as a long chat log. |

## 2. Stage definitions

| Stage | Entry condition | Exit condition |
|---|---|---|
| Candidate | Data screening only is complete. | Passes validation into the quarterly list, or is excluded. |
| Pending Claim | In the quarterly list and awaiting Sales judgment. | `Claimed` / `Released to GatherOne` |
| Assigned | A current execution owner is known. | Effective customer contact is completed. |
| Contacted | Effective customer contact has been completed. | Customer responds, or the record moves to `No Response`. |
| Opportunity Confirmed | Customer confirms a clear opportunity. | Moves to SDK/UA execution or closes. |
| SDK/UA In Progress | Evaluation, development, testing, or commercial execution has started. | `Launched` / `Blocked` / `Closed` |
| Launched | There is launch or actual-spend evidence. | Moves into ongoing growth tracking. |
| Blocked | A clear blocker exists and a support request has been recorded. | Blocker is resolved, transferred, or closed. |
| No Response | Repeated outreach was completed under the program rule without a response. | A new response returns the record to `Contacted`. |
| Not a Fit | Clearly outside the program target. | Normally not reopened unless conditions change. |
| Closed | Completed, discontinued, or transferred to another process. | Create a new record only when a new opportunity emerges. |

## 3. Claim rules

1. A Sales claim represents relationship and introduction responsibility; it does not automatically claim all GatherOne day-to-day execution.
2. A GatherOne claim represents scalable outreach and update responsibility; it does not authorize GatherOne to make technical or commercial commitments on Moloco’s behalf.
3. One Bundle can have only one current execution owner. A Moloco relationship owner may remain as a collaborating owner.
4. When the claim window ends without a documented reason to retain the account, release it to GatherOne by default.
5. Every handoff must record the transfer date, previous owner, receiving owner, and next action in the tracker.

## 4. Update-quality checks

Before every biweekly review, check:

- whether the record has an owner;
- whether it has a recent update date;
- whether it has a next action and date;
- whether a `Blocked` record has a blocker category and support owner;
- whether SDK/UA status matches actual progress;
- whether duplicate Bundles exist; and
- whether an active record has been stale for more than 14 days.
