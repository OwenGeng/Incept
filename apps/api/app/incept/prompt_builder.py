"""Prompt construction for direct per-size creative generation."""

from __future__ import annotations

from app.incept.layout_prompt_rules import build_layout_prompt_rule, layout_family_for_size


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


def build_theme_create_style_modify_prompt(
    *,
    style_name: str,
    style_details: str,
) -> str:
    return f"""You are an expert AI image modifier. Your task is to transform the artistic style of [Image 1] while strictly preserving its original structural layout, camera perspective, and object composition.

Instructions:
1. Analyze the composition, object placement, and geometry of [Image 1]. Do not move, remove, or add new core subjects.
2. Completely overhaul the aesthetic of [Image 1] into the following style: "{style_name}".
3. Specific stylistic details to apply: {style_details}.
4. Modify the lighting, textures, color palette, and atmospheric effects to match this style perfectly (e.g., if the style requires metallic textures or neon lights, map them directly onto the existing objects in [Image 1]).
5. Ensure the final output looks cohesive, as if the original scene was natively created in the new style.

Negative Constraint: Do not alter the baseline composition, pose of people, or layout of the scene."""


def build_theme_create_style_transfer_prompt() -> str:
    return """You are an advanced AI creative director executing a zero-loss style transfer. You are provided with two images: [Image 1] (the core content layout) and [Image 2] (the visual style inspiration).

Your goal is to re-render [Image 1] so that it looks exactly as if it was created in the visual universe of [Image 2].

Strict Execution Instructions:
1. **Content & Structure (From Image 1):** You must 100% preserve the composition, spatial layout, camera angle, perspective, and the exact placement/pose of all subjects/objects from [Image 1]. Do not introduce new objects from Image 2's content.
2. **Artistic Style & Aesthetics (From Image 2):** Analyze [Image 2] and completely extract its visual DNA. This includes the color palette, lighting scheme (e.g., volumetric, high-key, neon, cinematic shadow), textures (e.g., matte, glossy, metallic, 3D clay, hand-drawn), brushstrokes, atmospheric effects, and grading.
3. **Seamless Synthesis:** Map the extracted style from [Image 2] directly onto the structure of [Image 1]. The output must look cohesive, intentional, and high-fidelity, without any artifacts or blurry borders.

Negative Constraint: Do not copy the physical subjects, characters, or text content from [Image 2] into the final image. Only copy the *how*, not the *what*."""


def build_theme_create_asset_text_replace_prompt(
    *,
    logo_position: str,
    element_position: str,
    old_text: str,
    new_text: str,
    font_style: str,
) -> str:
    return f"""You are executing a precise UI/UX asset and text replacement task on [Image 1]. You are provided with asset images: [Image 2] (New Logo) and [Image 3] (New Button/Element).

Perform the following localized modifications seamlessly, keeping all other untouched areas of [Image 1] identical:

1. **Logo Replacement:**
   - Locate the existing logo situated at the {logo_position} of [Image 1].
   - Replace it entirely with the new logo provided in [Image 2].
   - Utilize the alpha channel (transparency) of [Image 2] for a clean overlay. Scale and blend it naturally to match the local lighting and perspective.

2. **Element/Button Replacement:**
   - Locate the interactive element/button at the {element_position} of [Image 1].
   - Replace its visual asset with [Image 3], preserving the original button's interactive boundary and alignment.

3. **Text Content Update:**
   - Locate the text that reads "{old_text}" in [Image 1].
   - Rewrite and precisely render this text to read exactly: "{new_text}".
   - The typography should use a {font_style} font, with colors and sizes that harmoniously match the surrounding design.

Ensure no artifacts, blurry edges, or misalignment occur at the boundaries of the replaced elements."""


_RESIZE_MICRO_BANNER_SIZES = {"320x50"}
_RESIZE_LARGE_BANNER_SIZES = {"1200x222", "640x100"}
_RESIZE_ULTRA_NARROW_LEADERBOARD_SIZES = {"728x90"}
_RESIZE_LANDSCAPE_SIZES = {"1200x628", "1200x600", "640x360"}
_RESIZE_PORTRAIT_SQUARE_SIZES = {"720x720", "300x250", "480x480", "320x480", "360x640"}

