const record = (value: unknown): Record<string, unknown> => value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const finite = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value : undefined;
const tokenKeys = ['input', 'output', 'cacheRead', 'cacheWrite', 'total'] as const;
export type TokenUsage = Record<(typeof tokenKeys)[number], number>;
const tokens = (value: unknown): TokenUsage => {
  const source = record(value);
  const result = Object.fromEntries(tokenKeys.map(key => [key, Math.max(0, finite(source[key]) ?? 0)])) as TokenUsage;
  if (finite(source.total) === undefined) result.total = result.input + result.output + result.cacheRead + result.cacheWrite;
  return result;
};
export function usageSummary(value: unknown) {
  const stats = record(value);
  const childSource = Array.isArray(stats.children) ? stats.children : stats.children ? [stats.children] : [];
  const children = childSource.map(value => {
    const child = record(value);
    return { name: typeof child.name === 'string' ? child.name : '', tokens: child.tokens ? tokens(child.tokens) : undefined, cost: finite(child.cost) };
  });
  const childTokens = tokens(undefined);
  for (const child of children) if (child.tokens) for (const key of tokenKeys) childTokens[key] += child.tokens[key];
  // Pi's product tokens already include child usage. Never add children a second time.
  const totalTokens = tokens(record(stats.totals).tokens ?? stats.tokens);
  const ownTokens = Object.fromEntries(tokenKeys.map(key => [key, Math.max(0, totalTokens[key] - childTokens[key])])) as TokenUsage;
  const budget = record(stats.budget);
  return { tokens: totalTokens, ownTokens, childTokens, children,
    cost: finite(stats.cost), elapsedMs: finite(stats.elapsedMs), tokensPerSecond: finite(stats.tokensPerSecond),
    modelBudget: finite(budget.limit) === undefined ? undefined : {
      used: finite(budget.used) ?? 0, limit: finite(budget.limit)!, remaining: finite(budget.remaining),
    } };
}
