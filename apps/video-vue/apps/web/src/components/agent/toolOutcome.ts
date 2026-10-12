/** Works for live tool details and restored Pi journal JSON. */
export function isResearchIncomplete(name: string, result: unknown): boolean {
  if (name !== "web_search") return false;
  try {
    const receipt = typeof result === "string" ? JSON.parse(result) : result;
    return receipt !== null && typeof receipt === "object" && receipt.status === "research_incomplete";
  } catch { return false; }
}