_GEMINI_MICRO_BANNER_RESIZE_TEMPLATE = """You are an expert production designer specializing in high-performance responsive micro-banners. Adapt the provided input image into an ultra-thin, wide banner format with the exact resolution of {target_size} (e.g., 320x50).

CRITICAL RESPONSIVE MICRO-LAYOUT CONSTRAINTS:
1. PRESERVE ALL ASSETS: Every original text element, logo, and the CTA/Text block must be preserved with 100% pixel-perfect fidelity. Do not alter fonts, colors, or content.
2. AGGRESSIVE VISUAL SCALE: Scale up all main assets (Logo, CTA, Hero element) so they dominate the vertical space, occupying at least 80% of the banner's height.
3. ADAPTIVE INWARD LAYOUT: Re-arrange the assets into three columns:
   - Move/Place the brand LOGO to the FAR LEFT, with a small left padding.
   - Move/Place the main HERO CHARACTER/IMAGE into the center.
   - Move/Place the preserved CTA / Main text block on the CENTER-RIGHT, not on the far right edge.
4. SAFE MARGIN MANDATE: You MUST implement a strict safety margin on the FAR RIGHT EDGE. The entire right text block, including all disclaimers, must be shifted INWARD (to the left) by approximately 10% of the canvas width. This ensures zero cropping of text."""

_GEMINI_LARGE_BANNER_RESIZE_TEMPLATE = """You are an expert senior production designer. Adapt the provided input image into a large, wide banner format with the exact resolution of {target_size} (e.g., 1200x222). This version must strictly eliminate the duplicate branding bug seen in image_13.png.

CRITICAL LARGE BANNER LAYOUT & SINGLE-LOGO CONSTRAINTS:

1. ABSOLUTE SINGLE LOGO MANDATE (ANTI-DUPLICATION):
   - You are strictly FORBIDDEN from rendering more than ONE instance of the brand LOGO on the entire banner. Double logos or cloned text headers (as seen in image_13.png) are a critical failure.
   - The ONLY permitted logo must be the one placed in the designated Far-Left zone.
   - If any part of the original logo, title text, or brand badge appears a second time in the background battlefield scene, you must completely erase, paint over, and content-aware fill it using the native background textures (ambient smoke, ancient roofs, or sky).

2. ADAPTIVE THREE-COLUMN LAYOUT:
   - FAR LEFT Column: Render the single, complete brand LOGO stack cleanly. You may use a native framing panel, color block, or border accent derived directly from the source image style to isolate this logo section professionally.
   - CENTER Column: Display the central Hero character. Ensure he is naturally integrated into the cinematic scene without hard rectangular borders.
   - CENTER-RIGHT Column: Render the entire CTA / Main text block (including header tags and subtitles) using identical fonts and colors.

3. SAFE MARGIN MANDATE:
   - Shift the entire right-hand CTA/text column inward to the left, leaving a strict 10% empty safety margin on the far right edge of the canvas. Every character, descriptor, and disclaimer line must be whole, legible, and completely safe from cropping."""

_GEMINI_OVERSAMPLED_LEADERBOARD_RESIZE_TEMPLATE = """You are a precision technical production artist and layout designer. Your only task is to generate a 2-row vertical split-screen layout sheet containing TWO completely separate, independent 728x90 cinematic web banners stacked vertically inside a single 728x180 canvas.

The image must be perfectly divided into a Top Row (Y-axis 0px to 90px) and a Bottom Row (Y-axis 90px to 180px). Each row must act as an independent standalone 728x90 banner asset with zero asset leakage between them.

CRITICAL DUAL-ROW INDEPENDENT LAYOUT CONSTRAINTS:

1. TOP ROW BANNER COMPOSITION (Y-AXIS 0px - 90px):
   - Inside this exact top half, render a complete, self-contained 728x90 banner layout.
   - Left Logo Panel (NATIVE COLOR INHERITANCE): Identify the primary brand logo or title graphic from the source image. Render this complete logo asset inside a clean vertical panel on the leftmost edge of this row. CRITICAL COLOR RULE: The background color and texture of this panel MUST 100% inherit and replicate the exact original background color, style, and theme surrounding the logo in the source image (whether it is dark, bright, yellow, blue, or textured). Do not alter, invert, or invent a new background color for this panel. Keep the native branding color scheme perfectly intact.
   - Center Main Subject: Identify the primary central character, figure, or focal subject from the source image. Shrink it heavily until it occupies a maximum of 40% of this row's vertical height (roughly 35 pixels tall). Ensure its entire top boundary (hair/hat/helmet), full face, and eyes are 100% visible and perfectly centered vertically within this top row.
   - Right CTA Text: Identify the call-to-action (CTA) text block, promotional text, and subtext lines from the right side of the source image. Render this complete multi-layer text stack strictly within the rightmost 25% zone of this row. Scale it down to fit neatly within the 90px row height without any clipping. Maintain a strict 10% empty safety margin from the extreme right edge.

2. BOTTOM ROW BANNER COMPOSITION (Y-AXIS 90px - 180px):
   - Inside this exact bottom half, render a duplicate, independent 728x90 banner layout following the exact same structural layout rules as the Top Row.
   - Left Logo Panel (NATIVE COLOR INHERITANCE): Re-render the complete compressed brand logo inside the leftmost edge panel of this bottom row. The background color and texture MUST be an exact duplicate of the top row's panel, faithfully inheriting the native color scheme of the source image's logo area.
   - Center Main Subject: Re-render the primary central subject, shrunken down to 40% of this row's height, with the entire head, face, and eyes 100% visible and centered vertically within Y=90px to Y=180px.
   - Right CTA Text: Re-render the complete compressed multi-layer right-side text stack strictly within the rightmost 25% zone of this bottom row, with a 10% empty safety margin from the extreme right edge.

3. PERFECT COMPONENT FLOW & SEPARATION:
   - For BOTH rows independently, the left logo panel, the 40% miniature central subject, and the right CTA text must form three separate horizontal islands.
   - The remaining gaps inside each row must be seamlessly filled with connecting environment textures, smoke, or backgrounds from the source image.
   - Ensure the transition line at Y=90px is clean and straight, acting as a perfect boundary between the Top Row banner and the Bottom Row banner."""

