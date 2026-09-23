# Incept Video Roadmap

> Updated: 2026-07-08  
> Scope: practical roadmap for Incept video capabilities based on the current Studio architecture, available Vertex AI models, and our existing image / asset / thread system.

---

## Product Direction

Incept should treat video as a production pipeline, not as a single model call.

The recommended order is:

1. **Playable -> Video**
2. **Competitor Video -> Video Style Transfer**
3. **Video -> Playable**

### Testable MVP surface

The first directly testable release should expose four paths in the Video
workbench:

| User flow | Input | Output |
| --- | --- | --- |
| Image -> Video | One source image and optional direction | Veo Fast MP4 variant(s) |
| Playable -> Video | One self-contained HTML playable and optional direction | Playable analysis report plus Veo Fast MP4 variant(s) based on the playable visual language |
| Competitor Style Transfer | One source image plus a reference image/video | Style report plus Veo Fast MP4 variant(s) |
| Video -> Playable | One source video and optional reference image | Flash-Lite analysis, a Gemini 3.5 playable draft, and a self-contained Moloco HTML playable |

The initial Video -> Playable runtime supports a guided two-choice interaction.
Additional interaction templates are added only after each has its own
deterministic browser test path and Moloco validation coverage.

This ordering is intentional:

- **Playable -> Video** is the most deterministic and least dependent on model creativity.
- **Competitor Video -> Video Style Transfer** has strong business value but should start from controlled reference-based generation, not fully open-ended transfer.
- **Video -> Playable** is valuable, but it depends on a reusable playable template/runtime system and should come after the video pipeline is stable.

---

## Phase 1 — Playable -> Video

### Goal

Allow a user to upload an HTML5 playable bundle, automatically run it in a controlled browser session, record a clean gameplay path, and export an MP4 video asset.

Optional enhancement:

- pass the recorded video through **Veo Fast** for visual polish, motion smoothing, or cinematic enhancement

### Why this should come first

- It solves a real advertiser problem immediately: existing playable creatives cannot always be reused in video-only placements.
- It does **not** require the video model to invent gameplay.
- It reuses our current strengths: asset storage, threads, generation history, and output management.

### Core flow

```text
Upload playable HTML bundle
        ->
Unpack and validate bundle
        ->
Launch headless browser runtime
        ->
Auto-detect interactive elements
        ->
Run scripted interaction path
        ->
Record browser session to video
        ->
Export MP4
        ->
Optional Veo Fast enhancement
        ->
Save to thread + library
```

### Capture implementation

Playable -> Video is a real browser-capture pipeline, not an image-to-video
shortcut:

1. Flash-Lite analyzes the uploaded self-contained HTML and returns a compact
   interaction plan with normalized click, drag, swipe, and wait actions.
2. Incept injects that plan only into a temporary capture copy of the playable.
3. Creative Core opens the capture copy in headless Chrome through Chrome
   DevTools Protocol, executes the interaction path, and captures frames.
4. FFmpeg encodes those captured frames into an H.264 MP4.
5. The temporary capture project is deleted; the original uploaded playable is
   never modified.

The capture environment must provide Creative Core, Google Chrome/Chromium,
Node.js/pnpm, and FFmpeg. This has been locally verified with a 15-second
1920x1080 H.264 MP4 export. Cloud Run deployment needs the same runtime
dependencies provisioned in the renderer environment before this workflow is
enabled there.

### Can the browser auto-interact?

**Yes.**

A browser can automatically interact with a playable using Playwright or Puppeteer.

This is not speculative. It is a standard automation pattern.

The browser runtime can:

- click buttons
- drag/swipe
- wait for animations
- trigger retries
- simulate taps at specific coordinates
- follow scripted or model-generated paths

### Recommended implementation strategy

We should support **three levels of automation**, in this order:

#### Level 1 — Deterministic scripted playback

Use predefined logic:

- wait for loading
- click “start” / “play”
- detect CTA
- perform a short best-effort interaction path
- stop after target duration

Best for MVP because it is stable and cheap.

#### Level 2 — DOM-assisted auto-play

Use browser inspection plus LLM analysis to understand:

- clickable nodes
- canvas regions
- major UI states
- probable gameplay loop

