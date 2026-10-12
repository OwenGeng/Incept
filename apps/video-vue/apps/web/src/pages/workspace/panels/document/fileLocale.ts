// Display aliases only. Never use these labels for reading, saving or renaming.
export function workspaceFileLabel(name: string, type: string, language: string): string {
  const generated = type === 'canvas' ? /^画布(\d+)\.json$/.exec(name) : null;
  return generated && language.startsWith('en') ? `Canvas${generated[1]}.json` : name;
}
const searchErrors = [
  ['查找内容不能为空', 'Search text is required'],
  ['查找内容需要 1–1000 个字符', 'Search text must contain 1–1,000 characters'],
  ['文件已打开或工作区已切换，停止替换', 'The file is open or the workspace changed; replacement stopped'],
  ['替换结果超过 5 MiB 上限', 'The replacement exceeds the 5 MiB limit'],
  ['保存失败或内容已被修改，已停止。请重新搜索以读取最新版本。', 'Saving failed or the content changed. Replacement stopped; search again for the latest version.'],
  ['无法读取目录', 'Could not read the directory'], ['读取失败', 'Could not read the file'],
] as const;
export function documentSystemText(value: string, language: string): string {
  if (!language.startsWith('en')) return value;
  for (const [zh, en] of searchErrors) {
    if (value === zh) return en;
    if (value.endsWith(`: ${zh}`)) return value.slice(0, -zh.length) + en;
  }
  return value;
}
