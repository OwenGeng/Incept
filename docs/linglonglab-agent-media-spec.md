# LinglongLab Agent multimodal input

Status: approved by the user ("继续"). Extends the approved request to complete image input
and remove the blanket 10/20 MiB limitation for customer video analysis.
Risk: medium (untrusted media processing, request memory and provider payloads).

## Objective and acceptance criteria

1. A customer can attach images to the selected Gemini, OpenAI or Claude Agent.
   The backend sends real image content in the provider's documented format;
   the UI no longer rejects all non-Gemini image attachments. Models, endpoints,
   project IDs and cloud locations remain exactly as configured by the user.
2. Customer videos up to the confirmed 450,000,000-byte CTV file limit can enter
   the Agent workflow. Upload/storage admission, preprocessing limits and
   provider request budgets are separate, named constraints—not misrepresented
   as model capabilities. Original files remain unchanged.
3. Gemini analyzes a bounded video proxy when inline transmission is appropriate;
   an existing configured private GCS bucket may supply an owned file reference
   when supported. Do not create a bucket, publish files, change IAM or guess
   configuration. If storage is unavailable, use the bounded proxy path or
   report a concrete failure; do not silently pretend analysis succeeded.
4. OpenAI/Claude receive bounded, timestamped image samples from videos, with
   the inspected range, sampling density and missing-audio limitation explicit.
   They must not claim native full-video/audio analysis on this route. Sampling
   must not be described as proof that every frame was inspected.
5. Image resizing or video proxying affects only an analysis copy. Show when
   detail was reduced. Failed/cancelled preprocessing leaves the original intact,
   creates no completed-analysis claim, and cleans up temporary artifacts.
6. Keep genuine per-provider/per-input limits and bounded total payload, pixel,
   duration, subprocess time and processing concurrency budgets. Exceeding a
   budget gives a specific actionable explanation, not an arbitrary blanket
   metadata-only downgrade. Long clips require an explicit analysis range when
   the complete clip exceeds the processing budget.

## Scope and non-goals

- Scope: existing authenticated attachment upload; provider image adapters;
  bounded video preprocessing; truthful attachment inspection manifests;
  current-turn cancellation; frontend warnings; regression tests and docs.
- Non-goals: model migration, new providers, new infrastructure, credentials or
  IAM changes, public links, production deployment, advertising-rights clearance,
  and changing the original CTV export requirements.
- Native audio/transcription for OpenAI/Claude is not inferred from image support.
  Gemini's existing audio path is retained. A separate transcription integration
  would require its own verified API/model contract.

## Implementation boundaries

Use Python/FastAPI and the existing OpenAI, Anthropic, Google GenAI, Pillow,
FFmpeg/FFprobe and Google Cloud Storage dependencies. Keep media preparation in
a focused Video Studio module, not provider configuration or canvas operations.
The Agent continues to use prepared parts and an inspection manifest; extend
that manifest with native-image/video-proxy/sampled-frames inspection modes.
Default optional fields preserve saved conversation compatibility.

Example provider boundary (illustrative, not a model/config change):

```python
content = [{"type": "input_text", "text": prompt}]
content.append({"type": "input_image", "image_url": image_data_url})
```

- Always: validate ownership and file content, resolve files within tenant/project
  roots, limit allocation and processing, use subprocess argument lists rather
  than a shell, forbid media demuxer network access, check cancellation, sanitize
  errors, and disclose exactly what reached the selected model.
- Ask first: new dependencies, changed cloud configuration/permissions, new
  external transcription services, or paid/live integration tests beyond the
  agreed smoke check.
- Never: replace originals, expose private media via public URLs, send another
  tenant's files, infer unsupported model IDs, or call a metadata-only attachment
  "analyzed".

## Test strategy and commands

Use existing pytest tests in `apps/api/tests/` with isolated temporary project
storage. SDK calls are stubbed only at the provider boundary; assert actual
constructed multimodal request bodies. Use real tiny generated videos to verify
sampling/proxying, original-file preservation, timestamp mapping and cleanup.
Cover corrupt media, path escapes, cancellation, missing FFmpeg/storage, bounded
output, provider rejection and attachment persistence/retry.

```sh
# From apps/api; production metadata is disabled for tests.
VIDEO_STUDIO_METADATA_DATABASE=false DATABASE_URL= DATABASE_CONFIG_JSON= PYTHONPATH=.:tests .venv/bin/pytest tests -q
# From apps/video-vue
pnpm typecheck
pnpm build:web
node --experimental-strip-types --test apps/web/src/components/agent/attachmentInput.test.ts apps/web/src/components/agent/conversationInput.test.ts apps/web/src/components/agent/replyStream.test.ts apps/web/src/components/agent/conversationDelete.test.ts
```

Frontend changes reuse the current attachment controls and progress UI. Verify
in an isolated real browser with synthetic media and intercepted provider calls;
distinguish this from a production/live-model smoke test.

## Verified reference contracts

- [OpenAI image input](https://developers.openai.com/api/docs/guides/images-vision):
  Responses `input_image` blocks with an image URL, base64 data URL or file ID.
- [Claude vision](https://platform.claude.com/docs/en/build-with-claude/vision):
  Messages `image` blocks with documented source types and image/request limits.
- [Google video understanding](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/video-understanding):
  inline media and Cloud Storage file references; exact capability and admission
  depend on the configured model and input transport, not a universal 10/20 MiB rule.

## Proposed build order

1. Provider image adapters and real-payload regression tests.
2. Bounded local video preparation, cancellation and security tests.
3. Existing-storage reference integration and explicit fallback/error behavior.
4. Upload admission and frontend capability/warning alignment.
5. Full regression suite, browser verification, review and documentation.

## Confirmed semantics and release boundary

User approved video analysis semantics: Gemini video/proxy input; OpenAI/Claude
timestamped sampled frames with explicit lack of audio/full-frame coverage.
No model/cloud configuration or production data migration is proposed.

Implemented with mocked SDK wire tests, real tiny-video processing and isolated browser tests.
Live provider/private-GCS validation and 450 MB stress uploads remain unverified. Cloud Run
HTTP/1 ingress has a separate 32 MiB per-request cap; deployment transport changes are outside
this application-only change. See the hardening document for current safety budgets and checks.
