/** A save acknowledgement does not include edits entered while it was in flight. */
export async function flushUntilStable(save: () => Promise<void>, hasPendingDraft: () => boolean) {
  do { await save(); } while (hasPendingDraft());
}
