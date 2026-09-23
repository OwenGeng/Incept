import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const localesRoot = path.resolve(here, "../components/ai-video/src/locales");

function flatten(value, prefix = "") {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return Object.entries(value).flatMap(([key, child]) =>
      flatten(child, prefix ? `${prefix}.${key}` : key),
    );
  }
  return [[prefix, value]];
}

async function readCatalog(locale) {
  const directory = path.join(localesRoot, locale);
  const names = (await readdir(directory)).filter((name) => name.endsWith(".json")).sort();
  const catalog = new Map();

  for (const name of names) {
    const json = JSON.parse(await readFile(path.join(directory, name), "utf8"));
    for (const [key, value] of flatten(json)) {
      catalog.set(`${name}:${key}`, value);
    }
  }
  return catalog;
}

const [english, chinese] = await Promise.all([readCatalog("en-US"), readCatalog("zh-CN")]);
const problems = [];

for (const [key, value] of english) {
  if (!chinese.has(key)) problems.push(`Missing zh-CN key: ${key}`);
  if (typeof value !== "string" || !value.trim()) problems.push(`Empty en-US copy: ${key}`);
}
for (const key of chinese.keys()) {
  if (!english.has(key)) problems.push(`Missing en-US key: ${key}`);
}

if (problems.length) {
  console.error(`AI Video locale audit failed:\n${problems.join("\n")}`);
  process.exitCode = 1;
} else {
  console.log(`AI Video locale audit passed (${english.size} translated keys in en-US and zh-CN).`);
}
