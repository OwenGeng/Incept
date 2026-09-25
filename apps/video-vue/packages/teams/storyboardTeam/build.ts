import { createTeamConfig } from "@linglonglab/video-teams-scaffold";

await createTeamConfig(import.meta.url, { sync: process.argv.includes("--sync") ? "replace" : "missing" });
