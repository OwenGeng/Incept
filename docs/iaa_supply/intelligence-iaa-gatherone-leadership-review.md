# Intelligence: IAA × GatherOne Co-win Program
## Leadership Review, Operating Model, and Q3 2026 Recommendations

> **Status note:** This is a leadership-review draft, not the primary project operating document. The current canonical design is the workflow-first blueprint in [`project-owner-workflow-blueprint.md`](./project-owner-workflow-blueprint.md). Use that document to run the project; use this file only when a leadership-facing summary is needed after the workflows are validated.

> Prepared for leadership review
>
> Project owner: Owen
>
> Current operating partners: Michael / GatherOne / Moloco Sales / Supply Team
>
> Scope: Intelligence-led identification and activation of IAA, SDK, and UA opportunities among Chinese-origin mobile app companies

## 1. Executive Summary

Intelligence has built the core capability to identify Chinese-origin mobile app companies with potential across two sides of the Moloco flywheel:

1. **Supply opportunity:** the app may benefit from integrating the Moloco publisher SDK and opening additional IAA demand.
2. **Demand opportunity:** the company may have existing or potential user acquisition (UA) spend that could become Moloco advertiser demand.

The current opportunity is not a lack of data. The opportunity is to turn the data into a repeatable, multi-party operating system.

The current `demand&supply co-win list` workbook is already being used as a prospect pool, agency work queue, reference dataset, SQL output, and progress tracker. This makes it difficult to answer basic leadership questions reliably:

- Which accounts are actually in scope for this quarter?
- Who owns the next action for each account?
- Which accounts have been accepted by GatherOne?
- Which accounts require Moloco Sales introduction?
- Which accounts are blocked on SDK support?
- How many accounts have converted into live SDK supply or UA spend?
- What incremental value has been created?

### Recommendation

Approve a light-weight operating model with four principles:

- **Separate data layers:** raw source, quarterly snapshot, execution queue, and reporting.
- **Use Bundle as the operational unit:** company-level relationships remain visible, but each Bundle has one execution owner and one current stage.
- **Run a two-lane coverage model:** Moloco Sales focuses on strategic relationships and introductions; GatherOne owns scalable SMB outreach and day-to-day follow-up.
- **Make Supply support reusable:** Supply Team provides validated training, documentation, examples, and escalated technical support rather than owning SMB prospecting.

The program should be measured by activated supply and demand outcomes, not by the number of rows added to a spreadsheet.

## 2. Why This Program Matters

The project addresses a structural coverage gap:

- Large publisher accounts receive disproportionate Supply Team attention.
- A long tail of Chinese-origin developers has meaningful overseas scale but may not yet be covered by Moloco SDK or Moloco UA.
- Moloco Sales has limited capacity to conduct detailed outreach to every SMB account.
- GatherOne can provide scalable outreach capacity, but needs qualified data, clear ownership, and sufficient SDK knowledge.

The strategic thesis is a potential two-sided flywheel:

```text
Data signal → qualified company / Bundle → agency outreach → SDK or UA activation
      ↑                                                   ↓
      └──────────── spend and launch data ←───────────────┘
```

This is a portfolio approach. Individual SMB accounts may be small, but a repeatable activation engine can create aggregate publisher supply, advertiser demand, and future cross-sell opportunities.

## 3. What Has Been Built

The Intelligence capability already includes the main building blocks:

- Monthly Cold Prospect Pipeline using BigQuery, SensorTower data, and company enrichment.
- SDK / UA overlap analysis and prioritized prospect segments.
- Separate IAA, IAP, and Hybrid logic where the commercial motion differs.
- Historical Moloco advertiser matching.
- Bundle comparison against external data sources.
- Prospect tracking and launch-status checks using actual Moloco spend signals.
- A working Google Sheet used for cross-team coordination.
- An initial GatherOne operating model, SDK playbook, and co-win list field specification.

This means the project has progressed beyond a research exercise. The next stage is operational discipline and measurable conversion.

## 4. Current State of the Shared Workbook

The workbook reviewed is titled `demand&supply co-win list` and was last modified on August 11, 2026. It is valuable as a working artifact, but it is not currently a controlled operating database.

### 4.1 Observed structural issues

The workbook contains at least six different content blocks:

