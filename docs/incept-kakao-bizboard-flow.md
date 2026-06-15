# Incept Kakao Bizboard Flow

## Scope

This document only covers `Kakao Bizboard 1029x258`.

Do not use this flow for:

- Native Display
- Native List
- generic Kakao image generation

## Product Goal

After `Kakao Clean` succeeds, the cleaned image becomes the source for the fixed Bizboard thumbnail area.

The final creative is not AI-laid-out. It is assembled through a locked Bizboard template:

1. cleaned image
2. app icon
3. main copy
4. app download copy
5. AD mark
6. DSP disclosure
7. optional gacha disclosure

## Current Incept Flow

### Step 1. Upload

User uploads one or more source creatives.

### Step 2. Clean

Backend Kakao clean removes:

- text
- logos
- UI overlays

Output of this step is a cleaned image asset stored in project history.

### Step 3. Confirm

User accepts or rejects each cleaned result.

Only accepted cleaned assets continue to composition.

### Step 4. Bizboard Compose

User fills fixed Bizboard fields:

- `App Icon`
- `Main Copy`
- `App Download Copy`
- `DSP Name`
- `Gacha toggle`

The system then generates a fixed `1029x258` transparent PNG.

### Step 5. Save

The composed Bizboard is uploaded back into Library as a generated asset.

## Template Rules Implemented In Code

Source files:

- `/Users/owen.geng/Documents/Projects/Incept/apps/web/components/incept/KakaoFlow.tsx`
- `/Users/owen.geng/Documents/Projects/Incept/apps/web/lib/kakao-compositor.ts`

## Canvas

- Width: `1029`
- Height: `258`
- Output: transparent `PNG`

## Safe Margins

- Left safe margin: `48px`
- Right safe margin: `48px`

## Thumbnail Slot

The cleaned image is placed into the right-side thumbnail slot.

- Slot size: `315 x 186`
- Slot Y: `36`
- Slot X: `1029 - 48 - 315 = 666`
- Insertion mode: center crop

The cleaned image is never stretched.

## Left Text Zone

The left content zone is locked and must not overlap with the thumbnail.

Derived width:

- `LEFT_ZONE_W = THUMB_X - SAFE_L - 24`

This is used to block text from colliding with the thumbnail area.

## Main Copy

Rules currently enforced:

- required
- rendered at `48px`
- measured before output
- must be at least `290px` wide
- must not exceed `585px` wide
- must not overlap the thumbnail zone

If it fails these rules, compose is blocked.

## App Download Copy

Rules currently enforced:

- required
- rendered at `26px`
- must include `앱`
- must end with `>`
- must fit the fixed slot
- emoji is rejected

Default value:

- `앱에서 확인 >`

## DSP Disclosure

Rules currently enforced:

- DSP name required
- final disclosure line must fit the fixed slot
- emoji is rejected

Output line:

- default: `{DSP_NAME} 광고입니다.`
- gacha mode: `{DSP_NAME} 광고 · 확률형 아이템 포함`

## App Icon

Rules currently enforced:

- required
- displayed as `38 x 38`
- fixed slot

Current implementation uses a rounded clipping path for preview/composition.

If Kakao review requires stricter square-corner behavior later, change only the icon clipping in `kakao-compositor.ts`.

## Preview Behavior

In the metadata step:

- first accepted cleaned asset is used for live preview
- preview is only shown when validation passes
- if validation fails, preview is suppressed and error messages are shown

## Validation Behavior

Current validation runs in:

- `validateKakaoBizboardInputs()`

Current checks:

- cleaned thumbnail exists
- app icon exists
- main copy exists
- app download copy exists
- DSP name exists
- main copy width is within allowed range
- main copy does not collide with thumbnail zone
- app download copy contains `앱`
- app download copy ends with `>`
- app download copy fits slot
- DSP disclosure fits slot
- no emoji in restricted text fields

## Output Naming

Each composed file is uploaded with the pattern:

- `{source_name}_kakao_bizboard_1029x258.png`

## Remaining Follow-Up Work

The current flow is much closer to a real Bizboard pipeline, but a few things are still worth tightening later:

1. Add stricter character filtering for Kakao-safe symbols.
2. Add square-corner icon mode if Kakao rejects rounded icon treatment.
3. Add source-image OCR check to ensure cleaned thumbnail is truly text-free before compose.
4. Add final file-size validation against Kakao limits.
5. Move client-side composition to backend if we want deterministic server-rendered output.

## Key Principle

For Kakao Bizboard, the cleaned image is only the thumbnail source.

The final asset should always come from:

- cleaned image
- locked geometry
- locked typography slots
- locked disclosure logic

This must remain a deterministic template system, not a freeform image generation workflow.
