"""Prompt construction for direct per-size creative generation."""

from __future__ import annotations

from app.layout_prompt_rules import build_layout_prompt_rule, layout_family_for_size


def _size_category(size: str) -> str:
    """Return a human-readable category for a WxH size string."""
    try:
        width, height = (int(x) for x in size.lower().split("x"))
    except ValueError:
        return "unknown"
    ratio = width / height
    if ratio >= 4.0:
        return "strip"
    if ratio >= 1.6:
        return "wide"
    if ratio >= 0.9:
        return "square"
    return "tall"


def get_composition_rule(size: str) -> str:
    return build_layout_prompt_rule(size)


def build_no_ocr_reference_resize_guardrail(target_size: str) -> str:
    """
    Temporary guardrail for source-image resize before OCR/Gemini anchors exist.

    This does not guarantee production-safe layout, but it gives the image model
    the clearest possible instruction: preserve the source creative inventory and
    re-layout it for one target size instead of cropping or redesigning it.
    """
    return f"""
SOURCE IMAGE RESIZE GUARDRAIL - no OCR or anchor detection available yet:
- Treat the attached image as the source creative inventory.
- Preserve all visible original content as much as possible: logo, CTA button, headline/text block, characters, products, foreground objects, background setting, brand colors, and visual style.
- This is NOT a crop. This is a layout adaptation.
- Do not simply zoom into the source image. Do not cut off the logo, CTA, character head/face, product, or headline.
- Re-layout the source creative for {target_size}: scale elements down, reposition them, simplify spacing, and rebalance the composition so the important content fits the canvas.
- Keep the same advertising message unless the user explicitly asks to change it.
- The logo and CTA must remain fully visible and readable when they exist in the source creative.
- Logo and CTA should be smaller supporting elements, not oversized posters. Follow the target-size logo/CTA proportion rules.
- Use exactly one primary logo and exactly one primary CTA when they exist in the source creative.
- Do not keep one copy from the source and also generate another copy. Choose one clean, complete placement for each.
- Do not show partial, cropped, ghosted, or overlapping duplicate copies of logo text, CTA text, or button shapes.
- If the target is very narrow, compress the scene horizontally, use a left-to-right arrangement, and simplify background detail before dropping any important brand element.
- If not every tiny background detail can fit, preserve identity-critical elements first: logo, CTA, headline/main text, main character/product, and recognizable background style.
- Do not create a new unrelated ad, new logo, new CTA wording, or new character identity.
""".strip()


def build_generation_prompt(
    user_request: str,
    target_size: str,
    style_hint: str | None = None,
    preserve_elements: list[str] | None = None,
) -> str:
    """Build a simple direct-generation prompt for one target size."""
    composition = get_composition_rule(target_size)
    family = layout_family_for_size(target_size)
    style_line = f"Keep the same art style, background world, color palette, and brand identity: {style_hint}" if style_hint else "Keep the same art style, background world, color palette, and brand identity."
    preserve_line = (
        f"Keep these important elements when they are part of the creative: {', '.join(preserve_elements)}."
        if preserve_elements
        else "Keep the important brand and scene elements that define the ad."
    )
    family_line = _direct_family_instruction(target_size, family)

    return f"""
{user_request}

Adapt this into exactly one final advertisement image at {target_size}.

{style_line}
{preserve_line}
{family_line}

Additional direction:
{composition}

Strict requirements:
- Create exactly one final image for this size only.
- Do not create a contact sheet, collage, before/after, or multi-size layout.
- Recompose the ad for {target_size}; do not simply crop the source.
- Keep the background style and creative direction consistent.
- Keep brand elements readable and fully visible when they exist.
- Do not duplicate logos, CTA buttons, or headline text.
- Do not add extra words, labels, watermarks, borders, UI chrome, or size text.
""".strip()


