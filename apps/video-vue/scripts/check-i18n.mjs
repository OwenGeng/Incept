import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const sourceRoots = [join(root, "apps/web/src"), join(root, "packages")];
const catalogue = ["apps/web/src/i18n.ts", "apps/web/src/i18nCatalog.ts"]
  .map(file => readFileSync(join(root, file), "utf8"))
  .join("\n");
const translatedPhrases = [...catalogue.matchAll(/\[\s*["'`]([^"'`]*[\u3400-\u9fff][^"'`]*)["'`]\s*,/gu)]
  .map(match => match[1]);
const dynamicPatterns = [
  /确定删除[“”]/u,
  /确定永久删除云端项目/u,
  /\$\{/u,
];

function vueFiles(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => {
    const path = join(directory, entry.name);
    return entry.isDirectory() ? vueFiles(path) : entry.name.endsWith(".vue") ? [path] : [];
  });
}

const unresolved = [];
for (const file of sourceRoots.flatMap(vueFiles)) {
  const source = readFileSync(file, "utf8");
  const template = source.match(/<template(?:\s[^>]*)?>([\s\S]*?)<\/template>/u)?.[1] ?? "";
  let inComment = false;
  template.split("\n").forEach((rawLine, index) => {
    let line = rawLine;
    if (line.includes("<!--")) inComment = true;
    if (inComment) {
      if (line.includes("-->")) inComment = false;
      return;
    }
    if (!/[\u3400-\u9fff]/u.test(line)) return;
    if (translatedPhrases.some(phrase => line.includes(phrase.trim()))) return;
    if (dynamicPatterns.some(pattern => pattern.test(line))) return;
    unresolved.push(`${relative(root, file)}:${index + 2}: ${line.trim()}`);
  });
}

if (unresolved.length) {
  console.error("Untranslated Chinese UI found in Vue templates:\n" + unresolved.join("\n"));
  process.exitCode = 1;
} else {
  console.log("Vue UI translation audit passed.");
}
