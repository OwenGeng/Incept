const terminalStatuses = new Set(['completed', 'error', 'limited', 'cancelled']);
export function isDelegationTerminal(status: string) { return terminalStatuses.has(status); }
export function canApplyDelegatedSnapshot(parentObserved: boolean, busy: boolean, hasController: boolean) {
  return parentObserved && !busy && !hasController;
}
