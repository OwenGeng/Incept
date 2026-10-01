#!/usr/bin/env node
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const read = (path) => readFileSync(resolve(root, path), "utf8");
const failures = [];

function requireText(path, text) {
  const contents = read(path);
  if (!contents.includes(text)) failures.push(`${path} is missing: ${text}`);
}

requireText("Dockerfile.web", "COPY apps/video-vue/tsconfig.base.json ./tsconfig.base.json");
requireText("Dockerfile.web", "COPY packages/linglonglab-shared ./packages/linglonglab-shared");
requireText("Dockerfile.nbs-api", "COPY apps/web/public/Pretendard/ ./fonts/kakao/");
requireText("Dockerfile.nbs-api", "ENV KAKAO_FONT_DIR=/app/fonts/kakao");
requireText("cloudbuild.api.yaml", "Dockerfile.nbs-api");
requireText("cloudbuild.web.yaml", "INCEPT_ENABLE_GAMING_PLAYABLE=$_INCEPT_ENABLE_GAMING_PLAYABLE");
requireText("deploy.sh", "--no-allow-unauthenticated");
requireText("deploy.sh", "remove-iam-policy-binding");
requireText("deploy.sh", "roles/cloudsql.client");
requireText("deploy.sh", "validate_cloud_resources");
requireText("deploy.sh", "VERTEX_GEMINI_MODEL=gemini-3.8-flash");
requireText("deploy.sh", '--update-env-vars="^|^');
requireText("apps/api/app/incept/config.py", 'vertex_gemini_model: str = Field(default="gemini-3.8-flash")');
if (process.argv.includes("--deploy")) {
  const envPath = resolve(root, ".env.deploy");
  if (!existsSync(envPath)) {
    failures.push(".env.deploy does not exist");
  } else {
    const values = Object.fromEntries(
      readFileSync(envPath, "utf8")
        .split(/\r?\n/)
        .filter((line) => /^[A-Za-z_][A-Za-z0-9_]*=/.test(line))
        .map((line) => {
          const separator = line.indexOf("=");
          return [line.slice(0, separator), line.slice(separator + 1).trim()];
        }),
    );
    for (const key of [
      "DEPLOY_SA_EMAIL",
      "GCP_PROJECT_DEPLOY",
      "CLOUD_SQL_INSTANCE_CONNECTION_NAME",
      "DATABASE_CONFIG_SECRET",
      "DATABASE_CONFIG_SECRET_VERSION",
      "INCEPT_ASSET_BUCKET",
      "INCEPT_INTERNAL_API_KEY_SECRET",
      "INCEPT_INTERNAL_API_KEY_SECRET_VERSION",
      "GOOGLE_CLIENT_ID",
      "GOOGLE_CLIENT_SECRET_SECRET",
      "GOOGLE_CLIENT_SECRET_SECRET_VERSION",
      "AUTH_SECRET_SECRET",
      "AUTH_SECRET_SECRET_VERSION",
      "BQ_WRITE_PROJECT",
      "BQ_READ_PROJECT",
      "BQ_DATASET_CONFIG",
      "BIGQUERY_DATASET",
      "GCP_PROJECT_DATA",
      "INCEPT_ADMIN_EMAILS",
    ]) {
      if (!values[key]) {
        failures.push(`.env.deploy is missing ${key}`);
      } else if (/^(?:your-|replace|changeme|<)/i.test(values[key])) {
        failures.push(`.env.deploy still has a placeholder for ${key}`);
      }
    }
    for (const [nameKey, versionKey] of [
      ["OPENAI_API_KEY_SECRET", "OPENAI_API_KEY_SECRET_VERSION"],
      ["ANTHROPIC_API_KEY_SECRET", "ANTHROPIC_API_KEY_SECRET_VERSION"],
    ]) {
      if (Boolean(values[nameKey]) !== Boolean(values[versionKey])) {
        failures.push(`.env.deploy must set both ${nameKey} and ${versionKey}, or neither`);
      }
    }
  }
}

if (failures.length) {
  process.stderr.write(`preflight failed:\n- ${failures.join("\n- ")}\n`);
  process.exit(1);
}
process.stdout.write("preflight passed\n");
