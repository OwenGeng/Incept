# Incept — Codex Guidelines

## External API / Cloud Service Config

**NEVER** change model names, API endpoints, or cloud locations by guessing.

When an external API returns 4xx errors (404, 400, 403):
- STOP before modifying model IDs, location strings, or endpoint URLs
- Ask the user to provide the official documentation or confirm the correct value
- Treat all Vertex AI / GCP config (`GCP_LOCATION`, model IDs, project IDs) as user-owned ground truth

**Why:** Model names and locations for Google Vertex AI / Gemini are not reliably in training data, especially post-cutoff models. Wrong guesses cause cascading changes that are hard to revert.

## Tech Stack

- **API:** FastAPI (Python), runs at `localhost:8000`
- **Web:** Next.js (TypeScript), runs at `localhost:3000`
- **Image generation:** `gemini-3.1-flash-image` via Vertex AI, `location=global` (NOT `us-central1`)
- **Text/analytics Gemini:** `gemini-3.6-flash` via Enterprise Agent Platform, `location=global`
- **Config files:** `apps/api/app/incept/config.py` (Studio/image), `apps/api/app/core/config.py` (analytics)
