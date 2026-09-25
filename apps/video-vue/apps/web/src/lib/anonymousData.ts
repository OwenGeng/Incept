type UsageEvent = "onboarding.complete" | "onboarding.skip" | "workspace.canvas" | "workspace.document";
type AgentOutcome = "success" | "failed" | "cancelled";
type CanvasSnapshot = { nodes: readonly { type?: string }[]; edgeCount: number };

// LinglongLab intentionally keeps the original UI instrumentation hooks as
// local no-ops. No usage data leaves the browser.
const anonymousData = {
  track(_event: UsageEvent) {},
  startAgent() {
    return (_outcome: AgentOutcome) => {};
  },
  observeCanvas(_read: () => CanvasSnapshot | undefined) {
    return () => {};
  },
};

export default anonymousData;