The LLM does **not** run the playable.
It only produces an interaction plan such as:

```json
[
  { "type": "wait", "ms": 1200 },
  { "type": "click", "selector": "#play-button" },
  { "type": "drag", "from": [320, 900], "to": [520, 900], "duration_ms": 600 }
]
```

The browser runner executes the plan.

#### Level 3 — Human-adjustable interaction path

If the generated interaction path is poor, let the user:

- replay
- choose a different interaction style
- optionally edit the path

This is ideal for v1.5 or v2.

### Required backend pieces

1. **Playable upload pipeline**
- accept zip / html bundle
- unpack into isolated temp workspace
- validate entrypoint
- rewrite relative asset paths if needed

2. **Browser execution service**
- Playwright preferred
- fixed viewport
- mobile/vertical presets
- capture console and runtime errors

3. **Recording pipeline**
- record session to mp4/webm
- trim leading idle frames
- export poster frame
- persist metadata

4. **Interaction planner**
- deterministic fallback
- optional Gemini analysis for better click/drag sequence

5. **Thread/library integration**
- recorded videos saved as generated assets
- playable source saved as source asset
- outputs linked to the same thread

### Risks

- Some playables are pure canvas and expose little DOM structure.
- Some bundles depend on blocked external assets.
- Some playables need timing-sensitive interactions.
- Browser recording performance must be stable in Cloud Run or a worker environment.

### MVP success definition

- Upload playable bundle
- Auto-run in a browser
- Produce a clean 6–15 second MP4
- Save into current thread and library
- Optional “enhance with Veo Fast” button

---

## Phase 2 — Competitor Video -> Video Style Transfer

### Goal

Take a competitor reference video and generate a new branded video with a similar visual language, pacing, and tone.

### Business value

- This is one of the strongest user asks: “my competitor has a winning video, help me make something like it.”
- It pairs naturally with SensorTower Top Creatives and future insight products.

### Important product rule

We should **not** start with “full arbitrary video-to-video transfer.”

We should start with a controlled pipeline:

```text
Competitor video
        ->
Keyframe extraction
        ->
Gemini visual analysis
        ->
Structured style descriptor
        ->
Reference-based video generation
        ->
Branded output
```

### What Gemini should extract

- color palette
- composition style
- subject framing
- motion energy
- transition feel
- headline / CTA placement style
- lighting mood
- texture / rendering style

### Recommended MVP

Start with:

- one user source image or source short clip
- one competitor reference video
- one structured style summary
- one generated output video

This is much more realistic than a full direct transfer engine.

### Why this is harder than Playable -> Video

- More model-dependent
- Harder to preserve brand identity while borrowing style
- Motion, pacing, and framing are much less deterministic

### Model guidance

- **Veo Fast** is fine for early iterations and lower-cost preview runs
- stronger models help here more than in Playable -> Video
- if we later need higher fidelity, this is the phase where model upgrades matter most

---

## Phase 3 — Video -> Playable

### Goal

Take an input video and generate a lightweight HTML5 playable ad by mapping the content to a known gameplay template.

### Important constraint

This must be **template-based**.

We should not attempt:

- arbitrary video -> arbitrary playable generation

We should instead do:

```text
Input video
        ->
Gameplay classification
        ->
Template selection
        ->
Asset extraction
        ->
Template slot replacement
        ->
Moloco-compliant playable export
```

### Product definition: an AI-assisted interactive video engine

We do not need to recreate Unity or Cocos. Incept should build a lightweight,
template-driven **interactive video engine** for advertising:

- a visual layer for backgrounds, short video loops, image assets, and effects
- an interaction layer for taps, swipes, drags, choices, and simple drawing
- a deterministic state machine that controls fail, success, retry, and end-card
  transitions
- an AI layer that analyzes source material and fills a known template; it does
  not invent or execute arbitrary game logic at runtime

This is the useful part of the "video-driven playable" idea. It is especially
well suited to acquisition creatives, where the interaction is intentionally
short, guided, and conversion-oriented rather than a full game.

### Runtime approach

Use a small TypeScript/JavaScript runtime, based on native DOM/Canvas first.
PixiJS can be introduced only if a template needs higher-performance 2D
rendering. Avoid Unity/Cocos for the initial product because our goal is a
small, deterministic ad runtime, not a general-purpose game engine.

