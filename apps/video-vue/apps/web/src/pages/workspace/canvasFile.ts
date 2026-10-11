import axios from "axios";
import type useWorkspaceFiles from "@/lib/workspaceFiles";

type CanvasAssetNode = { id: string; data?: unknown };

export function getClipboardNodeOwner(node: { id?: string; type?: string; data?: { textPath?: unknown } }) {
  // New snapshots identify the owning node explicitly. Old text snapshots have a
  // canonical content path; arbitrary media references do not prove ownership.
  const legacy = /^(?:remote-)?textNode$/.test(node.type ?? "") && typeof node.data?.textPath === "string"
    ? /^assets\/([^/]+)\/content\.md$/.exec(node.data.textPath.replaceAll("\\", "/"))?.[1] : undefined;
  const id = node.id ?? legacy;
  return id && !/[<>:"/\\|?*\x00-\x1f]/.test(id) && !/[. ]$/.test(id)
    && !/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(id) ? id : undefined;
}

export function remapNodeOwnedPaths<T>(data: T, ids: ReadonlyMap<string, string>): T {
  function rewrite(value: unknown): unknown {
    if (typeof value === "string") {
      // Only exact workspace-relative node-owned paths; never rewrite URLs or shared generated assets.
      const path = value.replaceAll("\\", "/");
      const match = /^assets\/([^/]+)\/(.+)$/.exec(path);
      if (match && !match[2]!.split("/").includes("..") && ids.has(match[1]!)) return `assets/${ids.get(match[1]!)}${path.slice(7 + match[1]!.length)}`;
      return value;
    }
    if (Array.isArray(value)) return value.map(rewrite);
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, rewrite(item)]));
    return value;
  }
  return rewrite(data) as T;
}

export function getCanvasAssetDirectories(nodes: CanvasAssetNode[], retainedNodes: CanvasAssetNode[]) {
  const retained = new Set(retainedNodes.map(node => node.id.toLowerCase()));
  const pending = retainedNodes.map(node => node.data);
  const visited = new WeakSet<object>();
  while (pending.length) {
    const value = pending.pop();
    if (typeof value === "string") {
      const parts = value.replaceAll("\\", "/").split("/").filter(part => part && part !== ".");
      if (parts[0]?.toLowerCase() === "assets" && parts[1] && !parts.includes("..")) retained.add(parts[1].toLowerCase());
    } else if (value && typeof value === "object" && !visited.has(value)) {
      visited.add(value);
      for (const item of Object.values(value)) pending.push(item);
    }
  }
  // ACT: 仅清理节点所属目录，不把引用路径当作目录归属，避免误删 assets/generated 等共享目录。
  return [...new Set(nodes.map(node => node.id))]
    .filter(id => id && !/[<>:"/\\|?*\x00-\x1f]/.test(id) && !/[. ]$/.test(id)
      && !/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(id) && !retained.has(id.toLowerCase()))
    .map(id => `assets/${id}`);
}

export async function isCanvasFile(files: Pick<ReturnType<typeof useWorkspaceFiles>, "readText">, path: string) {
  try {
    const header = await files.readText(path, 4096);
    return /^\s*\{/.test(header) && /"linglonglabVideoCanvas"\s*:\s*true\s*[,}]/.test(header);
  } catch (error) {
    // ACT: 扫描期间已消失或不可作为文件读取的条目跳过，权限及其他 IO 错误继续抛出。
    if (axios.isAxiosError(error) && [400, 404].includes(error.response?.status ?? 0)) return;
    throw error;
  }
}
