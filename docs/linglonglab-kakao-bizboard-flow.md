# LinglongLab Kakao Bizboard Flow

## Scope

This document covers `Kakao Bizboard 960x300` only.

Do not use this flow for:

- Naver Smart Channel (still `1029x258`)
- Native Display
- Native List
- generic Kakao image generation

## Spec Status

- Kakao is moving Bizboard creatives from `1029x258` to `960x300`. The official release is **Oct 19, 2026**, and both sizes are served during a migration window whose end date is not published
  ([moloco/marvel2#82898](https://github.com/moloco/marvel2/pull/82898)).
- Moloco accepts `960x300` for Kakao only. Naver stays on `1029x258`, so a `960x300` image must never be used for Naver.
- LinglongLab produces `960x300` only. The old `1029x258` template flow was removed. If a `1029x258` Kakao creative is still needed during the migration window, it has to be produced outside this flow.

## Reference Implementation

Layout values mirror Moloco's official generator:

- `moloco/cloud-appbase`, `go/appbase/handlers/kakao_bizboard_v2.go`
- UI reference: `moloco/moloco-cloud-portal`, `MCKakaoBizboardImageGenerateDialogContentV2.tsx` (flag `KAKAO_BIZBOARD_IMAGE_GEN_V2`)

v2 draws on a blank canvas. There is no base image; `kakao-bizboard-template.png` belonged to the old `1029x258` flow.

A pixel comparison on 2026-10-07 found identical text and image geometry for all four templates when additional info is present. Intentional differences are listed under [Intentional differences](#intentional-differences-from-the-moloco-generator).

## Product Goal

After `Kakao Clean` succeeds, the cleaned image becomes the source for the fixed Bizboard image area. The final creative is not AI-laid-out. It is assembled deterministically from a locked template: image, app icon, copy lines, and optional additional info.

## Flow

1. **Upload** one or more source creatives (up to 10).
2. **Clean** removes text, logos, and UI overlays. The result is stored in project history as a cleaned asset.
3. **Confirm**: the user accepts or rejects each cleaned result. Only accepted results continue.
4. **Compose**: the user picks a template and fills the fields below.
5. **Save**: the PNG is uploaded to the Library as a generated asset named `{source_name}_kakao_bizboard_960x300.png`.

Composition runs on the backend (`POST /api/v1/kakao/compose-bizboard`). The browser only validates copy first, with the same Pretendard font, so errors show before a request is sent.

## Templates

| Template | App icon + app copy | Sub copy | Image slot |
|---|---|---|---|
| `APP_DOWNLOAD_ONE_LINE_COPY_THUMBNAIL` (default) | yes | no | thumbnail |
| `APP_DOWNLOAD_TWO_LINE_COPY_THUMBNAIL` | yes | yes | thumbnail |
| `TWO_LINE_COPY_THUMBNAIL` | no | yes | thumbnail |
| `APP_DOWNLOAD_ONE_LINE_COPY_OBJECT` | yes | no | object |

## Canvas and Geometry

- Canvas: `960x300`, transparent `PNG`, at most `300,000` bytes
- Text area right edge: `x = 569`
- Thumbnail slot: `(601, 39)` to `(921, 261)`, `320x222`, corner radius `18`, center-cropped (never stretched)
- Object slot: `314px` wide at `x = 603`, vertically centered
- App icon: `38x38` at `x = 45`
- App copy sits right of the icon at `x = 91`, followed by a chevron (`9px` gap, `10x18`)

Type (Pretendard): main copy Bold `46`, sub copy Regular `38`, app copy Regular `29`, additional info Regular `22`.
Colors: main `#191919`, sub and app copy `#696969`, additional info `#949494`.

Text baselines for each template are defined in `LAYOUTS` in `apps/api/app/routers/kakao.py`.

## Field Rules

Enforced by the backend (`validate_copy`) and mirrored in the browser (`validateKakaoBizboardInputs`):

- **Main copy**: required, must fit the text area, and at least `240px` wide for one-line templates.
- **Sub copy** (two-line templates): required, must fit, and cannot equal the main copy. For two-line templates, main or sub must be at least `240px` wide.
- **App copy** (app templates): required, must include `앱` or `App`, and must fit before the chevron. An app icon is required.
- **Additional info**: optional, must fit.
- **Gacha toggle**: prepends `확률형 아이템 포함` to the additional info.
- **Banned content** in any text field: emoji and the symbols Kakao rejects (`^^`, `:D`, `☞`, `☑`, `♨`, and similar).
- **Placeholders**: any field containing `APP_NAME` is rejected. The UI pre-fills `APP_NAME 앱에서 확인` and `APP_NAME 출시`, and users must replace them with real copy.
- **Object images** must have a transparent background and be at least `219px` wide after trimming.
- **Output size**: if the PNG exceeds `300,000` bytes the request fails and the user must use a simpler image.

Text that is too long is rejected with an error instead of being clipped.

## Intentional Differences From the Moloco Generator

These follow Kakao's Oct 2026 PSD and guideline, not the Moloco generator:

| Case | Moloco generator | LinglongLab |
|---|---|---|
| No additional info | Text stays where it is and the bottom line is left empty | The text block is vertically re-centered (about `20px` lower) |
| Object image with transparent padding | Scales the whole canvas to `314px` wide | Trims transparent padding first, then scales |
| Transparent thumbnail | Transparent areas stay transparent | Flattened onto white, because Kakao rejects transparent thumbnails |
| Over-long copy | Clipped silently | Rejected with an error |

Outputs for a Bizboard with additional info and a thumbnail template are pixel-equivalent apart from font anti-aliasing.

## Input Handling

- Sources can be a data URL, an uploaded asset, a `/static/` file, or an HTTPS URL.
- Remote URLs must use HTTPS, may not carry credentials, may not redirect, and must resolve to public addresses.
- Source images are limited to `10 MB` and `40,000,000` pixels.

## Key Principle

For Kakao Bizboard, the cleaned image is only the image source. The final asset always comes from the cleaned image, locked geometry, locked typography slots, and the disclosure logic. This must remain a deterministic template system, not a freeform image generation workflow.

## Tests

`apps/api/tests/test_kakao_bizboard.py` covers rendering for all templates, the recentered layout, rounded corners, the gacha notice, copy validation (including the `APP_NAME` guard), object handling, and remote image safety.
