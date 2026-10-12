import assert from "node:assert/strict";
import test from "node:test";
import { isResearchIncomplete } from "./toolOutcome.ts";

test("research limitation survives live results and journal reload without mislabeling other tools", () => {
  const receipt = { status: "research_incomplete", sources: [] };
  for (const result of [receipt, JSON.stringify(receipt)]) {
    assert.equal(isResearchIncomplete("web_search", result), true);
    assert.equal(isResearchIncomplete("mediaJobs", result), false);
  }
  for (const result of [undefined, null, "broken JSON", { sources: [{ url: "https://example.com" }] }]) {
    assert.equal(isResearchIncomplete("web_search", result), false);
  }
});

// Changing the UI language also localizes receipts loaded from old journals.
import { nativeToolResult } from "../../../../../packages/agentLocale/index.js";
test("stored incomplete research receipts follow the current interface language", () => {
  const original = { status: "research_incomplete", sources: [], message: "调研未完成", attempts: [{ error_code: "empty_results" }] };
  const english = JSON.parse(nativeToolResult(JSON.stringify(original), "web_search", "en-US") as string);
  assert.match(english.message, /^Research incomplete/);
  assert.doesNotMatch(english.message, /[\u3400-\u9fff]/);
  assert.deepEqual(english.attempts, original.attempts);
  const chinese = nativeToolResult(english, "web_search", "zh-CN") as typeof original;
  assert.match(chinese.message, /^调研未完成/);
  assert.deepEqual(chinese.sources, []);
});
