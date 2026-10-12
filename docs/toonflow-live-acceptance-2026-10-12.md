# LinglongLab live workflow acceptance — 2026-10-12

This is a local, single-user acceptance run on `toonflow-native-host`, not a
production deployment or a five-user Cloud Run load test. The user authorized
project `验收` and a total CNY 100 budget. Production cloud/model configuration
was preserved.

## Why previous checks missed these defects

Adapter tests mostly exercised synthetic model responses, including single tool
calls. They did not enforce Gemini's parallel-response turn contract. The UI
translation audit accepted catalogue substrings, missed composed runtime port
labels, and did not translate image alt attributes. UI and Agent language settings
were separate, and old SDK conversations lacked a locale-change event. Browser
smoke checks stopped before media attachment, provider references, refresh,
playback and download. Passing those checks established their limited coverage,
not complete user workflow acceptance.

## Defects reproduced and repaired

| Defect | Repair and evidence |
| --- | --- |
| Gemini rejected multiple tool results | Consecutive Pi results share one Gemini response turn, retaining IDs, error flags and signatures; real model continued the creation flow. |
| Small stream events buffered through Next.js | NDJSON responses prohibit compression transformation; running status and exact approval cards were visible before the model round finished. |
| English UI with Chinese Agent configuration/history | Reconcile Vue and Agent locale settings, await settings saves, localize the native default language, and retain locale changes as Pi custom messages; both a fresh conversation and the original Chinese-history conversation replied in English. No history text was reconstructed. |
| Missing dynamic/accessible translations | Localized port labels, image alt text, download-copy/image-edit controls and tab closing; strengthened the audit to reject untranslated complete static labels even when a substring is translated. |
| Attached media disappeared from mounted nodes | Node outputs hydrate externally replaced canvas data before publishing component outputs. Image and video previews survived browser reload. |
| Reference video rejected local images | Preserve MIME in workspace-frame data URLs, upload exact approved frames to unique owned GCS objects, pass the existing Omni reference contract, and clean temporary objects after success/failure. Model IDs, endpoints and regions were unchanged. |
| Silent request retained provider audio | The generated-media writer now removes audio locally when `generate_audio=false`, copying the video stream. A real FFmpeg regression checks audio removal, duration and dimensions. |
| Chat project links displayed `[Blocked]` | Resolve relative AST references through authenticated workspace reads and rebuild their rendering when the project binding becomes available. External/unsafe paths are not promoted to project references. |

## Actual production chain

Project `5525832b645f4d479f757f78492aff5a` contains the brief, storyboard, two
keyframes, two video takes, five canvas nodes, final export and
`acceptance-manifest.md`. Two reference attempts failed locally before a video
provider request; corresponding second-shot requests were cancelled. There were
two successful real image generations and two successful real video generations.
No automatic paid retry was authorized.

The final file is `exports/red-boat-acceptance-6c0e8b4e.mp4`. Independent FFprobe
verification found 8.000 seconds, 1280×720, 24 fps, 192 frames and zero audio
streams. Browser playback reached the end without a media error. A one-frame-per-
second contact sheet covered both shots. Browser download was verified by matching
the downloaded file's SHA-256 with the project export. The original provider
clips have audio and remain as evidence; their manifest was corrected to state
that, and the final export is silent. No new paid generation was used to verify
the audio-removal repair.

English and Chinese interface checks cover the canvas controls, node ports,
question cards, file tree, document toolbar and search panel. User-authored
Chinese project names and historical messages are preserved. These checks do
not prove every screen/dialog or every future model response is defect-free.

## Budget and acceptance boundary

Observed SDK usage across this test project's sessions: 451,664 uncached input,
1,250,980 cached input and 23,400 output tokens. Together with two images and
8 seconds of 720p video, a conservative estimate using published rates and
CNY 10 per USD as a budgeting allowance is about CNY 30, below the authorized
limit. This is an estimate, not a billing reconciliation; SDK zero-cost fields
were not treated as free usage. Pricing source:
[Google Cloud pricing](https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing).

Local checks: 608 API cases, 56 native runtime cases, 90 frontend cases and
3 translation-audit cases passed without failures or skips. Workspace typechecks,
node/web builds and the strengthened translation audit passed. GitHub checks must
be evaluated against the final commit separately.

Not accepted by this run: deployed Cloud Run behavior, simultaneous real usage
by five users, live external search reliability, every provider/model option,
long-form production, or commercial creative quality. The short test's two shots
show a visible background/color change; technical workflow success does not make
this a finished commercial creative.
