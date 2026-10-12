# Native host acceptance record

Branch `toonflow-native-host`; upstream source pin
`acdf33ce4ec0c33dac3bccf2d6d7c03f4d2f6807`. This is a code and local acceptance
record, not a production deployment or five-human-user trial.

## Verified boundaries

- Five distinct test accounts execute real native/Pi sessions concurrently in
  one host PID/generation. Identical tool-call IDs still produce only each
  account's authorized workspace receipt, context and event stream.
- Cancelling one account preserves the other four and the shared process.
  A sixth active parent is refused explicitly; callback IDs cannot cross runs,
  be replayed, or deliver late results after termination.
- The actual SDK resumes after host exit and local journal/cache removal using
  durable snapshots, preserving prior SDK entry IDs. Crash recovery does not
  automatically replay model calls or uncertain paid operations.
- Native child work retains its SDK journal across parent continuation and
  independent user turns; busy children reject competing parent continuation.
  Deleted user turns, receipts, compactions and original child task metadata
  remain deleted. Late cancelled results cannot become successful reports.
- Explicit native reports persist and refresh without changing the parent's
  committed SDK source. A later parent fork imports each report once through
  Pi's native custom-message API. Reports cannot change ownership or content
  under an existing report ID.
- Vendored source hashes, retained original source bytes and import/re-export
  transformations are verified automatically. Lifecycle bodies remain pinned
  upstream code; scoped adapters replace desktop authority.

## Validation evidence

Final frozen-source results: **558 API tests, 51 runtime tests and 75 frontend
tests passed**, with zero failures, errors or skips. Active hosted Agent and
workspace-lock line coverage is **89%** (new native host: 87%, enterprise
transport: 96%, document locks: 93%). The independent overall coverage gate
also passed at 89%. Browser checks passed
question refresh/answer, child stop/continuation, report exact-once reload,
steering, normal follow-up completion, interrupted follow-up preservation and
resend, memory/skill save and reload, thinking selection, five-identity project
isolation and canonical conversation deletion.
[Detailed browser record](native-toonflow-frontend-acceptance.md),
[completed native report](acceptance/toonflow-native-host/native-report-completed.jpg),
[retained interrupted instruction](acceptance/toonflow-native-host/queued-stop-retained-labelled.jpg). The required gates reject failed, errored or skipped cases. Active
coverage includes the new native host rather than excluding its branches.
All 25 Vue workspace/runtime type checks, Next.js types and lint, translation
checks, frozen-lockfile installation, Vue build/static sync, Next.js production
build, preflight and release-fixture validation passed. Test reports were
validated with the repository checker rather than relying only on exit codes.

A clean temporary production-only dependency deployment also imported the
native SDK and host successfully, without relying on development packages.
This is a host-platform dependency check, not a Linux container build.

Production dependency audits passed their configured high/critical threshold.
The root JavaScript audit reported two moderate advisories, the Vue workspace
one low advisory, and the Python audit no known advisories. These summaries do
not claim zero dependency risk.

## Cross-review fixes

Fresh cross-review closed credential redaction at terminal/checkpoint/child/report
boundaries; disabled memory and native revision/CAS compatibility; bounded fair
callback production and cancellation-driven enterprise client closure; report
mutation/cancellation races; and PostgreSQL exact-path nested advisory-lock
reentry. Meaningful regressions include a real four-child model barrier, twenty
repeated cancellations while another owner still progresses, queue-stop-refresh
receipts, report idempotency, and PostgreSQL connection/transaction isolation.
PostgreSQL lock tests use a simulated pool; deployed PostgreSQL acceptance is
not claimed.

## Unfinished release gates

The unified image build could not pass locally: Docker Hub's configured Python
base-image fetch timed out during TLS negotiation; a separate native Node stage
also could not download pnpm from the configured npm registry inside Docker.
A repeated base-image pull made no progress and was stopped. No dependency,
model, region, API endpoint or global network setting was changed to hide this.
The branch's GitHub workflow includes both frozen builds and the unified image
build; its actual result must be checked independently of local test results.

Real-provider quality, actual paid generation, final exported-media quality and
deployed Cloud Run restart/resource/quota behavior have not been exercised.
Those require authorized release acceptance. No production service or history
was changed and no deployment was performed.

## Bilingual follow-up (2026-10-12)

Interface-owned native status, report receipts, stream failures and pinned
upstream static errors have an English/Chinese catalogue. Each native run
receives its authenticated account language. The model policy explicitly applies
to questions, options, task names and visible progress as well as answers.
User text, filenames, task names supplied by users and completed creative work
are preserved, rather than translated by the UI. Existing historical model
content remains in its original language; real-provider language compliance
still requires model acceptance.

Concurrent real SDK child/report sessions verify independent Chinese/English
receipts without changing report content. A browser round trip from Chinese to
English and back verified memory controls, reasoning labels, navigation and
ARIA labels. The legacy DOM locale bridge now restores only text it translated,
so it cannot overwrite a newly rendered reactive label with the previous
language. The Chinese language option itself displays `Chinese` in English.
[English Agent settings evidence](acceptance/toonflow-native-host/english-agent-settings.png).

The updated suite passed 558 API, 53 runtime and 81 frontend tests, without
failures or skips, plus workspace types, translation audit and production Vue
build/static sync. Linux image build and lifecycle CI for the preceding host
commit passed at https://github.com/OwenGeng/Incept/actions/runs/38162782495;
the bilingual commit has its own CI run.

The shared locale catalogue is an explicit production dependency shipped as
JavaScript with TypeScript declarations. A clean production-only deployment
successfully imported the native runtime, private host and locale package;
no development TypeScript loader is needed for dependency files.

Question cards receive interface language explicitly, including fallback titles,
invalid-form hints, validation, submission and skip receipts. Failed askUser
forms use the same inline card and do not depend on a separate renderer build.

## Business approval locale closure (2026-10-12)

Media submission, external-agent transmission and remote cancellation approval
cards now use each authenticated account's Chinese/English setting for titles,
explanations and both choices. Approval parsing requires the exact label issued
with that card; it does not silently default to Chinese after an English choice.
A language change while the card is pending cannot change its approval meaning.
The exact request, original customer content and idempotency binding are retained.

Twenty-one additional regressions cover both locales, approval, cancellation,
skip, ambiguous answers, wrong-action/wrong-language choices and account
isolation. Full API acceptance passed **579 tests**, zero failures/errors/skips.
No paid generation or real external-agent transmission was performed by these
mock-boundary tests. Runtime/frontend source is unchanged from its prior 53/81
passing suites.

Linux CI also exposed an initialization-dependent report-cancellation test
barrier. Injecting a six-second initialization delay reproduced both old test
failures; the corrected test passes both cases under that same delay. It now
waits for runtime readiness before holding the metadata lock and observes the
callback's actual lock attempt before cancellation/replacement. The critical
callback deadline remains five seconds, and the test still requires
AgentCancelled and no persisted reports; no runtime cancellation check was
relaxed or skipped.
