# Incept Video Architecture

## Purpose

This document defines the recommended product and technical architecture for the upcoming **Video** module in Incept Studio.

It is intentionally written before implementation so the team can align on:

- what to build first
- what to defer
- how video should fit into the current thread / asset / library system
- which parts of the current image stack can be reused
- how to keep the first release realistic and stable

This document is based on:

- the current Incept codebase
- the existing Studio thread and asset architecture
- the current Google Vertex AI / Veo capability shape at a high level
- modern AI video platform patterns used by products such as Runway, Kling, and similar workflow-based tools

This document is a planning reference, not an implementation log.

---

## Product Positioning

The Incept Video module should not start as a full timeline editor.

It should start as a **thread-based AI video generation workspace** that is optimized for short-form ad creative production.

The first release should focus on:

- generating short videos from strong visual anchors
- continuing or extending existing shots
- keeping all video outputs inside the same asset and thread system already used by Studio

The product goal is:

> turn Incept from an image-only creative workspace into a unified creative workspace for image, GIF, Kakao, and short AI video production.

---

## Current Codebase Readiness

The current project already contains several useful video-adjacent hooks:

- the shared asset model already supports `type: "video"`
- the tool registry already contains a mock `veo-video` tool entry
- the sidebar already contains a disabled `Video` entry
- the generic asset / thread / library system is already reusable for video outputs

Relevant files:

- `/Users/owen.geng/Documents/Projects/Incept/packages/incept-tool-registry/src/index.ts`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/tool_registry.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/models.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/web/components/incept/Sidebar.tsx`
- `/Users/owen.geng/Documents/Projects/Incept/apps/web/components/incept/Workspace.tsx`
- `/Users/owen.geng/Documents/Projects/Incept/apps/web/lib/incept-api.ts`

This means Incept does **not** need a separate storage platform for video.

It should reuse:

- threads
- jobs
- assets
- asset lineage
- library
- local/GCS storage strategy
- polling and job status patterns

However, the current generation request model is image-centric and should not be stretched too far.

The video system should have its own request models and workflow endpoints.

---

## Core Product Recommendation

### Recommendation

Build **Video as a separate Studio module**, not as another tab inside the current image creation box.

### Why

Image workflows are currently designed around:

- prompt + source image
- per-size image outputs
- deterministic asset cards

Video workflows need a different interaction model:

- duration
- aspect ratio
- motion instructions
- optional reference frames
- optional end frame
- video extension
- video-specific preview and playback

If video is forced into the current image creation panel, the UX will become crowded and harder to maintain.

### UI Direction

Enable the existing sidebar `Video` route and create a dedicated `CreateVideoView`.

Video should still live inside the same Studio shell and use the same:

- thread picker
- thread history
- assets panel
- library
- preview modal patterns

---

## Product Scope by Phase

## Phase 1 — Stable Foundation

Phase 1 should only include the capabilities that are most likely to be stable, valuable, and compatible with the current codebase.

### Phase 1 features

- `Image to Video`
- `First + Last Frame Storyboard`
- `Extend Video`

### What this means

#### 1. Image to Video

User uploads or selects one strong source image and enters a motion prompt.

Output:

- a short generated video
- one or more variants
- a poster frame stored as preview metadata

#### 2. First + Last Frame Storyboard

User provides:

- a start frame
- an end frame
- a motion / transition prompt

The system generates the transition shot between those frames.

#### 3. Extend Video

User takes an existing generated video and continues it for another short segment.

This fits the current thread model well because the new asset can clearly reference:

- parent video asset
- root video asset
- extension lineage

### Why Phase 1 should stop here

These three capabilities are:

- easy to explain
- commercially useful for ad creatives
- aligned with existing thread/asset lineage
- much lower risk than direct video remediation or face replacement

---

## Phase 2 — Workflow Depth

After Phase 1 is stable, add workflow features that make the product feel closer to modern AI video platforms.

### Phase 2 features

- `Reference Character / Ingredients`
- `Shot Presets`
- `Prompt Assist`
- `Storyboard Multi-Shot Planning`
- `Batch Video Variants`

### Product behavior

At this stage the system becomes less like a one-shot generator and more like a guided creative workflow.

Examples:

- reference face or character consistency across multiple shots
- predefined camera presets such as `push-in`, `pan-left`, `tracking`, `close-up`
- an AI assistant that rewrites vague user intent into a structured video prompt
- multi-shot planning inside a thread

This phase is where Incept begins to resemble Runway-style workflow tools rather than just a single prompt box.

---

## Phase 3 — Advanced Editing and Remediation

Phase 3 is where higher-risk and higher-complexity workflows can be added.

### Phase 3 features

- `Video Remediation`
- `Video-to-Video Restyle`
- `Synthetic Recast / De-identification`
- `Audio-aware generation`
- `Lip sync and dialogue-aware outputs`
- `Localized video edits`

### Important product note

These should not be Phase 1 features.

They are significantly more complex because they introduce:

- stronger safety filtering risk
- more expensive generation flows
- identity and likeness concerns
- frame consistency problems
- more difficult QA and preview requirements

For this reason, the initial version of Incept Video should **not** start with direct full-video policy repair or face replacement.

---

## Recommended User Experience

## Entry Point

Enable `Video` in the Studio sidebar as a first-class module.

Inside the video page, use a compact composition similar to the image page:

- top thread bar
- central generation area
- bottom composer / controls
- right assets drawer

## Phase 1 Composer Inputs

The first version should keep inputs minimal.

### Required fields

- `Source Image` or `Start Frame`
- `Prompt`

### Optional fields

- `End Frame`
- `Reference Images`
- `Duration`
- `Aspect Ratio`
- `Variants`
- `Camera Preset`

### Suggested default values

- Model: user-visible generic `Model`
- Engine default: official Veo model configured in backend
- Duration: `4s`
- Aspect ratio: `16:9`
- Variants: `1`

### Suggested supported aspect ratios in V1

- `16:9`
- `9:16`

Avoid supporting too many aspect ratios in the first release.

## Result Card Actions

Each generated video card should support:

- `Play`
- `Use as Start Frame`
- `Use as End Frame`
- `Extend`
- `Download`
- `Open in Library`

If a poster frame is available, it should also support:

- `Use poster as Source Image` for image workflows later

---

## Architectural Layers

The recommended architecture follows a layered workflow model.

## 1. Video UX Layer

Frontend components should stay separate from image-only composition logic.

Recommended files:

- `/Users/owen.geng/Documents/Projects/Incept/apps/web/components/incept/CreateVideoView.tsx`
- `/Users/owen.geng/Documents/Projects/Incept/apps/web/components/incept/VideoThreadView.tsx`

Responsibilities:

- file upload
- thread switching
- prompt editing
- preview playback
- action buttons for extend and reference reuse

## 2. Video Prompt Planning Layer

Add a dedicated prompt builder instead of reusing image prompt construction.

Recommended file:

- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/video_prompt_builder.py`

