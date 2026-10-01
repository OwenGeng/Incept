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
  "image-video": {
    products: { image: true, video: true, gaming_playable: false },
  },
};

const releaseIdPattern = /^linglong-image-video-v\d+\.\d+\.\d+(?:-(?:rc\.\d+|hotfix\.\d+))?$/;
const shaPattern = /^[0-9a-f]{40}$/;
const requiredApprovalRoles = ["AI Committee", "Engineering owner", "Product owner"];
const approvalDecisions = new Set(["approved", "rejected", "changes_requested"]);
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
    fail("release_id must look like linglong-image-video-v1.2.3");
  }
  if (!(manifest.release_profile in profiles)) fail("release_profile must be image-video");
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
  if (!Array.isArray(manifest.approvals?.required)) {
    fail("approvals.required must be an array");
  }
  if (
    manifest.approvals.required.length !== requiredApprovalRoles.length
    || requiredApprovalRoles.some((role) => !manifest.approvals.required.includes(role))
  ) {
    fail(`approvals.required must contain exactly: ${requiredApprovalRoles.join(", ")}`);
  }
  if (!Array.isArray(manifest.approvals.records)) fail("approvals.records must be an array");
  for (const record of manifest.approvals.records) {
    if (!record || typeof record !== "object" || Array.isArray(record)) fail("each approval record must be an object");
    if (!requiredApprovalRoles.includes(record.role)) fail(`unknown approval role: ${record.role ?? "missing"}`);
    if (!approvalDecisions.has(record.decision)) fail(`invalid approval decision for ${record.role}`);
    if (typeof record.reviewer !== "string" || !record.reviewer.trim()) fail(`approval reviewer is required for ${record.role}`);
    if (typeof record.evidence !== "string" || !record.evidence.trim()) fail(`approval evidence is required for ${record.role}`);
    if (typeof record.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(record.date)) {
      fail(`approval date must be YYYY-MM-DD for ${record.role}`);
    }
  }
  if (manifest.rollout?.strategy !== "Cloud Run revision") {
    fail("rollout.strategy must be Cloud Run revision");
  }
  if (!releaseIdPattern.test(manifest.rollout?.rollback_release_id ?? "")) {
    fail("rollout.rollback_release_id must be a valid prior release ID");
  }
  if (manifest.rollout.rollback_release_id === manifest.release_id) {
    fail("rollout.rollback_release_id must differ from release_id");
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
  const latestDecisionByRole = new Map();
  for (const record of manifest.approvals.records) latestDecisionByRole.set(record.role, record.decision);
  const missing = manifest.approvals.required.filter((role) => latestDecisionByRole.get(role) !== "approved");
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
    INCEPT_ENABLE_GAMING_PLAYABLE: String(products.gaming_playable),
  };
  process.stdout.write(Object.entries(values).map(([key, value]) => `export ${key}=${shellQuote(value)}`).join("\n") + "\n");
}

function create(profile, releaseId) {
  if (!(profile in profiles)) fail("profile must be image-video");
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
      required: requiredApprovalRoles,
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