Each playable should consist of:

```text
Background / video / image layers
        +
Template interaction component
        +
State-machine scene flow
        +
Audio and CTA / end-card layer
        ->
Single Moloco-ready HTML output
```

Video can make a playable feel visually rich, but it must be used selectively.
It is appropriate as a background, transition, result animation, or end card.
The actual conversion interaction must remain simple code-driven UI so it is
reliable, measurable, and responsive on device.

### Playable schema

The equivalent of a Remotion composition for Incept should be a validated
`PlayableSchema`: a structured configuration that describes scenes, assets,
interactions, and transitions. Templates own the executable code; AI produces
or edits configuration only after validation.

Example shape:

```json
{
  "template": "swipe_collect_v1",
  "canvas": { "width": 1080, "height": 1920 },
  "assets": {
    "background": "background.webp",
    "hero": "hero.png",
    "cta": "cta.png"
  },
  "scenes": [
    {
      "id": "tutorial",
      "interaction": "swipe_collect",
      "onSuccess": "win",
      "onTimeout": "fail"
    },
    { "id": "win", "type": "endcard" }
  ]
}
```

This makes creative variations cheap: the template remains stable while asset
URLs, copy, colors, coordinates, timing, and interaction parameters change.

### AI responsibilities

AI should assist the production pipeline, not replace the engine:

- classify the gameplay or interaction pattern from an image/video
- recommend the closest existing template
- map uploaded assets into template slots
- produce a draft `PlayableSchema` for validation
- propose copy, colors, and interaction parameters for variants
- later, suggest asset extraction or generated replacements when the source is
  incomplete

Asset segmentation, generated art, and generated audio are useful later-stage
accelerators, but they are not prerequisites for the first working templates.

### Recommended initial templates

1. Tap / choice puzzle
2. Swipe Collect
3. Drag and Drop
4. Draw to Protect
5. Simple Match-3 preview

Start with a small number of high-quality templates rather than attempting a
large library. Each new template should be built as a reusable interaction
component with documented slots, success/failure states, and a test path.

### Why this comes later

- Requires a full template runtime
- Requires asset extraction quality
- Requires template and runtime validation
- Requires predictable single-file packaging for Moloco

### Moloco-only export scope

For this phase, Incept exports for **Moloco only**. We do not need a general
multi-network adapter layer. The exporter should focus on the exact Moloco
creative constraints, bundle the runtime and assets into one self-contained
HTML file, and validate the resulting artifact before download. Other ad
networks can be added later only when there is a concrete business need.

### Moloco standalone playable and IEC requirements

The runtime and exporter must treat the following as release-blocking
requirements, based on Moloco's *Playable and Interactive End Card (IEC)
creative guide*:

| Area | Required behavior |
| --- | --- |
| Upload format | Deliver one `.html` or `.htm` file, never a ZIP archive. |
| File size | Final ad file must be smaller than 5 MB. |
| Layout | Support both portrait and landscape and remain responsive across phone, tablet, and desktop viewports. |
| Asset delivery | Inline every image, sound, font, and video asset as a compressed data URI. No external URLs, HTTP requests, or dynamic asset loading. |
| Forbidden APIs | Do not include `XMLHttpRequest` or `mraid.js`. |
| Redirects | Do not include JavaScript redirects. |
| CTA | The intended CTA must call `FbPlayableAd.onCTAClick()` with no parameters. |
| Preview validation | The playable must expose a working CTA path so it can be exercised in Moloco Ads Manager's preview tool. |

An IEC is the same interactive demo preceded by a video ad. A standalone
playable contains only the interactive demo. The Incept template runtime should
therefore keep the demo self-contained, while IEC assembly can be added as a
separate composition layer later.

### Moloco validator

Every generated playable should be statically validated before it appears as
downloadable:

1. Verify HTML extension, size, and responsive viewport metadata.
2. Reject `XMLHttpRequest`, `mraid.js`, JavaScript redirects, ZIP output, and
   external `src` / `href` references.
3. Verify that `FbPlayableAd.onCTAClick()` is present with no argument.
4. Verify that referenced media uses `data:` URIs only.
5. Run a local browser smoke test of the template's deterministic CTA path.