def build_reference_generation_prompt(
    user_request: str,
    target_size: str,
    style_hint: str | None = None,
    preserve_elements: list[str] | None = None,
) -> str:
    """Build a simple direct adaptation prompt for one target size using references."""
    family = layout_family_for_size(target_size)
    family_line = _direct_family_instruction(target_size, family)
    style_line = f"Keep the same style and identity as the uploaded image reference(s): {style_hint}" if style_hint else "Keep the same style and identity as the uploaded image reference(s)."
    preserve_line = (
        f"Preserve these important source elements when present: {', '.join(preserve_elements)}."
        if preserve_elements
        else "Preserve the recognizable background, logo concept, CTA concept, main subject matter, and color palette from the source."
    )

    return f"""
Use the uploaded image reference(s) as the source creative.

{user_request}

Adapt the source creative into exactly one final ad at {target_size}.
{style_line}
{preserve_line}
{family_line}

Rules:
- Recompose the ad so it looks intentionally designed for {target_size}.
- Keep the background, world, mood, and overall visual style consistent with the source.
- Do not output the reference image itself, any contact sheet, or any comparison layout.
- Do not generate multiple versions inside one image.
- Do not duplicate logos, CTA buttons, or headline text.
- Keep important brand elements fully visible and inside the canvas.
- Do not add extra words, labels, watermarks, or size text.
""".strip()


def _direct_family_instruction(target_size: str, family: str) -> str:
    if family == "narrow_banner":
        return (
            f"For this very wide banner ({target_size}), redesign the composition as a real banner: "
            "clean readable layout, preserve the same background style, keep the logo fully visible, "
            "keep the CTA fully visible, and make the banner feel intentionally designed for this aspect ratio."
        )
    if family == "portrait":
        return (
            f"For this vertical format ({target_size}), use a top-to-bottom composition with clear hierarchy "
            "and keep the main scene or product dominant."
        )
    if family == "compact_square":
        return (
            f"For this compact format ({target_size}), keep a balanced composition with a strong central scene "
            "and supporting brand elements."
        )
    return (
        f"For this landscape format ({target_size}), keep a broad scene, preserve background continuity, "
        "and rebalance the ad naturally for the target width."
    )


def build_contact_sheet_generation_prompt(
    user_request: str,
    target_sizes: list[str],
    style_hint: str | None = None,
    preserve_elements: list[str] | None = None,
    panel_layout: dict | None = None,
    has_reference: bool = False,
    sheet_family: str | None = None,
    sheet_title: str | None = None,
) -> str:
    """Build a fixed-template contact-sheet prompt for backend splitting."""
    from app.contact_sheet import CONTACT_SHEET_SIZE, compute_panel_layout

    sizes = [size.strip() for size in target_sizes if size.strip()]
    title = sheet_title or "Contact Sheet"
    if panel_layout is None:
        panel_layout = compute_panel_layout(sizes)

    style_line = f"Art style and brand identity: {style_hint}" if style_hint else ""
    preserve_line = (
        f"Must preserve in every panel: {', '.join(preserve_elements)}."
        if preserve_elements
        else "Preserve source logo, CTA button, headline/text block, main character/product, background setting, brand colors, and visual style in every panel."
    )
    if has_reference:
        reference_section = f"""
Use the attached image reference(s) as the source creative, not as images to place side-by-side.

REFERENCE ADAPTATION RULES (apply to EVERY panel):
- Preserve the source creative's main game or product identity, logo text, CTA text, major subject matter, color palette, and illustration style.
- Keep the same brand and advertising message unless the user's request explicitly changes it.
- Recompose the source creative inside each panel for that panel's shape. Do NOT invent an unrelated ad.
- Never include the original reference as a thumbnail, inset, comparison, or layout preview.

{build_no_ocr_reference_resize_guardrail("each panel")}
""".strip()
    else:
        reference_section = (
            "Create original ad artwork for each panel based on the brief below. "
            "Keep visual identity, color palette, and brand elements consistent across all panels."
        )

    panel_lines: list[str] = []
    strip_sizes: list[str] = []
    for idx, size in enumerate(sizes):
        box = panel_layout.get(size)
        category = _size_category(size)
        if category == "strip":
            strip_sizes.append(size)
        if box:
            x1, y1, x2, y2 = box
            box_w, box_h = x2 - x1, y2 - y1
            shape_hint = (
                f" — ultra-wide horizontal strip, {box_w}px wide × {box_h}px tall"
                if category == "strip"
                else f" — {box_w}×{box_h}px on canvas"
            )
            panel_lines.append(
                f"- Panel {idx + 1} ({size}, {category}){shape_hint}: "
                f"exact black-bordered rectangle from ({x1},{y1}) to ({x2},{y2}). "
                f"This rectangle is FIXED — do not move, resize, or swap it."
            )
        else:
            panel_lines.append(
                f"- Panel {idx + 1} ({size}): one black-bordered rectangle with the correct aspect ratio."
            )
    panel_plan = "\n".join(panel_lines)
    strip_hierarchy = ", ".join(strip_sizes) if strip_sizes else "banners"

    return f"""
{user_request}

{reference_section}

{preserve_line}
{style_line}

OUTPUT: one single {CONTACT_SHEET_SIZE} landscape contact sheet containing exactly {len(sizes)} ad panels on a plain pure white background.
SHEET TYPE: {title}

PANEL PLAN:
{panel_plan}

CONTACT SHEET STRUCTURE - critical for backend extraction:
- Each panel must be a separate rectangle with a thin solid black border.
- Leave generous pure white gutters between panels.
- Do not overlap panels.
- Do not rotate panels.
- CRITICAL: Do NOT write any text, numbers, dimension labels (such as "320x50", "728x90", "1200x628"), size annotations, pixel counts, captions, watermarks, rulers, or UI chrome anywhere in the image — not inside panels, not in gutters, not at panel corners. The output must contain ONLY ad artwork and white background. Any dimension text will corrupt the deliverable.
- The inside of each black border must contain only the finished ad artwork for that panel.
- Render only the requested panels above. Do not add extra panels, duplicate panels, or alternate versions.
- Respect the exact rectangle positions and proportions above.
- Treat the listed rectangles as a fixed reusable template. Keep every requested size in its designated position every time.
- Do not swap the positions of two requested sizes.
- Do not visually enlarge a smaller requested size to make it compete with a larger one.
- All requested sizes must live on this single sheet only.

PANEL ART RULES:
- Each panel is a complete ad layout, not a crop of the original reference.
- Re-layout content to fit each panel's shape: scale, reposition, simplify spacing.
- Narrow or strip panels ({strip_hierarchy}): left-to-right, logo left, hero center, CTA right.
- Square, portrait, and medium-wide hero panels: logo near top, hero scene central, CTA in lower third.
- Exactly one logo and one CTA per panel. No duplicates, no partial cuts.
- Logo and CTA fully inside the panel with safe internal padding.
- Consistent art style, brand colors, and visual identity across all panels.

SELF-CHECK:
- Exactly {len(sizes)} black-bordered panels present and filled.
- No artwork bleeds outside its panel border.
- Zero dimension labels, size text, or annotations anywhere (not "320x50", not "728x90", not any size string).
- Logo and CTA fully visible in every panel.
- Every requested size stays inside its assigned rectangle and keeps the assigned fixed sheet position.
""".strip()


