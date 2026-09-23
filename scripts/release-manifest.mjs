#!/usr/bin/env node
/**
 * The release module is the single seam between an auditable release record
 * and deployment configuration. It intentionally has no cloud credentials.
 */
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const profiles = {
  "image-ai-video": {
    products: { image: true, ai_video: true, video_production: false, gaming_playable: false },
  },
  full: {
    products: { image: true, ai_video: true, video_production: true, gaming_playable: true },
  },
};

const releaseIdPattern = /^linglong-(?:ai-video|full-studio)-v\d+\.\d+\.\d+(?:-(?:rc\.\d+|hotfix\.\d+))?$/;
const shaPattern = /^[0-9a-f]{40}$/;
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

function fail(message) {
  process.stderr.write(`release manifest error: ${message}\n`);
  process.exit(1);
}

function git(...args) {
  return execFileSync("git", args, { cwd: root, encoding: "utf8" }).trim();
}

function readManifest(path) {
  const absolutePath = resolve(root, path);
  if (!existsSync(absolutePath)) fail(`manifest does not exist: ${path}`);
  try {
    return { absolutePath, manifest: JSON.parse(readFileSync(absolutePath, "utf8")) };
  } catch (error) {
    fail(`invalid JSON in ${path}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function validate(manifest) {
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) fail("manifest must be a JSON object");
  if (manifest.schema_version !== 1) fail("schema_version must be 1");
  if (typeof manifest.release_id !== "string" || !releaseIdPattern.test(manifest.release_id)) {
    fail("release_id must look like linglong-ai-video-v1.2.3 or linglong-full-studio-v1.2.3");
  }
  if (!(manifest.release_profile in profiles)) fail("release_profile must be image-ai-video or full");
  if (typeof manifest.source_commit !== "string" || !shaPattern.test(manifest.source_commit)) {
    fail("source_commit must be a full 40-character Git SHA");
  }

  const expectedProducts = profiles[manifest.release_profile].products;
  for (const [name, expected] of Object.entries(expectedProducts)) {
    if (manifest.products?.[name] !== expected) {
      fail(`products.${name} must be ${expected} for ${manifest.release_profile}`);
    }
  }
  for (const artifact of ["api", "web"]) {
    const tag = manifest.images?.[artifact]?.tag;
    if (tag !== manifest.release_id) fail(`images.${artifact}.tag must exactly equal release_id`);
  }
  if (!Array.isArray(manifest.approvals?.required) || manifest.approvals.required.length === 0) {
    fail("approvals.required must name the required reviewers");
  }
  return manifest;
}

function assertCheckout(manifest, manifestPath) {
  const currentCommit = git("rev-parse", "HEAD");
  if (currentCommit === manifest.source_commit) {
    fail("manifest must be committed as the release-record commit before deploying");
  }
  const changedPaths = git("diff", "--name-only", `${manifest.source_commit}..${currentCommit}`)
    .split("\n")
    .filter(Boolean);
  const relativeManifestPath = manifestPath.replace(`${root}/`, "");
  if (changedPaths.length !== 1 || changedPaths[0] !== relativeManifestPath) {
    fail(`only ${relativeManifestPath} may change after source_commit; found: ${changedPaths.join(", ") || "none"}`);
  }
  if (git("status", "--porcelain")) fail("checkout is dirty; commit or stash changes before deploying a reviewed release");
}

function assertApproved(manifest) {
  const approvedRoles = new Set(
    (manifest.approvals.records ?? [])
      .filter((record) => record && record.decision === "approved" && typeof record.role === "string")
      .map((record) => record.role),
  );
  const missing = manifest.approvals.required.filter((role) => !approvedRoles.has(role));
  if (missing.length) fail(`missing approved review records for: ${missing.join(", ")}`);
}

function shellQuote(value) {
  return `'${String(value).replaceAll("'", "'\\''")}'`;
}

function printEnvironment(manifest) {
  const products = manifest.products;
  const values = {
    RELEASE_ID: manifest.release_id,
    PRODUCT_RELEASE_PROFILE: manifest.release_profile,
    INCEPT_ENABLE_VIDEO_PRODUCTION: String(products.video_production),
    INCEPT_ENABLE_GAMING_PLAYABLE: String(products.gaming_playable),
  };
  process.stdout.write(Object.entries(values).map(([key, value]) => `export ${key}=${shellQuote(value)}`).join("\n") + "\n");
}

function create(profile, releaseId) {
  if (!(profile in profiles)) fail("profile must be image-ai-video or full");
  if (!releaseIdPattern.test(releaseId)) fail("invalid release ID");
  if (git("status", "--porcelain")) fail("checkout is dirty; create the manifest from the release commit");

  const output = join(root, "releases", `${releaseId}.json`);
  if (existsSync(output)) fail(`manifest already exists: releases/${basename(output)}`);
  const manifest = {
    schema_version: 1,
    release_id: releaseId,
    release_profile: profile,
    source_commit: git("rev-parse", "HEAD"),
    products: profiles[profile].products,
    images: { api: { tag: releaseId }, web: { tag: releaseId } },
    approvals: {
      required: ["AI Committee", "Engineering owner", "Product owner"],
      records: [],
    },
    rollout: { strategy: "Cloud Run revision", rollback_release_id: "REPLACE_BEFORE_DEPLOY" },
  };
  mkdirSync(dirname(output), { recursive: true });
  writeFileSync(output, `${JSON.stringify(manifest, null, 2)}\n`, { encoding: "utf8", flag: "wx" });
  process.stdout.write(`created releases/${basename(output)}\n`);
}

const [command, ...rawArgs] = process.argv.slice(2);
const args = rawArgs[0] === "--" ? rawArgs.slice(1) : rawArgs;
if (command === "validate" && args.length === 1) {
  const { manifest } = readManifest(args[0]);
  validate(manifest);
  process.stdout.write(`valid: ${manifest.release_id}\n`);
} else if (command === "env" && args.length === 1) {
  const { absolutePath, manifest } = readManifest(args[0]);
  validate(manifest);
  assertApproved(manifest);
  assertCheckout(manifest, absolutePath);
  printEnvironment(manifest);
} else if (command === "create" && args.length === 2) {
  create(args[0], args[1]);
} else {
  fail("usage: release-manifest.mjs validate <manifest> | env <manifest> | create <profile> <release-id>");
}
