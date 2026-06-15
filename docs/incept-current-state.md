# Incept Current State

## Purpose

This document is a practical handoff summary of the current Incept Studio state.

It is intended to answer:

- what is already rebuilt
- which workflows are currently active
- which files matter most
- what is still rough or unfinished
- where to continue next on another machine or in another Codex thread

This document focuses on **Studio**, especially:

- Resize
- Theme Create
- Kakao
- GIF generation

## Big Picture

Studio has been simplified aggressively.

The current product direction is:

1. `Resize` is a direct per-size Gemini generation pipeline
2. `Theme Create` is now a separate Gemini-based workflow with 3 fixed modes
3. `Kakao` is a deterministic two-step system:
   - Gemini clean
   - fixed Bizboard composition
4. `GIF` generation is no longer AI frame-by-frame; it is a deterministic Python animation pipeline

Several older systems were intentionally removed or bypassed:

- old orchestrator logic for resize/theme create
- old guardrails / manifest / contact sheet / smart resize chains
- old OCR-heavy resize assumptions
- Kakao as a freeform generation workflow

## Current Status By Workflow

## 1. Resize

### Current Product Behavior

Resize is now a much simpler path:

- user uploads one source image
- user selects one or more target sizes
- backend generates each selected size independently with Gemini image generation
- outputs are saved directly to Library

There is no clarification popup / preserve-priority modal in the active resize path.

### Supported Resize Direction

The current resize logic is prompt-driven and size-specific.

Important special case:

- user-visible `728x90` now uses a hidden `728x180` generation canvas
- backend then splits that result into **two separate `728x90` outputs**

This means:

- users no longer see `728x180` as a selectable size
- selecting `728x90` produces two `728x90` assets
- the `728x90` prompt is effectively the oversampled split-sheet prompt now

### Important Resize Files

- `/Users/owen.geng/Documents/Projects/Incept/apps/web/components/incept/CreateImageView.tsx`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/prompt_builder.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/store.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/composite.py`

### Key Resize Implementation Notes

- Resize prompt selection lives in `prompt_builder.py`
- per-size generation loop lives in `store.py`
- `728x180 -> two 728x90` split helper lives in `composite.py`
- generated assets store analysis metadata such as:
  - `resize_requested_size`
  - `resize_generation_canvas_size`
  - `resize_pipeline`

This metadata is important because regenerate relies on it.

### Resize Prompt State

Current important prompt behavior:

- `320x50` has its own micro-banner prompt family
- `1200x222` / `640x100` use the large-banner prompt family
- `728x90` now maps to the dual-row oversampled prompt behavior
- landscape / portrait / square sizes each use their own template families

### Resize Risks / Known Caveats

- `728x90` behavior is now non-standard because one request yields two outputs
- some UI or downstream assumptions may still expect "one requested size = one output"
- broad frontend TypeScript verification was not completed successfully within a short run window; targeted checks and Python checks were done instead

## 2. Theme Create

### Current Product Behavior

Theme Create is now treated as a **fully separate workflow**.

It is no longer meant to behave like resize, and it is not supposed to share the old asset-role-card logic.

Theme Create currently supports only 3 modes:

1. `Style Modify`
2. `Style Transfer`
3. `Asset & Text Replace`

### Current Theme Create Input Model

The UI has been simplified away from the old large role-card system.

Current direction:

- always keep `Source Image`
- show `Reference Image` only when the mode needs it
- keep a main prompt box
- only `Asset & Text Replace` shows a few helper fields

Current mode structure:

#### Style Modify

- Source Image
- Main prompt

Backend maps the prompt into the style-modify prompt template fields.

#### Style Transfer

- Source Image
- Reference Image
- Main prompt

Backend uses:

- `[Image 1]` as content anchor
- `[Image 2]` as style reference

#### Asset & Text Replace

- Source Image
- Reference Image A (new logo)
- Reference Image B (new button / element)
- Main prompt
- Helper fields:
  - old text
  - new text
  - logo position
  - element position
  - font style

### Theme Create Prompt State

The three Gemini-oriented prompt templates were added to `prompt_builder.py` and intentionally follow the provided prompt structures directly.

Important prompt builder functions:

- `build_theme_create_style_modify_prompt`
- `build_theme_create_style_transfer_prompt`
- `build_theme_create_asset_text_replace_prompt`

### Theme Create Backend State

Theme Create now has its own branch in `run_generation_background()` in `store.py`.

It does not go through the old resize path.

It chooses the prompt and reference-image ordering based on `theme_create_mode`.

Current fixed image order:

- `style_modify`
  - `[Image 1] = source`
- `style_transfer`
  - `[Image 1] = source`
  - `[Image 2] = reference`
- `asset_text_replace`
  - `[Image 1] = source`
  - `[Image 2] = new logo`
  - `[Image 3] = new element`

### Important Theme Create Files

- `/Users/owen.geng/Documents/Projects/Incept/apps/web/components/incept/CreateImageView.tsx`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/models.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/store.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/prompt_builder.py`
- `/Users/owen.geng/Documents/Projects/Incept/packages/incept-shared/src/index.ts`

### Theme Create Risks / Known Caveats