| Content block | Current role | Problem |
|---|---|---|
| Company prospect list | Candidate discovery and routing | Mixes source data, sales routing, agency notes, and status in one wide table |
| GatherOne / agency list | Execution queue | Contains deadline text in headers, free-text progress, bonus estimates, and support requests without a normalized workflow |
| Bundles Contact | Bundle handoff helper | Stores many Bundles as a comma-separated string instead of one Bundle per row |
| New Publisher Projection / large reference table | Supply reference or Top-2000 data | A large operational dataset is mixed into the same workbook as the agency workflow |
| Custom query output | Spend validation | SQL text and query output are embedded in the workbook, making it hard to maintain and audit |
| China entity lookup | Enrichment reference | Lookup data is mixed into the same operational file and includes unnamed columns |

The large reference block contains more than 2,000 records and visible `#REF!` errors. The exported content contains approximately 4,000 literal `#REF!` values in that block. This is not only a visual issue: it means users cannot distinguish a valid zero, a missing value, and a broken formula.

The workbook also has `Unnamed` columns and summary values embedded in header rows. This indicates that raw exports, manually inserted columns, and formula-driven data are being combined without a stable schema.

### 4.2 Data quality and control risks

The current structure creates five material risks:

1. **Ownership risk:** the workbook has relationship and routing fields, but the next-action owner, due date, and execution stage are not consistently separated.
2. **Duplicate risk:** company-level and Bundle-level records are mixed; the same company or Bundle can appear in multiple areas without a clear master record.
3. **Staleness risk:** fields such as `DDL 8/11` are embedded in headers rather than represented as a date field that can be updated each cycle.
4. **Logic risk:** manual column changes have already caused Apps Script column-mapping issues and forced the Agency List export to be disabled.
5. **Access risk:** the current permission metadata indicates that anyone with the link has writer access. This should be reviewed immediately and replaced with controlled sharing or protected ranges.

### 4.3 Leadership interpretation

The workbook is showing a governance problem, not an individual execution problem. Different teams are using the same file for different purposes:

- Intelligence wants to preserve data provenance and analytical context.
- Moloco Sales wants relationship and routing information.
- GatherOne wants a short action list with clear next steps.
- Supply wants technical context only when support is required.
- Leadership needs a small number of reliable outcome metrics.

One flat sheet cannot serve all five needs safely. The solution is not simply to delete columns; it is to separate the layers while keeping one controlled Bundle-level execution view.

## 5. Recommended Information Architecture

The current workbook should be reorganized into the following tabs or equivalent linked tables:

### `00_Readme_Definitions`

Purpose, scope, owner, update cadence, status definitions, priority definitions, and contact points.

### `01_Q3_2026_Master_Snapshot`

Quarterly frozen snapshot generated from the monthly pipeline. This is the accountable source for what entered the Q3 program.

Minimum fields:

- Quarter and snapshot date
- Company and China entity
- Publisher and Bundle
- Base and Gaming / Non-Gaming
- Lead source
- IAA / SDK signal
- UA signal
- Priority and priority reason
- Existing Moloco relationship or history
- Recommended route

### `02_Execution_Queue`

A narrow working table for Moloco Sales, Michael, and GatherOne. One row per Bundle.

Minimum fields:

- Bundle
- Company
- Moloco relationship owner
- GatherOne execution owner
- Claim status
- Current stage
- Opportunity motion: `IAA / SDK`, `UA`, `Co-win`, `Observe`
- Last action date
- Next action
- Next action due
- Blocker category
- Support needed
- Support owner
- Last update

### `03_GatherOne_Submissions`

GatherOne's self-sourced opportunities, kept separate from Intelligence-generated prospects until they pass the minimum qualification check.

Required fields: company, Bundle, source, country/base, monetization signal, UA signal, contact evidence, recommended motion, and GatherOne owner.

### `04_Outcome_Tracking`

Bundle-level activation and value tracking:

- SDK evaluation date
- SDK integration start date
- SDK live date
- First publisher revenue date
- Moloco UA start date
- First UA spend date
- D30 / D90 publisher revenue
- D30 / D90 UA spend
- Current status based on verified data

### `05_Reference_Data_ReadOnly`

Supply Top-2000 data, raw exports, SQL outputs, and lookup tables. This tab should not be edited by Sales or GatherOne.

### `06_Exceptions_and_Data_Quality`

Duplicate Bundles, missing company mappings, invalid or broken formulas, unresolved ownership conflicts, excluded companies, and records requiring manual review.

### `07_Leadership_Dashboard`

Small summary view only. It should show funnel movement and business outcomes, not the full prospect list.

## 6. Recommended Operating Model

### 6.1 Roles

