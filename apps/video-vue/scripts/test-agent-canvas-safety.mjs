import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../apps/web/src/pages/workspace/panels/canvas/agentCanvasSafety.ts", import.meta.url), "utf8");
const ts = await import("../apps/web/node_modules/typescript/lib/typescript.js");
const compiled = ts.default.transpileModule(source, { compilerOptions: { target: ts.default.ScriptTarget.ES2022, module: ts.default.ModuleKind.ESNext } }).outputText;
const { createCanvasRunGuard, validateCanvasReplacement } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const initial = { nodes: [
  { id: "group", type: "canvasGroup", position: { x: 0, y: 0 }, data: {}, style: { width: "600px" } },
  { id: "custom", type: "future-node", position: { x: 20, y: 30 }, parentNode: "group", data: { selected: "keep data fields" } },
  { id: "text", type: "remote-textNode", position: { x: 10, y: 20 }, data: { text: "old" } },
], edges: [{ id: "link", source: "custom", target: "text", label: "Original" }], viewport: { x: 0, y: 0, zoom: 1 } };
const guard = createCanvasRunGuard("original.json", initial);
const noise = structuredClone(initial);
noise.nodes[1].selected = true;
noise.nodes[1].dimensions = { width: 999, height: 999 };
noise.nodes[1].computedPosition = { x: 999, y: 999 };
noise.viewport.zoom = 2;
guard.assertUnchanged("original.json", noise);
assert.equal(guard.id, "original.json");
assert.throws(() => guard.assertBinding("switched.json"), /画布已切换/);
assert.throws(() => guard.refresh("switched.json", noise), /画布已切换/);
for (const mutate of [
  graph => { graph.nodes[1].data.selected = "changed"; },
  graph => { graph.nodes[1].position.x += 1; },
  graph => { graph.nodes[1].parentNode = "other"; },
  graph => { graph.nodes[0].style.width = "700px"; },
  graph => { graph.edges[0].label = "Changed"; },
]) {
  const changed = structuredClone(initial);
  mutate(changed);
  assert.throws(() => guard.assertUnchanged("original.json", changed), /画布已被修改/);
}
const replacement = validateCanvasReplacement(initial, new Set(["remote-textNode"]), initial);
assert.deepEqual(replacement.nodes, initial.nodes);
assert.deepEqual(replacement.edges, initial.edges);
const newUnknown = structuredClone(initial);
newUnknown.nodes.push({ id: "unknown-new", type: "future-node", data: {}, position: { x: 0, y: 0 } });
assert.throws(() => validateCanvasReplacement(newUnknown, new Set(["remote-textNode"]), initial), /节点类型/);
const duplicate = structuredClone(initial);
duplicate.nodes.push(structuredClone(initial.nodes[0]));
assert.throws(() => validateCanvasReplacement(duplicate, new Set(["remote-textNode"]), initial), /重复/);
const badEdge = structuredClone(initial);
badEdge.edges[0].target = "missing";
assert.throws(() => validateCanvasReplacement(badEdge, new Set(["remote-textNode"]), initial), /连线/);
guard.refresh("original.json", noise);
guard.assertUnchanged("original.json", initial);

// Exercise the actual context wiring with a local flow fake; no browser or production data is touched.
let graph = structuredClone(initial);
let currentId = "original.json";
let flushes = 0;
let mutateDuringFlush = false;
const flow = {
  toObject: () => structuredClone(graph),
  setNodes: nodes => { graph.nodes = nodes; },
  setEdges: edges => { graph.edges = edges; },
  setViewport: async viewport => { graph.viewport = viewport; },
};
globalThis.canvasSafetyFixture = { flow, createCanvasRunGuard, validateCanvasReplacement };
const toolsSource = (await readFile(new URL("../apps/web/src/pages/workspace/panels/canvas/useCanvasTools.ts", import.meta.url), "utf8")).replace(/^import .*;\n/gm, "");
const toolsCompiled = ts.default.transpileModule(toolsSource, { compilerOptions: { target: ts.default.ScriptTarget.ES2022, module: ts.default.ModuleKind.ESNext } }).outputText;
const prefix = `const nextTick = async () => {}; const useVueFlow = () => globalThis.canvasSafetyFixture.flow;
const useNodeToolsContext = () => () => ({ tools: [] });
const { createCanvasRunGuard, validateCanvasReplacement } = globalThis.canvasSafetyFixture;\n`;
const { useCanvasTools } = await import(`data:text/javascript;base64,${Buffer.from(prefix + toolsCompiled).toString("base64")}`);
const makeContext = useCanvasTools({
  availableNodes: { value: [{ type: "remote-textNode", label: "Text" }] },
  flushSave: async () => {
    flushes++;
    await Promise.resolve();
    if (mutateDuringFlush) graph.nodes[2].data.text = "New unsaved edit during flush";
  },
  getCanvasBinding: () => ({ id: currentId, signal: new AbortController().signal }),
  menu: () => ({}),
});
const context = makeContext("original.json", new AbortController().signal, new AbortController().signal);
await context.prepare();
assert.equal(flushes, 1);
currentId = "switched.json";
assert.equal(context.id, "original.json", "context target must not follow the active canvas");
await assert.rejects(context.call({ name: "replaceCanvas", args: initial }), /画布已切换/);
currentId = "original.json";
graph.nodes[2].data.text = "User edit while model was running";
await assert.rejects(context.call({ name: "replaceCanvas", args: initial }), /画布已被修改/);
assert.equal(graph.nodes[2].data.text, "User edit while model was running");
await context.prepare();
await context.call({ name: "replaceCanvas", args: initial });
assert.deepEqual(graph.nodes, initial.nodes, "actual replacement must retain group and unknown node");
mutateDuringFlush = true;
await assert.rejects(context.prepare(), /画布已被修改/);
assert.equal(graph.nodes[2].data.text, "New unsaved edit during flush");
delete globalThis.canvasSafetyFixture;
console.log("Agent canvas target, concurrent edit guard, noise tolerance and group retention checks passed.");