- The old `style_match` generation mode still exists in shared types and some backend enums, but the active UI path has been shifted away from it
- Theme Create UI was simplified, but not all cosmetic cleanup may be finished
- The current mapping of main prompt into the style-modify template is functional but could be refined later if a cleaner prompt schema is desired

## 3. Kakao

### Current Product Behavior

Kakao is no longer treated as a generic freeform image generation tool.

It is now conceptually:

1. `Kakao Clean`
2. `Kakao Bizboard Compose`

Only `Bizboard 1029x258` is in scope.

### Kakao Clean State

Kakao clean currently uses a short generic Gemini prompt, because long specific prompts previously caused safety/compliance refusals.

The prompt direction that worked was intentionally simple.

The key lesson is documented separately:

- `/Users/owen.geng/Documents/Projects/Incept/docs/incept-kakao-clean-debugging.md`

### Kakao Bizboard State

After clean:

- user confirms cleaned results
- a deterministic fixed Bizboard template is composed
- final output is a locked `1029x258` PNG

This composition is not freeform AI layout.

Important Kakao files:

- `/Users/owen.geng/Documents/Projects/Incept/apps/web/components/incept/KakaoFlow.tsx`
- `/Users/owen.geng/Documents/Projects/Incept/apps/web/lib/kakao-compositor.ts`
- `/Users/owen.geng/Documents/Projects/Incept/docs/incept-kakao-bizboard-flow.md`

### Kakao Risks / Known Caveats

- Composition is currently client-side and deterministic, but could still be moved to backend later if server-side rendering is preferred
- Kakao text validation can still be tightened further

## 4. GIF Generation

### Current Product Behavior

GIF generation is now deterministic and programmatic.

The flow is:

1. user selects an existing static asset
2. backend reads the static image
3. Python generates animation frames
4. frames are encoded and saved back to Library

There is no AI frame-by-frame animation generation in the current GIF pipeline.

### Current Motion Direction

The GIF approach was moved away from flashing a CTA rectangle.

The current preferred direction is:

- subtle full-frame cinematic sweep
- light breathing / global motion
- deterministic animation from one base image

This is documented in:

- `/Users/owen.geng/Documents/Projects/Incept/docs/incept-gif-python-vs-canvas-plan.md`

### Important GIF Files

- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/gif_generator.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/store.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/web/components/incept/CreateImageView.tsx`
- `/Users/owen.geng/Documents/Projects/Incept/apps/web/components/incept/Workspace.tsx`

### GIF State Summary

- independent GIF generation endpoint exists
- GIF actions exist in assets/library flows
- `320x480` was added to GIF support
- current output is better than the earlier rectangle-flash version
- future best direction is still structured overlay animation, not inferred mask animation

## Current Files Most Worth Knowing

If someone new has to resume work quickly, these are the most important Studio files:

### Frontend

- `/Users/owen.geng/Documents/Projects/Incept/apps/web/components/incept/CreateImageView.tsx`
- `/Users/owen.geng/Documents/Projects/Incept/apps/web/components/incept/Workspace.tsx`
- `/Users/owen.geng/Documents/Projects/Incept/apps/web/components/incept/KakaoFlow.tsx`
- `/Users/owen.geng/Documents/Projects/Incept/apps/web/lib/incept-api.ts`
- `/Users/owen.geng/Documents/Projects/Incept/apps/web/lib/kakao-compositor.ts`

### Backend

- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/store.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/prompt_builder.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/composite.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/gif_generator.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/incept/models.py`
- `/Users/owen.geng/Documents/Projects/Incept/apps/api/app/routers/incept.py`

## Documentation Map

Useful supporting docs:

- `/Users/owen.geng/Documents/Projects/Incept/docs/incept-architecture.md`
- `/Users/owen.geng/Documents/Projects/Incept/docs/incept-kakao-clean-debugging.md`
- `/Users/owen.geng/Documents/Projects/Incept/docs/incept-kakao-bizboard-flow.md`
- `/Users/owen.geng/Documents/Projects/Incept/docs/incept-gif-python-vs-canvas-plan.md`

## What Was Verified

The following was explicitly verified during recent work:

- Python syntax checks for the touched backend files using `py_compile`
- targeted code-path checks for:
  - resize prompt routing
  - `728x90` oversampled split logic
  - Kakao clean / Bizboard structure
  - Theme Create prompt routing

What was **not** fully verified end-to-end:

- full project TypeScript compilation in a short single run
- all browser-side flows in live manual QA after the latest Theme Create simplification

So the current state should be treated as:

`architecturally aligned and partially validated, but still worth live UI testing`

## Recommended Next Steps

If continuing work from here, the highest-value next actions are:

1. Live test all 3 Theme Create modes in the browser
2. Verify `728x90` now consistently returns two outputs and that downstream UX handles that cleanly
3. Test Kakao clean + Bizboard compose end-to-end on a few real creatives
4. Decide whether Theme Create should keep the small helper fields for `Asset & Text Replace` or compress further
5. Decide whether GIF should remain GIF-first or start exposing animated WebP / MP4

## One-Sentence Summary

Studio is now much simpler than before:

`Resize is prompt-per-size, Kakao is clean-plus-template, Theme Create is a separate 3-mode Gemini workflow, and GIF is deterministic Python animation rather than AI frame generation.`
