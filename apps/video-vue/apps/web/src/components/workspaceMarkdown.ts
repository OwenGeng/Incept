import type { SyntaxTree } from '@markmend/ast';

export function workspaceReferenceUrl(value: string, directory: string, origin: string): string {
  if (!directory || !origin || /^[a-z][a-z\d+.-]*:|^\/\/|^#|^\//iu.test(value)) return value;
  const path = value.replace(/^\.\//u, '').split('#')[0]!;
  if (!path || path.includes('\\') || path.includes('?') || /%(?:2e|2f|5c)/iu.test(path)
    || path.split('/').some(part => !part || part === '..' || part === '.' || part === '.agent')) return value;
  const target = new URL('/api/workspaces/files/read', origin);
  target.search = new URLSearchParams({ directory, path }).toString();
  return target.href;
}

export function resolveWorkspaceMarkdown(tree: SyntaxTree, directory: string, origin: string): SyntaxTree {
  const walk = (node: { type: string; url?: string; children?: unknown[] }) => {
    if (['link', 'image', 'definition'].includes(node.type) && node.url)
      node.url = workspaceReferenceUrl(node.url, directory, origin);
    for (const child of node.children ?? []) walk(child as Parameters<typeof walk>[0]);
  };
  walk(tree);
  return tree;
}
