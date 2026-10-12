# LinglongLab Video post-production backlog

Status: deferred by user instruction on 2026-10-12. Do not implement these
features as part of the 3W CTV production test.

The migrated Toonflow baseline has source video/audio nodes and FFmpeg tools;
it has not been verified to provide a complete web post-production editor.

| Deferred capability | Required user outcome | Acceptance evidence |
| --- | --- | --- |
| Web multi-track timeline | Arrange video, voiceover, music and captions in a saved edit revision | Reload retains timing and selected assets |
| Automatic captions and correction | Transcribe speech, edit text and timing | English text and timing reviewed against actual speech |
| Subtitle burn-in | Export readable, correctly positioned captions | Captions visible in downloaded video |
| Voiceover alignment | Align narration with each shot | Full playback confirms synchronized narration |
| Source / voiceover / music mixing | Preserve intended source audio and control track levels | Downloaded export contains an audible, reviewed mix |

## Current limitation

`apps/api/app/video_studio/render.py` removes source audio while normalizing
clips, then optionally adds one `soundtrack_path`. `ExportRequest` has no caption
track or multi-track mixing contract. This is not a complete sound/caption
production pipeline.

## 3W production acceptance boundary

Requested deliverable: English 30-second CTV video, 1920×1080, 16:9, with sound,
voiceover and subtitles, total generation budget at most CNY 100.

Offline finishing may produce a client preview without adding the deferred
product features. Any such deliverable must retain its script, caption file,
audio assets, composition instructions, generation records and QA in the project.
It does not establish that LinglongLab's native export supports these features.
Do not mark the end-to-end built-in sound/caption workflow as passed.

## Model change requested

Requested image default: `gemini-nano-banana-2.1`; fallback:
`gemini-3.1-flash-image`. Retire `gpt-image-2.5-flare` from the Video image menu.
The user confirmed Vertex AI. The [official model documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/nano-banana-2-1)
confirms `global`; the [pricing page](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing)
lists image output at USD 30 per million tokens for standard global service.
Fallback is a selectable alternative, not an automatic paid retry.

## MCP readiness

The authenticated server is implemented in `apps/api/app/video_studio/mcp.py`
and conditionally mounted at `/video-studio-mcp/`. It requires an HTTPS
`VIDEO_STUDIO_MCP_PUBLIC_URL` and `VIDEO_STUDIO_MCP_PRINCIPALS`.
The local settings inspected on 2026-10-12 have neither configured, and this
Codex chat exposes no LinglongLab Video MCP connector. No credentials or access
grants were created for this test. Cloud deployment readiness is unverified.
