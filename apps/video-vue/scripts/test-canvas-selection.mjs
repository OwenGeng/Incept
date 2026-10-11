import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

// Use the installed compiler; no test dependency or generated file is required.
async function importTypescript(path, removeImports = false) {
  let source = await readFile(new URL(path, import.meta.url), "utf8");
  if (removeImports) source = source.replace(/^import .*;\n/gm, "");
  const ts = await import("../apps/web/node_modules/typescript/lib/typescript.js");
  const compiled = ts.default.transpileModule(source, { compilerOptions: { target: ts.default.ScriptTarget.ES2022, module: ts.default.ModuleKind.ESNext } }).outputText;
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
}
const { arrangeSelection, clampSelectionToolbar } = await importTypescript("../apps/web/src/pages/workspace/panels/canvas/selectionLayout.ts");
const { remapNodeOwnedPaths, getCanvasAssetDirectories, getClipboardNodeOwner } = await importTypescript("../apps/web/src/pages/workspace/canvasFile.ts", true);
const { getSelectionRoots, getSelectionTree } = await importTypescript("../apps/web/src/pages/workspace/panels/canvas/selectionNodes.ts", true);
const make = (id, x, y, width, height) => ({ id, position: { x, y }, dimensions: { width, height } });
const nodes = [make("b", 30, 80, 100, 90), make("a", -10, -20, 200, 50), make("c", 50, 100, 80, 120)];
assert.deepEqual([...arrangeSelection(nodes, "horizontal")], [["a", { x: -10, y: -20 }], ["b", { x: 254, y: -20 }], ["c", { x: 418, y: -20 }]]);
assert.deepEqual([...arrangeSelection(nodes, "vertical")], [["a", { x: -10, y: -20 }], ["b", { x: -10, y: 94 }], ["c", { x: -10, y: 248 }]]);
assert.deepEqual([...arrangeSelection(nodes, "grid")], [["a", { x: -10, y: -20 }], ["b", { x: 254, y: -20 }], ["c", { x: -10, y: 134 }]]);
assert.equal(arrangeSelection([], "grid").size, 0);
assert.equal(nodes[0].position.x, 30, "layout helper must not mutate input");
assert.deepEqual(clampSelectionToolbar(-40, -300, 1000, 600, 320, 38), { left: 8, top: 8 });
assert.deepEqual(clampSelectionToolbar(2000, 2000, 1000, 600, 320, 38), { left: 672, top: 554 });
assert.deepEqual(clampSelectionToolbar(50, 20, 100, 20, 320, 38), { left: 8, top: 8 });
const data = { textPath: "assets/old/content.md", outputs: [{ value: "assets/other/clip.mp4" }], shared: "assets/generated/a.png", external: "https://host/assets/old/a.png", prefix: "assets/oldish/a.png", unsafe: "assets/old/../shared.png" };
const result = remapNodeOwnedPaths(data, new Map([["old", "new"], ["other", "second"]]));
assert.equal(result.textPath, "assets/new/content.md");
assert.equal(result.outputs[0].value, "assets/second/clip.mp4");
assert.equal(remapNodeOwnedPaths("assets\\old\\frame.png", new Map([["old", "new"]])), "assets/new/frame.png");
assert.equal(remapNodeOwnedPaths("assets\\old\\..\\shared.png", new Map([["old", "new"]])), "assets\\old\\..\\shared.png");
for (const key of ["shared", "external", "prefix", "unsafe"]) assert.equal(result[key], data[key]);
assert.equal(data.textPath, "assets/old/content.md", "cloning must not mutate the original");
assert.equal(getClipboardNodeOwner({ id: "source", data: { textPath: "assets/other/content.md" } }), "source");
assert.equal(getClipboardNodeOwner({ type: "remote-textNode", data: { textPath: "assets/old/content.md" } }), "old");
assert.equal(getClipboardNodeOwner({ type: "remote-imageNode", data: { textPath: "assets/generated/content.md" } }), undefined);
assert.equal(getClipboardNodeOwner({ id: "../outside" }), undefined);
assert.equal(getClipboardNodeOwner({ id: "CON" }), undefined);
assert.deepEqual(getCanvasAssetDirectories([{ id: "old" }, { id: "shared-node" }], [{ id: "new", data: { value: "assets/old/image.png" } }]), ["assets/shared-node"]);
const group = make("group", 0, 0, 300, 400);
const child = { ...make("child", 10, 10, 100, 80), parentNode: "group" };
const independent = make("independent", 600, 0, 100, 80);
assert.deepEqual(getSelectionRoots([group, child, independent], [group, child, independent]).map(node => node.id), ["group", "independent"]);
assert.deepEqual(getSelectionTree([group], [group, child, independent]).map(node => node.id), ["group", "child"]);
console.log("Canvas selection layout, clamp, asset isolation, group tree and retention checks passed.");
