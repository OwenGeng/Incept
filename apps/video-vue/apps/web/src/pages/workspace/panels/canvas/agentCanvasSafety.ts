type Graph = { nodes: unknown[]; edges: unknown[] };
type Entry = Record<string, unknown>;
const runtimeFields = new Set([
  "selected", "dragging", "resizing", "dimensions", "computedPosition", "positionAbsolute",
  "handleBounds", "events", "initialized", "isParent", "sourceNode", "targetNode",
  "sourceX", "sourceY", "targetX", "targetY",
]);

function isEntry(value: unknown): value is Entry {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function stable(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stable);
  if (isEntry(value)) return Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])]));
  return value;
}

function graphSignature(graph: Graph) {
  const entries = (values: unknown[]) => values.map(value => isEntry(value)
    ? Object.fromEntries(Object.entries(value).filter(([key]) => !runtimeFields.has(key))) : value);
  // Only top-level Vue Flow runtime fields are ignored; identically named customer data remains meaningful.
  return JSON.stringify(stable({ nodes: entries(graph.nodes), edges: entries(graph.edges) }));
}

export function createCanvasRunGuard(id: string, graph: Graph) {
  let baseline = graphSignature(graph);
  let original = JSON.parse(JSON.stringify(graph)) as Graph;
  function assertBinding(currentId: string) {
    if (currentId !== id) throw new Error("画布已切换，本次 Agent 修改未应用，请返回原画布后重新发送");
  }
  return {
    id,
    get original() { return original; },
    assertBinding,
    assertUnchanged(currentId: string, current: Graph) {
      assertBinding(currentId);
      if (graphSignature(current) !== baseline) throw new Error("画布已被修改，本次 Agent 结果未覆盖当前修改，请重新发送");
    },
    refresh(currentId: string, current: Graph) {
      assertBinding(currentId);
      baseline = graphSignature(current);
      original = JSON.parse(JSON.stringify(current)) as Graph;
    },
  };
}

export function validateCanvasReplacement(raw: unknown, allowed: ReadonlySet<string>, original: Graph): { nodes: Entry[]; edges: Entry[] } {
  if (!isEntry(raw) || !Array.isArray(raw.nodes) || !Array.isArray(raw.edges)) throw new Error("画布快照格式无效");
  const originalTypes = new Map(original.nodes.filter(isEntry).map(node => [node.id, node.type]));
  const nodeIds = new Set<string>();
  const nodes = raw.nodes.map(node => {
    if (!isEntry(node) || typeof node.id !== "string" || !node.id || typeof node.type !== "string" || !node.type) throw new Error("画布节点格式无效");
    if (nodeIds.has(node.id)) throw new Error("画布包含重复节点 ID");
    if (!allowed.has(node.type) && originalTypes.get(node.id) !== node.type) throw new Error("节点类型未启用，本次修改未应用");
    nodeIds.add(node.id);
    return { ...node };
  });
  const edgeIds = new Set<string>();
  const edges = raw.edges.map(edge => {
    if (!isEntry(edge) || typeof edge.id !== "string" || !edge.id || typeof edge.source !== "string" || typeof edge.target !== "string"
      || !nodeIds.has(edge.source) || !nodeIds.has(edge.target)) throw new Error("画布连线格式或目标无效");
    if (edgeIds.has(edge.id)) throw new Error("画布包含重复连线 ID");
    edgeIds.add(edge.id);
    return { ...edge };
  });
  return { nodes, edges };
}
