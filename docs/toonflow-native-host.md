# LinglongLab native Toonflow Agent host

Branch: `toonflow-native-host`. The previous Pi integration is preserved at
`7498f83`, and remains recoverable in this branch's Git history.

## Runtime and deployment boundary

The existing FastAPI service starts and supervises one private, long-lived Node
host per API worker. Node binds only an ephemeral `127.0.0.1` port, authenticated
with a generated process secret. Its API is not exposed through the public
router. FastAPI retains authentication, project ownership, model configuration,
business tools, durable events and SDK snapshot transactions. This uses the
existing Cloud Run container and service; it requires no additional public API
or IT service registration. FastAPI shutdown disposes its child process.

The active entry is `pi_process.run_process -> native_host.run_native ->
hostServer -> nativeRuntime -> native/upstream/runtime/index.run`. There is no
fallback to either the old Python Agent or the previous custom TypeScript
lifecycle. Type-only protocol imports from the previous runtime do not execute
its lifecycle.

The host vendors Toonflow commit `acdf33ce4ec0c33dac3bccf2d6d7c03f4d2f6807`.
Original run/session/delegation/sub-agent/model/resource/prompt modules and
sub-agent/report/memory tools are retained with explicit module-link rewrites.
The source manifest and upstream license live in
`apps/video-vue/apps/agentRuntime/src/native/`. Scoped adapters replace desktop
filesystem/global credential/resource access. Pi remains version `0.85.1`.
The public workspace interaction protocol remains compatible with the upstream
Vue UI. This reuses the native Agent core, not the entire desktop Express/Bun
server or its unrestricted desktop tools.

## Five concurrent users

The private host admits five active parent attempts. Every attempt owns its
AsyncLocalStorage context, model configuration, callback identifiers, event
stream, cancellation signal and scoped SDK journals. Child delegation is
bounded to four concurrently active children per parent and a shared maximum
of 40 model calls. Python callbacks share thirty workers, with at most six scheduled callbacks
per authenticated account, sixteen waiting per account and a bounded global
queue. Cancelling an attempt does not free a still-running producer slot until
the producer exits. Enterprise model requests have a local default 120-second
HTTP deadline (`VIDEO_AGENT_MODEL_TIMEOUT_SECONDS`, valid 1–900), and
cancellation closes the corresponding client. Model IDs, endpoints, projects
and locations are unchanged.

The sixth parent receives an explicit capacity error; it is
not silently queued or routed to another Agent implementation. Cancellation
aborts the target run and its children, without terminating the shared host.

Cloud Run's current deployment script configures one instance, 2 CPUs, 4 GiB,
request concurrency 20, a 900-second timeout and CPU outside requests. Five
concurrent synthetic-provider sessions verify software isolation and scheduling;
they do not measure actual model quotas, production memory peaks or generation
latency. Increasing instance/worker counts needs a separate routing/admission
capacity review. Active jobs interrupted by a crash are not automatically
replayed; committed SDK snapshots and durable UI events can be restored, and a
new user turn can resume safely.

## Verification contract

The frozen local suite passed 558 API, 51 runtime and 75 frontend tests with
zero failures/errors/skips and 89% active boundary coverage.
See [acceptance evidence and remaining release gates](toonflow-native-host-acceptance.md).

Acceptance requires zero failed, errored or skipped tests; at least 80% active
Agent boundary coverage including `native_host`; runtime/web type checks;
production builds; source provenance verification; real SDK five-account
concurrency, cancellation and context/tool/event isolation; control/question
recovery; child continuation/deletion/report regressions; and isolated browser
interaction checks. Model responses in these tests are synthetic. Real model
quality, paid generation, final exported-media quality and deployed Cloud Run
process-loss behavior remain separate release acceptance steps.

The GitHub preflight workflow runs on pushes to this branch as well as `main`.
It checks the native SDK import inside the unified API image. A failed image
build must be reported, not counted as a deployment-ready result. No production
deployment or production-history reset is part of this migration.