def build_edit_prompt(
    user_change_request: str,
    target_size: str,
    original_prompt: str | None = None,
    style_hint: str | None = None,
) -> str:
    """Build a prompt for an inpainting edit that preserves the rest of the image."""
    composition = get_composition_rule(target_size)
    context_line = (
        f"Original creative brief (what must be preserved): {original_prompt}"
        if original_prompt
        else ""
    )
    style_line = f"Art style to maintain: {style_hint}" if style_hint else ""

    return f"""
EDITING TASK - do NOT regenerate the entire scene.

What to change: {user_change_request}

{context_line}
{style_line}

PRESERVATION RULES (non-negotiable):
- Every element NOT mentioned in "What to change" must remain IDENTICAL: same position, same size, same color, same design.
- Do NOT alter character designs, facial expressions, or poses.
- Do NOT shift the overall composition or scene layout.
- Do NOT change the background unless explicitly asked.
- Do NOT add new elements unless explicitly asked.
- Maintain the exact same art style and color palette.

TARGET SIZE: {target_size}
COMPOSITION RULE: {composition}

If the requested change would make the image look unnatural, fill the removed area with a seamless background continuation that matches the surrounding context. Do NOT leave blank or grey spaces.
""".strip()


def build_multi_size_prompt(
    user_request: str,
    sizes: list[str],
    style_hint: str | None = None,
    preserve_elements: list[str] | None = None,
) -> dict[str, str]:
    """Build individual prompts for each size in a multi-size generation batch."""
    return {
        size: build_generation_prompt(
            user_request=user_request,
            target_size=size,
            style_hint=style_hint,
            preserve_elements=preserve_elements,
        )
        for size in sizes
    }


# ── Resize task prompts ───────────────────────────────────────────────────────
# Resize = "take this exact source image and adapt it to a different ad size".
# The non-negotiable rule: background, colors, art style, and visual identity
# must remain PIXEL-PERFECT IDENTICAL.  Only the layout adapts.