_GEMINI_LANDSCAPE_RESIZE_TEMPLATE = """You are an expert production designer. Adapt the provided input image into a Landscape format with the exact resolution of {target_size}.

CRITICAL VISUAL CONSTRAINTS:
1. PERFECT PRESERVATION: Maintain all visual elements, including logos, CTA, text, and main subjects, exactly as they appear in the original image. No modifications allowed.
2. COMPOSITION: Keep the original relative positioning of all elements. Do not rearrange or swap their positions.
3. CANVAS FILL: Intelligently expand or crop the background to fit the new aspect ratio. Ensure the final output is sharp, with zero distortion, stretching, or squashing of the main elements."""

_GEMINI_PORTRAIT_SQUARE_RESIZE_TEMPLATE = """You are an expert production designer. Re-layout and adapt the provided input image into a Portrait/Square format with the exact resolution of {target_size}.

CRITICAL VISUAL CONSTRAINTS:
1. NO RE-IMAGINING: Do not alter the design, colors, typography, or content of the original image assets. Every single element must look identical to the source.
2. VERTICAL LAYOUT:
   - Move/Place the brand LOGO at the TOP.
   - Move/Place the CTA (Call to Action) / Main text at the BOTTOM.
   - Both elements must be perfectly centered horizontally.
3. BACKGROUND ADAPTATION: Adjust the background to fit the new vertical canvas seamlessly. Ensure the central subject matter remains uncompromised, un-stretched, and undistorted."""

_GEMINI_RESIZE_NEGATIVE_PROMPT = (
    "rearranged characters, missing text, low resolution, warped logo, "
    "unreadable disclaimers, text touching the right edge, single element filling "
    "entire canvas, overcrowded layout, double logos, duplicated branding, "
    "cloned text, two logos."
)


def _get_resize_template(target_size: str) -> str:
    if target_size in _RESIZE_MICRO_BANNER_SIZES:
        return _GEMINI_MICRO_BANNER_RESIZE_TEMPLATE
    if target_size in _RESIZE_LARGE_BANNER_SIZES:
        return _GEMINI_LARGE_BANNER_RESIZE_TEMPLATE
    if target_size in _RESIZE_ULTRA_NARROW_LEADERBOARD_SIZES:
        return _GEMINI_OVERSAMPLED_LEADERBOARD_RESIZE_TEMPLATE
    if target_size in _RESIZE_LANDSCAPE_SIZES:
        return _GEMINI_LANDSCAPE_RESIZE_TEMPLATE
    if target_size in _RESIZE_PORTRAIT_SQUARE_SIZES:
        return _GEMINI_PORTRAIT_SQUARE_RESIZE_TEMPLATE
    return _GEMINI_LANDSCAPE_RESIZE_TEMPLATE


def build_resize_prompt(
    target_size: str,
    user_note: str = "",
    preserve_elements: list[str] | None = None,
    negative_prompt_override: str | None = None,
) -> str:
    template = _get_resize_template(target_size)
    prompt = template.format(target_size=target_size)

    extras: list[str] = []
    if preserve_elements:
        extras.append(
            f"Additional elements to preserve exactly from the original image: {', '.join(preserve_elements)}."
        )
    if user_note.strip():
        extras.append(f"Additional user instruction: {user_note.strip()}")
    negative_prompt = (negative_prompt_override or "").strip() or _GEMINI_RESIZE_NEGATIVE_PROMPT
    extras.append(f"Negative Prompt: {negative_prompt}")

    if extras:
        prompt = f"{prompt}\n\n" + "\n".join(extras)

    return prompt.strip()


def build_resize_prompts_for_sizes(
    target_sizes: list[str],
    user_note: str = "",
    preserve_elements: list[str] | None = None,
) -> dict[str, str]:
    """Build a dict of {size -> resize_prompt} for all requested sizes."""
    return {
        size: build_resize_prompt(
            target_size=size,
            user_note=user_note,
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
