# Incept Commercial Video Production Reference

> Updated: 2026-07-14  
> Purpose: turn Incept video generation from a sequence of model calls into a
> reviewable, deterministic production pipeline capable of delivering paid-media
> creative.

## Scope and decision

This document is a product and engineering reference for the Video workbench.
It draws patterns from [OpenMontage](https://github.com/calesthio/OpenMontage)
and [Remotion](https://github.com/remotion-dev/remotion), but does **not** copy
their code, assets, or licenses. In particular, OpenMontage is AGPL-3.0 and
must be treated as architectural inspiration only. Remotion licensing must be
reviewed before adopting it in a commercial deployment.

The target is not merely an attractive AI clip. The target is a complete,
brand-safe, technically valid ad asset with a deliberate hook, product proof,
payoff, and CTA.

## Current sample diagnosis

The reviewed sample `mpath178_xeoeuam_ipqzxgbk1mueioui_video1.mp4` is a
15-second, 720x1280, 24fps H.264 video. Its sampled frames show a material
continuity failure:

- The opening and the middle show an overhead pile of pig, cash, and gem
  objects.
- Other moments abruptly switch to a royal jewel match-board with a different
  camera, interaction model, and UI.
- The closing returns to the match-board instead of resolving a single story.

This is not primarily a rendering-resolution problem. It is a production-plan
problem: independently generated or extended clips are being treated as a
finished ad without a beat plan, state handoff, continuity review, or
deterministic final composition.

### Root causes to avoid

1. **One generic prompt for every segment.** A repeated broad prompt asks the
   model to invent the same concept again, not to advance the previous action.
2. **No explicit shot state.** The next segment has no machine-readable record
   of the prior segment's last camera, scene, UI state, objects, or action.
3. **Raw concatenation is presented as storytelling.** A clean MP4 join does
   not make two different generated scenes feel continuous.
4. **AI is asked to redraw deterministic assets.** Logos, score UI, CTA copy,
   legal text, and end cards should not be regenerated in every video segment.
5. **No creative quality gate before delivery.** There is no stop condition for
   visual jumps, repeated shots, missing product proof, lost copy, or an
   unsuitable final CTA.

## What to learn from OpenMontage

OpenMontage's useful idea is a **production pipeline**, not a larger prompt.
It starts from reference-video analysis, converts the result into a grounded
plan, produces options and costs before generation, and makes clear what will
be kept versus changed. Its Backlot concept uses a living storyboard and
approval gates so that a user reviews shots before final render. It also
performs multi-point validation through media metadata and sampled frames.

Incept should adopt these principles:

| OpenMontage pattern | Incept adaptation |
| --- | --- |
| Reference-video analysis | Analyze source/reference assets into pacing, visual language, hook, gameplay mechanic, and CTA requirements. |
| Production plan before generation | Create a structured `CommercialVideoPlan`, not a free-form prompt. |
| Scene contact sheet and approval gate | Show 3-4 planned beat cards and let the user approve or revise before spending Veo budget. |
| Per-shot prompt, cost, and quality trace | Store a prompt manifest, source assets, generated takes, cost estimate, and QC result in the thread. |
| Self-review before delivery | Require technical and visual checks before an asset receives a delivery-ready state. |

Useful OpenMontage references:

- [Reference-video planning and keep/change decisions](https://github.com/calesthio/OpenMontage#start-from-a-video-you-already-love)
- [Backlot storyboard and approval gates](https://github.com/calesthio/OpenMontage#watch-it-happen--the-backlot-living-storyboard)
- [Multi-point media self-review](https://github.com/calesthio/OpenMontage#quick-start)

## What to learn from Remotion

Remotion's valuable role is **deterministic composition**, not generative
gameplay. React code and data can define reusable video compositions and render
them programmatically. That makes it a strong candidate for the parts that
must be pixel-accurate:

- logo lockups and app icons
- text, disclosures, subtitles, and CTA buttons
- safe-zone placement
- fixed end cards
- repeatable transitions and overlays
- music/SFX placement after generation
- multi-size exports from the same project data

Incept should use an equivalent deterministic compositor. Remotion is one
option; an FFmpeg/HTML renderer can cover a smaller initial scope. The
important architectural decision is that these layers are **not** redrawn by
Veo for every segment.

Useful Remotion references:

- [Programmatic video and automation overview](https://github.com/remotion-dev/remotion)
- [Composition model](https://www.remotion.dev/docs/composition)
- [Rendering, server-side rendering, and Cloud Run documentation](https://www.remotion.dev/docs/)

## Target Incept production architecture

```text
User brief + source assets + reference assets
                 |
                 v
Gemini 3.5 Flash production planner
  - objective, audience, format, duration
  - brand locks and prohibited changes
  - hook / demo / payoff / CTA beat plan
  - required assets and missing-asset list
                 |
                 v
User review and approval of CommercialVideoPlan
                 |
                 v
Per-beat generation plan
  - source frame / style lock strategy
  - one unique Veo Fast brief per beat
  - expected starting and ending state
                 |
                 v
Veo 3.1 Fast motion plates + take QC
                 |
                 v
Deterministic composition
  - brand UI, CTA, legal copy, overlays, transitions, audio
                 |
                 v
Delivery QC -> MP4 + poster + prompt manifest + review record
```

### Required persisted artifacts

Every commercial video project should retain:

```text
commercial_video_plan.json
shot_plan.json
prompt_manifest.json
source_asset_manifest.json
takes/shot-01-take-01.mp4
takes/shot-02-take-01.mp4
review/qc.json
deliverables/final.mp4
deliverables/poster.jpg
```

This solves two product issues at once: users can see why a video was made a
certain way, and a failed beat can be regenerated without losing the rest of
the production.

## 15-second mobile-ad blueprint

For a 9:16 game ad, do not ask the model to create a vague 15-second gameplay
clip. Use a sequence with different jobs for every beat:

| Time | Beat | Generation/composition responsibility |
| --- | --- | --- |
| 0.0-2.0s | Hook | One legible game problem, product/game UI already visible. |
| 2.0-6.5s | Interaction proof | A single understandable interaction: tap, drag, match, merge, or pull. |
| 6.5-10.5s | Escalation | The first action resolves and triggers a distinct reward or larger puzzle state. |
| 10.5-12.5s | Payoff | Reward, score, or before/after outcome. Preserve the same scene language. |
| 12.5-15.0s | CTA/end card | Deterministic branded end card, CTA, logo, and disclosure rather than a newly generated scene. |

### How to generate a 15-second Veo sequence

Veo Fast has short discrete generation durations. A 15-second ad must therefore
be a controlled sequence, not two similar full-video requests:

1. Generate an initial 6-8 second **hook plus interaction** plate.
2. Review the final second of the selected take. Persist a `continuity_state`:
   camera, scene, subject placement, visible UI, action state, palette, and
   reward state.
3. Use the next request only for the **next beat**. Its prompt must begin from
   that saved state and specify a different outcome. Never repeat the entire
   master brief unchanged.
4. Sample the boundary before accepting it. If the second clip changes the
   camera, game, UI, or subject identity, reject only that extension and retry.
5. Trim the assembled motion plates to the planned duration, then compose the
   deterministic final CTA/end-card layer.

If the user supplies a source image and separate reference images, respect the
model's input constraints: use exactly the allowed conditioning mode for that
request. Do not send an image-to-video source and reference images together
when the API rejects that combination. A planning step may instead create a
single approved source/keyframe or use style direction in the prompt.

## CommercialVideoPlan schema

The planner should turn chat into a concrete, reviewable object. A minimal
shape is:

```json
{
  "objective": "Show a satisfying match mechanic and drive installation.",
  "format": {"aspect_ratio": "9:16", "duration_seconds": 15, "fps": 24},
  "brand_locks": ["logo", "game UI", "CTA copy", "palette"],
  "beats": [
    {
      "id": "hook",
      "range_seconds": [0, 2],
      "purpose": "Show the blocked board and goal.",
      "start_state": "Board has three visible orange pieces.",
      "end_state": "Cursor is about to tap the matching pair.",
      "veo_brief": "..."
    }
  ],
  "deterministic_overlay": {
    "end_card": true,
    "cta": "Install now",
    "safe_zone": "mobile-bottom"
  },
  "missing_assets": [],
  "acceptance_checks": ["single game world", "CTA legible", "no jump cut"]
}
```

The UI should display this as brief beat cards, not as a raw JSON document.
The raw artifact remains attached to the run for reproducibility.

## Prompt compiler rules

The prompt sent to Veo should be a short, beat-specific production brief. It
should not contain every instruction from the entire chat history.

Each brief must define:

1. **Continuity lock:** exact scene, camera, main objects, UI state, and
   rendering style that must persist from the prior beat.
2. **One action:** one clear user interaction or cinematic action.
3. **One result:** the exact state at the end of the beat.
4. **Camera discipline:** no unsolicited camera change, no scene replacement,
   no new game genre, no brand/UI redraw.
5. **Negative controls:** no duplicate scenes, no unrelated reward sequence,
   no text mutation, no illegible CTA.

Example outline for a match game:

```text
Continue the exact same top-down mobile match board from the approved previous
clip. Keep the same warm gold UI, gem grid, crown goal, camera position, and
board layout. A finger cursor taps the two matching orange pieces; both slide
into the tray, merge with a crisp visual pop, and the remaining-object counter
changes from 12 to 10. Keep the board visible throughout. End with the cleared
space and the counter at 10, ready for the next interaction. Do not cut to a
different game, a pile of objects, a reward room, or a new camera angle.
```

## Delivery quality gates

No output should be labeled delivery-ready until it passes all relevant gates.

### Technical

- correct aspect ratio, resolution, frame rate, codec, and target duration
- no black frames, invalid audio track, corrupt media, or frozen long tail
- poster frame generated
- source/take/final lineage retained in the thread

### Continuity

- sample frames at each shot boundary plus 25%, 50%, 75%, and final frame
- detect camera/scene/subject discontinuity between the previous ending and
  next opening
- require an explicit reviewer override if a hard cut is intentional
- reject visually duplicated beats that do not advance the planned action

### Brand and paid-media readiness

- locked logo and CTA are legible and inside safe zones
- source brand copy is exact; generated text is not trusted for final legal or
  CTA layers
- primary product action is understandable without sound
- end card persists long enough to be actionable
- required disclosure and destination CTA are deterministic overlays

### Human review

The user should see a compact contact sheet with each beat, selected take,
prompt, duration, cost, and QC state. Regeneration must be scoped to one beat,
not force a full re-render.

## Engineering priorities for Incept

### P0: Replace raw sequence concatenation

- Introduce `CommercialVideoPlan` and `ShotPlan` artifacts.
- Assign each generated or extended segment to one beat.
- Give every extension a beat-specific prompt and a captured continuity state.
- Add a boundary-frame QC pass before concatenation.
- Do not ship a video that fails boundary continuity checks.

### P1: Add deterministic finishing

- Build a small React/Remotion or HTML/FFmpeg composition service.
- Keep logo, product UI, CTA, legal copy, subtitles, and end cards outside the
  generative model.
- Support exact 9:16, 16:9, and square deliverables from the same plan.

### P2: Build the production review surface

- Convert the current chat plan into an editable beat storyboard.
- Show selected sources and reference assets only in the originating message;
  persist them as thread context, not as repeated attachments.
- Show generation progress per beat: queued, generating, continuity review,
  composing, QC, ready.
- Attach the exact per-beat Veo brief to each generated result.

### P3: Build reusable commercial primitives

- Make end card, CTA, product logo, subtitles, safe-zone guides, and sound
  cue timing reusable components.
- Create vertical game-ad templates: match/merge, runner, pull-pin, reward
  reveal, and app-demo.
- Keep gameplay-specific motion plates separate from reusable paid-media UI.

## Definition of success

Incept has reached the commercial-video bar when a user can:

1. Upload a source/reference set and explain the campaign in chat.
2. Approve a concise beat plan before generation spend starts.
3. Generate a 15-second sequence whose beats advance one coherent game or
   product story.
4. Re-render only a failed beat.
5. Receive a deterministic final MP4 with a correct CTA/end card, auditable
   prompt/take lineage, and automated delivery checks.

At that point, Veo is a high-value motion-plate provider inside a production
system, rather than the system itself.