_RESIZE_ABSOLUTE_GUARDRAIL = """
RESIZE TASK — ABSOLUTE CONSTRAINTS (non-negotiable):
- The background scene, color palette, lighting, atmosphere, and art style must remain IDENTICAL to the source image.
- Characters, logo design, CTA button style, and brand identity must NOT change.
- Do NOT invent new visual elements. Do NOT redesign anything.
- Do NOT change the mood, colors, texture, or visual identity in any way.
- The ONLY permitted change is adapting the layout/composition to fit the target size and its mandatory element positions.
- If background space is insufficient for the new aspect ratio, extend it naturally by continuing existing edge textures and colors — never fill with solid color or invent new scenery.
- Do NOT shrink, distort, or warp any element.
""".strip()

_RESIZE_BANNER_LAYOUT = """
MANDATORY LAYOUT for this ultra-wide banner — left-to-right, no exceptions:
┌──────────┬─────────────────────────┬────────────────┐
│  LOGO    │    HERO SCENE / KEY     │    CTA BUTTON  │
│  (LEFT)  │    VISUAL (CENTER)      │    (RIGHT)     │
└──────────┴─────────────────────────┴────────────────┘

- LEFT (≈12-18% of width): Brand logo — exact original design, fully visible, not cropped.
- CENTER (≈60-70% of width): Compact excerpt of the hero scene, main character, or product from the source image.
- RIGHT (≈16-22% of width): CTA button — same wording and visual style as in the source (e.g. "PLAY NOW").
- All three elements must be on ONE horizontal line — no vertical stacking.
- Simplify the hero scene aggressively to fit — keep only the most recognizable element.
- No element may be partially cropped at any edge.
""".strip()

_RESIZE_WIDE_LANDSCAPE_LAYOUT = """
LAYOUT for wide landscape ({size}):
- This format has room for the full creative scene — preserve the main composition of the source as closely as possible.
- Logo: top-left or top-center area, same size and design as source.
- CTA: lower-center or lower-right, same visual style as source.
- Hero / character / scene: occupies the dominant canvas area.
- If the aspect ratio differs slightly, extend the background edges naturally (continue existing sky, ground, or environment textures from the edges of the source image).
- Aim for minimal relayout — keep the original spatial arrangement of elements.
""".strip()

_RESIZE_PORTRAIT_LAYOUT = """
MANDATORY LAYOUT for portrait ({size}) — top-to-bottom, no exceptions:
┌────────────────────────┐
│   LOGO  (TOP CENTER)   │  ← centered horizontally, ~18-25% canvas height
├────────────────────────┤
│   HERO SCENE / CHAR    │  ← 50-60% of canvas height, centered
│   (MIDDLE)             │
├────────────────────────┤
│   CTA (BOTTOM CENTER)  │  ← centered horizontally, ~12-16% canvas height
└────────────────────────┘

- Stack all elements VERTICALLY — no horizontal side-by-side arrangement.
- Logo at top with clear padding from the top edge.
- Main character or hero visual centered in the middle area.
- CTA button at the bottom with safe padding, fully inside canvas, not cropped.
- Background fills naturally behind the character from the source image.
""".strip()

_RESIZE_SQUARE_LAYOUT = """
LAYOUT for compact square/near-square ({size}):
┌────────────────────────┐
│   LOGO  (TOP ~20%)     │  ← near top, centered or upper-corner
├────────────────────────┤
│   HERO SCENE           │  ← dominant, 55-65% of canvas height
│   (MIDDLE)             │
├────────────────────────┤
│   CTA  (BOTTOM ~15%)   │  ← near bottom, centered, safe padding
└────────────────────────┘

- Logo and CTA must BOTH be fully visible and readable.
- Hero content is the visual focus — logo/CTA should not dominate.
- Background fills naturally from source image.
""".strip()

_RESIZE_ENDCARD_PORTRAIT_LAYOUT = """
MANDATORY LAYOUT for endcard portrait ({size}) — top-to-bottom:
┌────────────────────────┐
│   LOGO  (TOP CENTER)   │
├────────────────────────┤
│   HERO SCENE / CHAR    │
│   (MIDDLE)             │
├────────────────────────┤
│  [App Store] [G Play]  │  ← side by side, centered, equal size
├────────────────────────┤
│   CTA (BOTTOM CENTER)  │
└────────────────────────┘

- Apple App Store badge on the LEFT, Google Play badge on the RIGHT — same row, same size.
- Both badges fully visible, not cropped.
- CTA button below the badges at the bottom.
""".strip()

