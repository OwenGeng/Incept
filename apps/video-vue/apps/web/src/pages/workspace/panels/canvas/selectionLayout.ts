export type Arrangement = "horizontal" | "vertical" | "grid";
type LayoutNode = { id: string; position: { x: number; y: number }; dimensions: { width: number; height: number } };

// Arrange only the roots chosen by the caller: group children retain their local positions.
export function arrangeSelection(nodes: LayoutNode[], mode: Arrangement, gap = 64) {
  const positions = new Map<string, { x: number; y: number }>();
  if (!nodes.length) return positions;
  const ordered = [...nodes].sort((a, b) => mode === "vertical"
    ? a.position.y - b.position.y || a.position.x - b.position.x || a.id.localeCompare(b.id)
    : a.position.x - b.position.x || a.position.y - b.position.y || a.id.localeCompare(b.id));
  const left = Math.min(...nodes.map(node => node.position.x));
  const top = Math.min(...nodes.map(node => node.position.y));
  const columns = mode === "grid" ? Math.ceil(Math.sqrt(nodes.length)) : mode === "horizontal" ? nodes.length : 1;
  const widths = Array.from({ length: columns }, (_, col) => Math.max(...ordered.filter((_, index) => index % columns === col).map(node => Math.max(node.dimensions.width, 1))));
  let y = top;
  for (let row = 0; row < Math.ceil(nodes.length / columns); row++) {
    let x = left;
    let height = 0;
    for (let col = 0; col < columns; col++) {
      const node = ordered[row * columns + col];
      if (!node) break;
      positions.set(node.id, { x, y });
      x += widths[col]! + gap;
      height = Math.max(height, node.dimensions.height, 1);
    }
    y += height + gap;
  }
  return positions;
}

export function clampSelectionToolbar(center: number, bottom: number, viewportWidth: number, viewportHeight: number, width: number, height: number) {
  const margin = 8;
  const maxLeft = Math.max(margin, viewportWidth - width - margin);
  const maxTop = Math.max(margin, viewportHeight - height - margin);
  return { left: Math.min(maxLeft, Math.max(margin, center - width / 2)), top: Math.min(maxTop, Math.max(margin, bottom - height)) };
}
