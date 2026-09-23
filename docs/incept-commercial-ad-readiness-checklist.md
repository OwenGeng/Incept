# Commercial Ad Readiness Checklist

## Purpose

This is the single release checklist for a guided Incept commercial. It is
deliberately stage-based: a failure is shown at the stage that introduced it,
not deferred until `Lock script`, Design, or final rendering. A production can
move forward only when all **BLOCKER** checks in its current stage pass.

Use this document for today's first end-to-end ad. Do not add unrelated
features or change model/API configuration while running it. Record warnings,
but resolve blockers before moving on.

## Rule of ownership

| Stage | Owner | Canonical output | Next stage may trust |
| --- | --- | --- | --- |
| Direction | Creative Strategist | Creative Contract + Asset Contract | A typed, source-grounded creative world and reusable asset inventory |
| Script | Senior Screenwriter | Timed Script with scene bindings | Only approved Asset Contract keys, one idea per beat |
| Design | Production Designer | Design Bible + Asset Packs | One reusable AI state per required contract key |
| Storyboard | Director | Shot list + keyframe/video prompts | Locked script and selected design states |
| Generate | Image/Video generation | Candidate images and video takes | Approved keyframes and shot prompts |
| Edit | Editor | Ordered cut, audio, captions, CTA | Selected takes plus final brand/claim checks |
| Deliver | QA/Delivery | Final MP4 + delivery manifest | A complete, approved, compliant cut |

No stage may invent a principal character, setting, prop, UI state, brand
claim, or cultural context that the preceding contract does not declare.

---

## 0. Production setup

**BLOCKER**

- [ ] One current creative reference is marked `reference`; own logo/product/UI
  assets are marked `brand`, never mixed together.
- [ ] Brief states product, audience, market/cultural context, offer/claim,
  duration (15/30/60s), aspect ratio, resolution, and output language.
- [ ] Reference material is used for transferable craft, not exact likeness,
  copy, logo, costume, footage, or composition.
- [ ] The target ad has a concrete CTA and required legal/disclaimer copy.

**Warning**

- [ ] Missing logo, store badge, product UI capture, or end-card copy is listed
  as a required brand asset before Design begins.

**Pass condition:** the brief can be read without watching the reference.

## 1. Direction — Creative Strategist

**BLOCKER: validate immediately after the Strategist run**

- [ ] Output language follows the latest user brief, not the language spoken in
  the reference.
- [ ] Creative Contract parses as typed JSON; it has a concept, core promise,
  story beats, originality guardrails, risks, and recurring character records
  where people/mascots appear.
- [ ] Every recurring character has a unique `character_key`, cultural context,
  identity/wardrobe/performance guidance, continuity lock, and original
  reference boundary.
- [ ] Asset Contract parses as typed JSON and has unique keys. `source_strategy`
  is only `original_prompt`, `brand_asset`, or `reference_frame_guidance`.
- [ ] Each recurring character, reusable environment, hero prop, game/UI state,
  and CTA/end-card has exactly one Asset Contract item. No duplicate entity
  under a second source mode.
- [ ] Every Contract key is traceable to either the brief, a reference insight,
  or a supplied brand asset. No generic Western/other-market replacement is
  introduced when the intended cultural setting is Korean (or vice versa).

**Warning**

- [ ] 5–8 reusable assets is a sensible default for a 30-second commercial;
  consolidate cosmetic variants rather than creating duplicate packs.
- [ ] Direction report contains three reference-frame purposes: hook, mechanism,
  and CTA/end-card.

**Stop if failed:** rerun/revise Creative Direction only. Do not draft Script.

## 2. Script — Senior Screenwriter

**BLOCKER: validate before `Lock script`**

- [ ] Total beat duration equals target duration; individual beats are 3–5
  seconds and each communicates one visual idea.
- [ ] Every scene has at least one explicit binding:
  `character_keys`, `environment_key`, `prop_keys`, or `ui_keys`.
- [ ] Every bound key exists in the current Asset Contract; there are no raw
  names such as “Friend A” in place of `char_friend_a`.
- [ ] Live-action scenes retain the Direction's declared cultural context,
  relationship roles, wardrobe/identity continuity, and product mechanism.
- [ ] The CTA scene binds the logo/store/CTA UI asset key and uses only approved
  claims/copy.
- [ ] Dialogue, on-screen copy, and captions use the requested output language.

**Warning**

- [ ] Every scene has a plain-language purpose, action, audio cue, and
  production-friendly setting. Technical generation prompts do not dominate
  the reader-facing script view.

**Stop if failed:** revise Script only. Never “fix” missing bindings in Design
by inventing a new pack.