| Role | Primary accountability |
|---|---|
| Owen / Intelligence project lead | Data methodology, monthly refresh, quarterly snapshot, operating cadence, cross-team escalation, outcome review |
| Michael / agency coordination owner | GatherOne relationship, commercial coordination, Sales introductions, support routing, agency follow-up discipline |
| Moloco Sales | Strategic account judgment, relationship ownership, warm introductions, direct ownership where warranted |
| GatherOne | Database matching, seller assignment, scalable outreach, pitch, customer follow-up, status updates, self-sourced opportunities |
| Supply Team | SDK training, technical documentation review, approved cases, office hours, escalated technical questions |

### 6.2 Two-lane account coverage

| Lane | Account type | Day-to-day owner | Moloco Sales role |
|---|---|---|---|
| Strategic lane | High-value, existing relationship, executive-sensitive, or high expected upside | Moloco Sales or named account owner | Own relationship and key commercial steps |
| Scale lane | SMB and long-tail accounts without a strong existing relationship | GatherOne | Provide an introduction when a relationship exists; otherwise remain informed |

This design addresses the current Sales motivation issue without treating it as a performance failure. Sales time is protected for accounts they consider strategically important, while GatherOne receives the volume it is expected to work.

### 6.3 Handoff rules

1. Intelligence produces a monthly candidate pool.
2. Owen freezes the quarterly snapshot and publishes the qualification logic.
3. Michael opens a short Sales claim window.
4. Sales either claims and introduces, reserves with a reason, or releases the account.
5. GatherOne matches, deduplicates, assigns sellers, and accepts the account into its queue.
6. GatherOne records the first action and next action in the execution queue.
7. Michael routes business and technical requests through one channel.
8. Actual SDK launch and UA spend are verified through data wherever possible.
9. The quarterly review evaluates conversion and changes the next cycle's filters, training, or routing.

## 7. What the Project Has Not Fully Defined Yet

These are the main omissions to resolve before scaling the program.

### 7.1 A clear commercial motion per account

The current list contains IAA, UA, and potential co-win accounts, but the first commercial action is not always explicit. Every record should be assigned one of four motions:

- `IAA / SDK first`
- `UA first`
- `Co-win: SDK + UA`
- `Observe / not ready`

Without this field, GatherOne may pitch the wrong product or wait for an opportunity that is not required for the first conversion.

### 7.2 A definition of “qualified” versus “interesting”

Data signals do not automatically equal a sales-ready opportunity. The program needs gates for:

- verified company and Bundle;
- no conflicting Moloco ownership;
- evidence of overseas scale or commercial activity;
- a plausible IAA or UA motion;
- a reachable business or technical contact;
- no known legal, compliance, or product exclusion.

Only records passing the minimum gate should enter the GatherOne execution queue.

### 7.3 A measurable value model

The program currently emphasizes qualified prospects and potential. Leadership will also need to see expected and realized value:

- expected D90 publisher revenue;
- actual D30 / D90 publisher revenue;
- expected and actual Moloco UA spend;
- time from first contact to SDK live or UA launch;
- activation rate by priority and source;
- cost of agency support or onboarding incentives;
- revenue or spend generated per activated Bundle.

The program should not promise fixed uplift before Supply validates the benchmark. The first target should be a reliable baseline and attribution model.

### 7.4 A formal rule for stale, lost, and recycled accounts

The project needs a common answer to:

- How many unanswered attempts before an account becomes `No Response`?
- When can GatherOne return an account?
- When can an account be recycled into a future quarter?
- What evidence is required to mark `Launched`?
- Who owns a company when one Bundle is strategic but another is SMB?

Without these rules, the pipeline will grow indefinitely and conversion rates will be overstated.

### 7.5 Sales credit and agency incentive design

The proposed model asks Moloco Sales to make a small introduction while GatherOne performs most execution. This is operationally sensible, but the project should define how credit is recognized:

- Sales introduction credit;
- GatherOne execution credit;
- Intelligence sourcing credit;
- Supply enablement contribution.

The mechanism does not need to become a heavy KPI system, but each party should receive visible attribution when an introduction becomes a live account. Otherwise the introduction step will eventually be deprioritized.

### 7.6 Technical support capacity and escalation ownership

The training plan is directionally correct, but the following must be named:

- primary Supply SME;
- backup SME;
- standard response time;
- supported SDK / mediation scope;
- approved customer-facing cases;
- escalation path for issues not covered by the documentation;
- owner responsible for updating the FAQ after a solution is found.

Supply review should be limited to technical accuracy, approved claims, and support feasibility. Supply should not become the default owner of every SMB opportunity.

### 7.7 External sharing, security, and data handling

GatherOne should not receive raw Supply Top-2000 data, internal sales notes, SQL, or unrelated account data. The external view should contain only the fields needed for the agreed outreach motion. Access should be restricted to named collaborators, with protected source and formula ranges.

## 8. Risks and Mitigations

