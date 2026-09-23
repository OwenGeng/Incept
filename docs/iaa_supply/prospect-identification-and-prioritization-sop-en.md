# Prospect Identification & Prioritization SOP

> English version

> **Owner:** Owen
> **Applies to:** Moloco IAA SMB Q3 Pilot
>
> This document defines which customers enter the quarterly execution queue and why. Day-to-day customer execution is maintained in the Tracker, not in this SOP.

## 1. Objective and outputs

Each month, convert data candidates into an executable Q3 pipeline. Every Bundle entering the queue must have a clear priority, commercial route, and handoff decision.

There are only four review outcomes:

| Outcome | Meaning | Next step |
|---|---|---|
| Qualified | Worthy of the current-quarter execution queue | Proceed to relationship review and Agency handoff |
| Needs Review | Potential, but a material fact or relationship decision is missing | Assign a verifier and due date |
| Hold | Do not invest execution effort now; retain for observation | Reassess at the next monthly refresh |
| Exclude | Clearly unsuitable or already sufficiently covered | Record the reason; do not re-enter as a duplicate |

## 2. Inputs and refresh cadence

After the monthly Intelligence refresh, Owen begins the review with the following inputs:

- `cold_prospect_app`: Bundle-level market, download, UA, Moloco, and Supply signals;
- `cold_prospect_publisher`: publisher-level view used to understand the product portfolio under the same entity;
- the current-quarter Supply target snapshot: used to identify existing Supply coverage and BD ownership;
- the current-quarter External / Internal Tracker: used to prevent duplicate queue entries and preserve existing customer actions; and
- GatherOne self-sourced submissions: candidate Bundles submitted by the Agency.

Data first enters the internal candidate pool. It is not added directly to the GatherOne execution queue before validation is complete.

## 3. Identification and validation steps

### Step 1: Confirm Bundle and data completeness

- Confirm that the Bundle, App, Publisher, OS, and `data_as_of` date are identifiable.
- Review downloads for the most recent complete month, download month-over-month change, paid-download share, active UA networks, and MAU where available.
- Check whether the Company / Publisher has a known Chinese entity, website, or usable contact path.
- If data is missing or the Bundle cannot be confirmed, use `Needs Review`; do not infer identity from a name alone.

### Step 2: Confirm the commercial opportunity

Review the following questions:

1. Is there an IAA / SDK, UA, or two-sided opportunity?
2. Does the customer already have a Moloco SDK, UA, or historical commercial relationship?
3. Is `IAA-first`, `UA-first`, `Co-win`, or `Observe` the appropriate route?
4. Is there an active Supply BD, Moloco Sales, or GatherOne relationship?
5. Is there an obvious geographic, product, commercial, or ownership conflict?

### Step 3: Determine priority

System priority is the starting point for data ordering; it does not replace commercial judgment.

| System priority | Current signal | Required action |
|---|---|---|
| P1 | IAA / Hybrid App, paid-download share ≥50%, and the top-download market is not China, India, Bangladesh, Iraq, or Pakistan | Prioritize relationship review and the Agency path |
| P2 | Paid-download share ≥20%, and the top-download market is not China, India, Bangladesh, Iraq, or Pakistan; Pure IAP Apps can be no higher than P2 | Enter the normal Q3 review queue |
| P3 | Weaker data signals, missing key fields, or no current fit | Progress only with a strong relationship or clear additional information |

`active_ua_networks` is a supporting signal only; it is no longer a hard P1/P2 threshold. The primary download market is calculated from SensorTower downloads accumulated in the current and previous month. If that market is China, India, Bangladesh, Iraq, or Pakistan, retain the App as P3 for observation rather than adding it to the P1/P2 execution queue.

The review also considers download scale and trend, monetization model, Publisher portfolio, reachability, and current Moloco coverage. A Bundle must not enter the execution queue solely because of high downloads or a high potential incentive amount.

### Step 4: Decide queue entry and commercial route

Record the following minimum decision for every Qualified Bundle:

- `priority` and a one-sentence rationale;
- `route`: `IAA-first / UA-first / Co-win / Observe`;
- whether a Moloco introduction is required, and the recommended relationship owner;
- whether the Bundle can be released to GatherOne; and
- the next responsible owner and completion date.

Only Bundles with all of these fields completed may enter the current-quarter execution queue.

## 4. Monthly queue-entry rules

- Use `quarter + normalized_bundle` as the duplicate-control key.
- Add a new Bundle to the current-quarter queue only after internal validation.
- For an existing Bundle, refresh only Intelligence fact fields and `latest_data_as_of`; do not add a duplicate row.
- A data refresh must not overwrite manual fields: owner, stage, customer feedback, next action, or support.
- Multiple Bundles under the same Chinese entity or Publisher may be reviewed together, but each Bundle is still progressed or held independently.

## 5. GatherOne self-sourced leads

A GatherOne submission must include at least Company, App, Bundle, OS, GatherOne owner, relationship basis, and an explanation of IAA / UA potential.

After Owen validates the submission using Bundle Lookup and internal data:

- If it is already in the queue, mark it as a duplicate and return it to the existing owner.
- If data is available and it meets the standard, process it through the normal `Qualified / Hold / Exclude` path.
- If data is not yet available, mark it `Needs Review` and first complete the Bundle, OS, Publisher, or customer-background facts.

## 6. Exceptions and escalation

| Situation | Handling rule |
|---|---|
| Existing Moloco or Supply owner | Do not send directly to the Agency. Michael or the relevant owner first decides whether to introduce, retain, or release the account. |
| Top-2000 / strategic account | Flag for route selection by Owen with Supply / Sales. Do not automatically exclude it or automatically assign it to the Agency. |
| Conflict between data and customer facts | Use verifiable information and record the reason for follow-up. |
| Multiple Publisher names for the same customer | Use Chinese entity, website, and customer confirmation to support grouping; do not merge automatically based on similar names alone. |
| No defined next action | Do not count the record in the active pipeline; return it to `Needs Review` or `Hold`. |

## 7. Monthly checklist

- [ ] Data has been refreshed and `data_as_of` is clear.
- [ ] New P1/P2 Bundles have completed internal review.
- [ ] Existing Bundles have not been added to the queue again.
- [ ] Every Qualified Bundle has a priority, route, owner recommendation, and next action.
- [ ] GatherOne self-sourced leads have a review outcome.
- [ ] Exceptions, conflicts, and strategic accounts have been recorded in the action register.

> Detailed customer status, customer communication, and support requests are maintained only in the Tracker. This SOP defines the qualification and queue-entry actions owned by Owen.