_RESIZE_ENDCARD_LANDSCAPE_LAYOUT = """
MANDATORY LAYOUT for endcard landscape (640x360) — left-to-right:
┌──────────┬─────────────────────┬────────────────┐
│  LOGO    │  [AppStore][GPlay]  │    CTA BUTTON  │
│  (LEFT)  │  side by side center│    (RIGHT)     │
└──────────┴─────────────────────┴────────────────┘

- Logo on the LEFT.
- App Store and Google Play badges centered side by side.
- CTA button on the RIGHT.
- Background and art style identical to source.
""".strip()

_RESIZE_ENDCARD_SQUARE_LAYOUT = _RESIZE_ENDCARD_PORTRAIT_LAYOUT  # same template


def _get_resize_layout(target_size: str, is_endcard: bool = False) -> str:
    """Return the mandatory layout instruction for a given target size."""
    from app.layout_prompt_rules import layout_family_for_size

    if is_endcard:
        if target_size == "640x360":
            return _RESIZE_ENDCARD_LANDSCAPE_LAYOUT.replace("{size}", target_size)
        return _RESIZE_ENDCARD_PORTRAIT_LAYOUT.replace("{size}", target_size)

    family = layout_family_for_size(target_size)

    if family == "narrow_banner":
        return _RESIZE_BANNER_LAYOUT

    if family == "wide_landscape":
        return _RESIZE_WIDE_LANDSCAPE_LAYOUT.replace("{size}", target_size)

    if family == "portrait":
        return _RESIZE_PORTRAIT_LAYOUT.replace("{size}", target_size)

    # compact_square (300x250, 720x720)
    return _RESIZE_SQUARE_LAYOUT.replace("{size}", target_size)


def build_resize_prompt(
    target_size: str,
    user_note: str = "",
    is_endcard: bool = False,
    preserve_elements: list[str] | None = None,
) -> str:
    """
    Build the complete prompt for a single-size Resize task.

    Resize = take source image exactly as-is, adapt only layout/composition
    to the target size.  Background and style are NEVER changed.

    Args:
        target_size:       e.g. "728x90", "320x480".
        user_note:         Optional extra instruction from the user (kept minimal).
        is_endcard:        True for endcard sizes (adds app store badge instructions).
        preserve_elements: Additional brand elements to call out explicitly.
    """
    layout = _get_resize_layout(target_size, is_endcard=is_endcard)
    preserve_line = (
        f"Additional elements to preserve from the source: {', '.join(preserve_elements)}."
        if preserve_elements else ""
    )
    note_line = f"User instruction: {user_note}" if user_note.strip() else ""

    return f"""
{_RESIZE_ABSOLUTE_GUARDRAIL}

TARGET SIZE: {target_size}

{layout}

{preserve_line}
{note_line}

FINAL SELF-CHECK:
- Background and art style are pixel-perfect identical to the source image.
- Logo is fully visible and not cropped.
- CTA is fully visible and not cropped.
- No element is stretched or distorted.
- Output is exactly {target_size} in composition (the model will produce it at the appropriate resolution).
""".strip()


def build_resize_prompts_for_sizes(
    target_sizes: list[str],
    user_note: str = "",
    endcard_sizes: frozenset[str] | None = None,
    preserve_elements: list[str] | None = None,
) -> dict[str, str]:
    """
    Build a dict of {size → resize_prompt} for all requested sizes.
    endcard_sizes: set of sizes that should use the endcard layout template.
    """
    from app.gif_generator import GIF_ALLOWED_SIZES  # endcard check

    _endcard = endcard_sizes or frozenset({"360x640", "480x480", "640x360"})
    return {
        size: build_resize_prompt(
            target_size=size,
            user_note=user_note,
            is_endcard=(size in _endcard),
            preserve_elements=preserve_elements,
        )
        for size in target_sizes
    }


def describe_reference_style(theme: str, provider: str, model: str) -> str:
    """
    Build a concise style description from asset metadata to include as context
    when the user says "based on the reference image".
    """
    parts = []
    if theme:
        parts.append(f"theme: {theme}")
    if provider == "openai":
        parts.append("bright, clean digital illustration style")
    elif provider == "gemini":
        parts.append("photorealistic or high-quality rendered style")
    return "; ".join(parts) if parts else "consistent with the reference image"