## 3. Design — Production Designer

**BLOCKER: validate before `Approve design & create storyboard`**

- [ ] Each required Asset Contract key maps to one, and only one, Asset Pack.
- [ ] Every AI performer is a Character Pack, including live-action-style
  people. Character packs lock identity, cultural context, hair, wardrobe,
  body/accessories, and performance against a neutral identity-board backdrop.
- [ ] Environment packs contain no people; character packs do not use final
  location backgrounds as their identity board.
- [ ] Props, UI/end cards, mascot, and environments are separate only when each
  is reused; no redundant source-mode duplicates exist.
- [ ] Every required pack is either `ready` with a selected A/B/C/D state or is
  visibly blocked/failed with a recovery instruction. Nothing required remains
  silently `draft`.
- [ ] Selected pack states satisfy the Script's setting, character and prop/UI
  bindings.

**Warning**

- [ ] 2×2 sheets are review material only. The selected individual panel—not
  the contact sheet—is the downstream keyframe reference.

**Stop if failed:** revise the failing pack/prompt only; preserve approved packs.

## 4. Storyboard — Director

**BLOCKER: validate before generating any video**

- [ ] Every shot points to a Script scene ID and has start time/duration that
  covers the full commercial without accidental gaps or overlaps.
- [ ] Each shot has one goal, one readable visual idea, action, camera,
  continuity note, audio cue, keyframe intent, and video prompt.
- [ ] Every character/environment/prop/UI state referenced by a shot is an
  approved individual Design state.
- [ ] Adjacent shots declare continuity for identity, wardrobe, lighting, hero
  prop state, UI state, and transition where relevant.
- [ ] Mobile 9:16 shots reserve safe areas; CTA and subtitle regions are not
  obscured by platform UI.

**Stop if failed:** revise the affected shot card or binding, not the whole
script.

## 5. Generate — Keyframes and video takes

**BLOCKER per shot**

- [ ] Required design states are approved and the selected panel is used as the
  keyframe/reference, never the four-panel sheet.
- [ ] Image candidate review uses A/B/C/D; one candidate is explicitly selected
  before it becomes the shot keyframe.
- [ ] Video generation prompt retains only this shot's approved characters,
  location, props/UI, action, camera, and continuity constraints.
- [ ] Video take is reviewed for identity drift, unwanted text/logo, cultural
  mismatch, contact-sheet artifacts, wrong aspect ratio, unsafe copy, and
  broken action before selection.
- [ ] Every storyboard shot has one selected take or is deliberately marked
  omitted/replaced.

**Warning**

- [ ] Regenerate only the failed shot; do not regenerate approved global packs
  because one take is weak.

## 6. Edit — final cut

**BLOCKER**

- [ ] Selected takes are in storyboard order and duration meets the target.
- [ ] No edit breaks character/prop/environment continuity across adjacent
  shots.
- [ ] Voice, music, SFX, captions, and CTA remain intelligible on mobile.
- [ ] Captions, offer, product claim, disclaimer, logo, and store badges are
  correct and remain within safe areas.
- [ ] First three seconds establish the intended hook; final three seconds make
  the next action unambiguous.

## 7. Deliver — final QA

**BLOCKER**

- [ ] Final format, aspect ratio, resolution, duration, audio, and file type
  match Production Contract.
- [ ] No stale required state, failed required pack, missing selected keyframe,
  or missing selected take remains.
- [ ] Final export contains no unapproved third-party logo, reference footage,
  copied likeness, placeholder copy, contact sheet, or debug text.
- [ ] Delivery manifest records production revision, selected pack panels,
  selected takes, asset provenance, copy/disclaimer version, and final asset
  ID.

---

## Today's 30-second commercial runbook

1. Create one new production. Attach one reference video and only the brand
   assets needed today. Fill the setup checklist completely.
2. Run Direction. Inspect the typed Contract gate before opening Script. If it
   fails, repair Direction; do not continue.
3. Run Script. Verify all scene bindings before locking. Lock only after the
   Script gate is fully green.
4. Generate and approve only the required Design packs. Start with recurring
   characters, environment, hero prop, UI/CTA, and mascot only if used.
5. Create storyboard. Review first/last shot and one middle shot before
   generating all keyframes.
6. Generate one test shot first. If identity/visual style holds, generate the
   remaining shots; otherwise fix the one failing pack or shot prompt.
7. Select takes, assemble the cut, run Delivery QA, and export.

## Non-negotiable stop rule

When a check fails, correct the owning stage and rerun only its downstream
dependents. Do not patch a later stage to hide an upstream contract failure.