The report should be saved into the same thread beside the generated playable,
so a user sees both the HTML artifact and its Moloco readiness result.

### Does this need a bigger model?

**Not primarily.**

What it needs most is:

- a gameplay classification schema
- a playable template system
- asset slotting rules
- export/runtime validation

The model is helpful for:

- classifying gameplay
- explaining which assets map into which slots
- generating text / copy / simple logic suggestions

But the model should **not** be the runtime.

### Model split for the testable MVP

| Task | Model / implementation |
| --- | --- |
| Image -> Video and video output | `veo-3.1-fast` |
| Image/video/playable analysis and style reports | `gemini-3.6-flash` |
| Image generation or replacement | `gemini-3.1-flash-image` |
| Playable concept and validated schema draft | `gemini-3.6-flash` |
| Final playable | Deterministic Moloco runtime rendered from the validated schema, not arbitrary model-authored JavaScript. |

This split keeps analysis inexpensive, reserves Veo Fast for motion generation,
and makes the final HTML auditable and repeatable.

---

## System Architecture Principles

These phases should share one media production architecture.

### 1. Unified asset model

We should support:

- source image
- source video
- playable bundle
- generated video
- analysis report
- extracted keyframes
- poster frame
- derived enhanced video

### 2. Unified thread model

A single thread should contain:

- uploaded source
- analysis results
- generated outputs
- enhancement passes
- follow-up edits

### 3. Code-driven composition layer

AI should generate or transform raw media, but final assembly should increasingly be code-driven:

- captions
- title cards
- transitions
- overlays
- end cards
- format variants

This is where a Remotion-like approach becomes highly valuable.

### 4. Provider abstraction

The UI should not be tightly coupled to one provider.

Internally we should be able to swap:

- Veo Fast
- stronger Veo tier later
- browser recording pipeline
- future stock footage / montage pipeline

### 5. Playable runtime and template governance

The playable runtime should be versioned separately from creative data:

- templates own executable interaction code
- `PlayableSchema` is validated against each template version
- generated drafts are never executed until validation passes
- each exported file records its template and schema version
- a deterministic test path is stored with the template for browser preview and
  future Playable -> Video capture

### 6. Budget and governance

Video generation must include:

- per-user budget checks
- preview vs final quality modes
- clear failure logging
- retry logic
- queued processing

---

## Deployment: Cloud Run Browser Capture

Playable-to-video is real browser capture, not an image-to-video fallback. The deployed API image includes Chromium, FFmpeg, Node.js, pnpm, and a prepared Creative Core workspace. `Dockerfile.api` receives Creative Core through a named Docker build context, so a local developer path is used only while building the image and never at runtime:

```bash
CREATIVE_CORE_BUILD_CONTEXT=/Users/owen.geng/.moloco/cr-agent/creative-core
./deploy.sh api
```

The initial controlled deployment runs capture in the API service with 2 CPUs, 4 GiB memory, a 900-second timeout, concurrency 1, and non-throttled CPU. This is sufficient for functional Cloud Run validation. Before enabling concurrent production capture, move this work into a dedicated Cloud Run renderer job/service with durable task state and GCS outputs; FastAPI `BackgroundTasks` are not a durable queue.

## Recommended Near-Term Build Order

### Sprint A

- playable upload model
- browser runner
- fixed viewport recording
- thread + asset persistence

### Sprint B

- deterministic interaction playback
- mp4 export
- preview in library and create page

### Sprint C

- optional Gemini-based interaction planning
- optional Veo Fast enhancement step

### Sprint D

- competitor video keyframe extraction
- Gemini style analysis schema
- reference-based video generation prototype

### Later

- template-driven video -> playable
- AI-assisted asset extraction, replacement, and audio generation
- broader playable template library

---

## Final Recommendation

The current best path is:

1. Build **Playable -> Video** first
2. Then build **Competitor Video -> Video Style Transfer**
3. Build a small, validated **Moloco-only playable runtime** with a handful of
   reusable templates
4. Then add **Video -> Playable** as AI-assisted template selection and
   schema generation

This path gives Incept:

- immediate advertiser value
- low-risk MVP delivery
- reusable infrastructure
- a cleaner bridge between image, video, and future playable production