Responsibilities:

- structure user prompt into a stable video prompt
- separate:
  - subject
  - motion
  - camera behavior
  - environment
  - duration intent
  - style
  - negative constraints
- later support prompt assist and preset prompts

## 3. Video Orchestration Layer

Use a dedicated orchestration path for all video jobs.

Recommended files:

- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/video_store.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/video_service.py`

Responsibilities:

- request validation
- job creation
- async generation
- polling vendor APIs
- writing video assets back into thread history

## 4. Asset Canonicalization Layer

All source inputs should first become canonical assets inside the current asset system.

That includes:

- start frames
- end frames
- reference images
- source videos
- generated videos

This keeps all video flows consistent with existing Studio history and lineage behavior.

## 5. Generation Engine Layer

This is the vendor-facing layer.

It should remain isolated so that product logic is not tightly coupled to one provider call shape.

Responsibilities:

- send the official Veo-compatible request body
- handle async operation polling
- normalize returned outputs
- return stable internal structures back to the orchestration layer

## 6. Postprocess and Library Layer

After generation:

- store the video file
- extract or assign poster preview
- save metadata such as duration, width, height, aspect ratio, provider, model, lineage
- write a thread message and attach output assets

---

## Data Model Recommendation

The current image-oriented request model should not be overloaded with too many video-specific fields.

Instead, add dedicated video models.

## Recommended shared models

In `packages/incept-shared` add:

- `VideoGenerationMode`
- `VideoGenerationRequest`
- `VideoGenerationResponse`
- `VideoAssetSummary`

### Suggested request fields

- `workspace_id`
- `thread_id`
- `prompt`
- `provider`
- `model`
- `created_by`
- `variants`
- `duration_seconds`
- `aspect_ratio`
- `source_asset_id`
- `end_frame_asset_id`
- `reference_asset_ids`
- `video_generation_mode`
- `include_audio`
- `camera_preset`

### Suggested internal modes

- `image_to_video`
- `first_last_frame`
- `extend_video`
- `reference_character`
- `video_remediation`

## Backend models

Recommended location:

- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/models.py`

or a separate:

- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/video_models.py`

Using separate models is cleaner if the codebase continues expanding.

---

## API Recommendation

Add dedicated workflow endpoints instead of mixing video into image-generation routes.

### Recommended endpoints

- `POST /workflows/video-generation`
- `POST /workflows/video-extend`
- `GET /jobs/{job_id}`
- `GET /assets`

Phase 2 can later add:

- `POST /workflows/video-storyboard`
- `POST /workflows/video-remediation`

This keeps the system easy to reason about:

- image jobs stay image jobs
- video jobs stay video jobs
- frontend can branch clearly by workflow type

---

## Thread and Lineage Strategy

Video should reuse the same thread-first strategy already used by Studio.

### Rules

- every user video action belongs to one thread
- every generated video output is an asset
- extension outputs should point to the parent video asset
- poster frames and derived thumbnails should reference the same root lineage where useful

### Example lineage

`Start Frame Image` -> `Video Asset A` -> `Video Asset B (extend)` -> `Poster Asset`

This allows:

- easier thread playback history
- library grouping
- future compare/regenerate actions

---

## Storage Strategy

Video should follow the same storage policy already used by Studio assets.

### Recommended policy

- if a GCS bucket is configured and upload succeeds: store in GCS
- if no bucket is configured: explicit local temp mode
- if a bucket is configured but upload fails: hard fail

This matches the current Studio direction and avoids silent drift between environments.

### Video storage note

Video files will be larger than images, so GCS should be treated as the intended production path.

Local mode is acceptable for development only.

---

## Prompt Strategy

Video prompts should not reuse image prompt templates directly.

Video prompt construction should emphasize:

- shot framing
- camera movement
- motion quality
- facial focus
- environment continuity
- timing and pacing

### Recommended prompt structure

1. shot type
2. subject identity
3. subject motion
4. camera motion
5. lighting and environment
6. rendering style
7. negative constraints

### Example internal prompt sections

- `SHOT`
- `SUBJECT`
- `ACTION`
- `CAMERA`
- `ENVIRONMENT`
- `STYLE`
- `NEGATIVE`

This structured format will make future prompt assist and preset systems much easier to build.

---

## Safety and Policy Position

Video safety should be treated more conservatively than image safety.

### Practical recommendation

Do not start with direct "repair any violating video" workflows.

Start with:

- compliant source image to video
- storyboard generation
- controlled extension

Only later add:

- remediation
- identity de-identification
- synthetic recast

### Why

Video policy repair adds more operational risk:

- more visible artifacts
- higher chance of safety refusal
- higher identity risk
- more expensive QA

For high-risk remediation use cases, the better long-term pattern is:

1. extract key frames
2. repair images first
3. regenerate video from repaired anchors

This should be the first remediation strategy before attempting full video-to-video repair.

---

## What Not to Build First

The following should be explicitly deferred:

- full timeline editor
- arbitrary video-to-video restyle
- face swap as a front-facing V1 feature
- local mask brush for video
- audio timeline editing
- lip sync editing UI
- multi-minute productions
- too many aspect ratios

These are expensive to build and will slow down a stable launch.

---

## Recommended V1 Delivery Scope

If the team wants the fastest stable launch, V1 should be:

- separate `Video` module in Studio
- `Image to Video`
- `First + Last Frame`
- `Extend Video`
- `16:9` and `9:16` only
- `4s`, `6s`, `8s` only
- `1` or `2` variants only
- thread history + library integration
- video assets saved through the existing storage path

This is enough to be useful, demoable, and technically coherent.

---

## Suggested Implementation Order

1. Enable sidebar `Video`
2. Add `CreateVideoView` frontend skeleton
3. Add shared video request/response models
4. Add backend video workflow endpoint
5. Implement `Image to Video`
6. Save outputs into thread and library
7. Add `First + Last Frame`
8. Add `Extend Video`
9. Add prompt assist and reference flows
10. Add remediation later

---

## Open Questions Before Coding

The following decisions should be confirmed before implementation begins:

1. Should V1 support only `16:9` and `9:16`?
2. Should V1 support only `4s`, `6s`, and `8s` durations?
3. Should V1 start with `Image to Video` and `Extend Video`, while deferring text-only video generation?
4. Should audio generation be hidden in V1 even if the provider supports it?
5. Should poster frames be first-class assets in library, or only internal previews?

Recommended answers for V1:

- Yes
- Yes
- Yes
- Yes
- Internal preview first, explicit asset later if needed

---

## Final Recommendation

The best path for Incept is not "build a full AI video editor immediately."

The best path is:

> build a clean, thread-based short-video generation system that reuses the current asset architecture and grows into a workflow platform over time.

If implemented in phases, this approach is:

- technically realistic
- product-coherent
- easier to maintain
- easier to demo
- much safer than starting with full video remediation

This gives Incept a strong video foundation without destabilizing the current Studio image workflows.