| Risk | Impact | Mitigation | Leadership implication |
|---|---|---|---|
| Sales does not provide introductions | GatherOne cannot use existing relationships; strategic coverage becomes inconsistent | Short claim window, low-effort intro request, visible attribution | Confirm that introductions are an expected collaboration behavior |
| GatherOne lacks SDK knowledge | Opportunities stall at technical questions | Supply-reviewed playbook, training, office hours, single escalation route | Assign Supply SME capacity |
| Workbook logic breaks again | Wrong updates, lost manual data, unreliable reporting | Separate raw/reference data from execution queue; protect schema | Approve a single source-of-truth design |
| Agency optimizes for volume over quality | Many rows, few activations | Qualification gates, stage aging, D90 outcome tracking | Align incentives with activated value, not submissions |
| SensorTower or company matching is imperfect | False positives, duplicate accounts, wasted outreach | Bundle-level dedupe, confidence flag, exception queue, manual review for priority accounts | Accept that data quality needs an operating owner |
| Support requests arrive without context | Supply time is consumed by clarification loops | Mandatory support request template and Michael as single router | Protect Supply capacity through intake discipline |
| No-response accounts remain open | Pipeline becomes inflated | Aging rules and quarterly recycling | Require funnel reporting based on active opportunities |
| Legal or policy exclusions are discovered late | Customer cannot be onboarded after significant effort | Add exclusion reason and compliance check before pitch | Include compliance as a qualification gate |
| Program success is not attributable | Leadership cannot distinguish activity from value | Bundle-level baseline, launch evidence, D30/D90 tracking | Fund the program against measurable outcomes |

## 9. Q3 2026 Execution Plan

### Phase 1: Stabilize the operating base

- Freeze the Q3 qualification logic and snapshot date.
- Create the normalized execution queue with one row per Bundle.
- Remove raw SQL, large reference exports, and lookup tables from the execution view.
- Resolve or quarantine `#REF!` errors and duplicate Bundles.
- Restrict workbook permissions and protect source/formula ranges.
- Name Michael's, GatherOne's, and Supply's operational contacts.

### Phase 2: Launch the two-lane workflow

- Run the Sales claim / introduction window.
- Release unclaimed SMB accounts to GatherOne.
- Require GatherOne to accept, assign, and update each account.
- Classify every active account as IAA-first, UA-first, Co-win, or Observe.
- Start the first SDK training and office-hours cycle.

### Phase 3: Measure the first conversion funnel

Report weekly or biweekly:

- accounts in quarterly snapshot;
- accounts accepted by GatherOne;
- Sales introductions completed;
- accounts contacted;
- opportunities confirmed;
- SDK evaluations and integrations in progress;
- UA opportunities in progress;
- launched Bundles;
- verified publisher revenue or UA spend;
- blocked accounts by blocker category.

### Phase 4: Conduct a quarterly review

The Q3 review should answer:

1. Which data signals predicted conversion?
2. Which priority tiers produced actual value?
3. Did the two-lane coverage model reduce Sales workload while increasing activation?
4. What percentage of technical questions were resolved through documentation?
5. Which accounts should be recycled, escalated, or excluded?
6. What should change in the Q4 screening logic and agency scope?

## 10. Proposed Leadership Decisions

Leadership approval is requested on the following points:

1. **Operating model:** approve Moloco Sales as strategic relationship / introduction layer and GatherOne as the scale execution layer for SMB accounts.
2. **Single source of truth:** approve a separated workbook structure with a controlled Bundle-level execution queue.
3. **Supply enablement:** assign a Supply SME and backup for SDK training, documentation review, and escalated support.
4. **Agency scope and incentives:** confirm the account scope, onboarding incentive logic, and the difference between lead submission and activated value.
5. **Measurement:** approve D30/D90 publisher revenue and UA spend as the primary outcome windows, subject to data availability.
6. **Data access:** restrict external sharing to the approved execution view and remove broad writer access.
7. **Q3 success criteria:** confirm the minimum number of accepted opportunities, active opportunities, SDK launches, and verified UA activations required for the program to continue.

## 11. Final Recommendation

Continue the program, but treat Q3 as an operating-model validation quarter rather than simply a lead-generation quarter.

The Intelligence team has already demonstrated the ability to find relevant prospects. The next proof point is whether a disciplined multi-party workflow can convert those signals into verified SDK supply, UA demand, and repeatable cross-team execution.

The immediate priority is therefore not adding more rows. It is to create a clean execution queue, assign clear owners, reduce friction for Sales, give GatherOne a validated SDK support system, and report outcomes that leadership can trust.
