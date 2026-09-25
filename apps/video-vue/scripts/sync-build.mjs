import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(packageRoot, "../..");
const sourceRoot = resolve(packageRoot, "build");
const targetRoot = resolve(repositoryRoot, "apps/web/public/video-app");

await rm(targetRoot, { recursive: true, force: true });
await mkdir(targetRoot, { recursive: true });
await cp(resolve(sourceRoot, "web"), targetRoot, { recursive: true });
await cp(resolve(sourceRoot, "nodes"), resolve(targetRoot, "nodes"), { recursive: true });

console.log(`Synced Vue video workspace to ${targetRoot}`);
