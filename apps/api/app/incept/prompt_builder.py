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
    prompt_template: str = "",
) -> str:
    normalized_prompt = prompt_template.strip()
    if normalized_prompt.startswith("You are ") or "Instructions:" in normalized_prompt:
        return normalized_prompt
    return f"""You are an expert AI image modifier. Your task is to transform the artistic style of [Image 1] while strictly preserving its original structural layout, camera perspective, and object composition.

Instructions:
1. Analyze the composition, object placement, and geometry of [Image 1]. Do not move, remove, or add new core subjects.
2. Completely overhaul the aesthetic of [Image 1] into the following style: "{style_name}".
3. Specific stylistic details to apply: {style_details}.
4. Modify the lighting, textures, color palette, and atmospheric effects to match this style perfectly (e.g., if the style requires metallic textures or neon lights, map them directly onto the existing objects in [Image 1]).
5. Ensure the final output looks cohesive, as if the original scene was natively created in the new style.

Negative Constraint: Do not alter the baseline composition, pose of people, or layout of the scene."""


def build_theme_create_style_transfer_prompt(*, prompt_template: str = "") -> str:
    base_prompt = """You are an advanced AI creative director executing a zero-loss style transfer. You are provided with two images: [Image 1] (the core content layout) and [Image 2] (the visual style inspiration).

Your goal is to re-render [Image 1] so that it looks exactly as if it was created in the visual universe of [Image 2].

Strict Execution Instructions:
1. **Content & Structure (From Image 1):** You must 100% preserve the composition, spatial layout, camera angle, perspective, and the exact placement/pose of all subjects/objects from [Image 1]. Do not introduce new objects from Image 2's content.
2. **Artistic Style & Aesthetics (From Image 2):** Analyze [Image 2] and completely extract its visual DNA. This includes the color palette, lighting scheme (e.g., volumetric, high-key, neon, cinematic shadow), textures (e.g., matte, glossy, metallic, 3D clay, hand-drawn), brushstrokes, atmospheric effects, and grading.
3. **Seamless Synthesis:** Map the extracted style from [Image 2] directly onto the structure of [Image 1]. The output must look cohesive, intentional, and high-fidelity, without any artifacts or blurry borders.

Negative Constraint: Do not copy the physical subjects, characters, or text content from [Image 2] into the final image. Only copy the *how*, not the *what*."""
    normalized_prompt = prompt_template.strip()
    if not normalized_prompt:
        return base_prompt
    if normalized_prompt.startswith("You are ") and "Strict Execution Instructions:" in normalized_prompt:
        return normalized_prompt
    return f"{base_prompt}\n\nAdditional Direction:\n{normalized_prompt}"


def build_image_remediation_prompt(
    *,
    analysis_summary: str = "",
    user_note: str = "",
    aggressive_personality_recast: bool = False,
) -> str:
    standard_prompt = """You are an advanced commercial advertising image editing engine. Your only task is to remediate policy violations in the provided ad image while preserving the original advertising layout with near pixel-perfect fidelity.

[HIGHEST PRIORITY: FULL CANVAS PRESERVATION]
- Treat the input image as a locked advertisement layout, not as a scene to redesign.
- The final output must preserve the COMPLETE original canvas composition: same framing, same camera angle, same edge boundaries, same text layout, same logo placement, same CTA placement, same headline placement, and the same visible top/bottom/left/right content.
- You are strictly FORBIDDEN from cropping, zooming in, reframing, punching in on subjects, enlarging the main characters, or pushing any edge content outside the canvas.
- If additional space is ever needed to support a compliant edit, extend or reconstruct the surrounding background subtly inside the same visual world. Do NOT solve the task by cutting off borders or enlarging the center.

[LOCKED REGIONS THAT MUST REMAIN FULLY VISIBLE]
- Preserve all marketing copy, headline text, subheadline text, CTA buttons, logos, dates, disclaimers, mascots, and background layout blocks unless a specific element is itself the policy violation.
- Every existing text block and CTA must remain fully readable and fully inside the canvas.
- The top title area, bottom footer area, left edge content, and right CTA area are protected layout zones. They must not be truncated, cropped, shifted off canvas, or reflowed into a new composition.

[LOCAL-ONLY EDITING RULE]
- Only edit the violating regions.
- Keep all non-violating areas unchanged in position, size, and visual hierarchy.
- Do not redesign the ad. Do not convert the whole piece into a new poster. Do not simplify the layout. Do not remove valid text or valid branding.

[MANDATORY REMEDIATION: IMPERSONATION & CELEBRITY IP ERADICATION]
- If recognizable real-world public figures or athletes are present, fully replace only those person regions with generic fictional commercial sports characters.
- Do NOT keep the original real-human likeness.
- Do NOT just lightly retouch the face. Change the face, hairstyle, facial hair, jersey identity cues, body silhouette cues, and other recognizable traits enough to remove resemblance.
- Replace official or iconic team styling, stripes, and famous jersey numbers with generic unbranded sportswear details.
- Keep the replacement characters in the SAME pose footprint and SAME approximate occupied area as the originals so the ad layout stays intact.

[MANDATORY REMEDIATION: TROPHY / IP REPLACEMENT]
- If a protected or recognizable real-world trophy or copyrighted competition object is present, replace only that object with a generic original victory trophy.
- Keep its approximate placement and scale so surrounding text and CTA layout are not disturbed.

[MANDATORY REMEDIATION: ADULT CONTENT]
- If any human or illustrated character shows excessive cleavage, intimate exposure, or sexually suggestive styling, redraw only the violating clothing/body area into modest, professional, fully covered attire.
- Keep the person’s pose footprint and composition footprint stable.

[MANDATORY REMEDIATION: DECEPTIVE UI]
- Remove fake play buttons, fake close icons, fake system UI, or deceptive notification overlays only when they are present and violating.
- Fill those removed regions seamlessly without disturbing nearby valid text or CTA areas.

[OUTPUT STANDARD]
- Output one final remediated ad image.
- The finished image must look like the original ad survived compliance cleanup, not like a newly reimagined ad.
- Preserve the original canvas size and aspect ratio of the uploaded image.
- The most important success condition is this: no cropped headline, no cropped CTA, no cut-off logo, no cut-off border content, and no missing legal or footer text caused by the remediation."""

    aggressive_personality_prompt = """You are an advanced commercial advertising image editing engine. Your only task is to remediate policy violations in the provided ad image while preserving the original advertising layout and full canvas integrity.

[HIGHEST PRIORITY: FULL CANVAS PRESERVATION]
- Treat the input image as a locked advertisement layout, not as a scene to redesign.
- Preserve the COMPLETE original canvas composition: same framing, same camera angle, same edge boundaries, same text layout, same logo placement, same CTA placement, same headline placement, and the same visible top/bottom/left/right content.
- You are strictly FORBIDDEN from cropping, zooming in, reframing, punching in on subjects, enlarging the main characters, or pushing any edge content outside the canvas.
- If additional space is ever needed to support a compliant edit, extend or reconstruct the surrounding background subtly inside the same visual world. Do NOT solve the task by cutting off borders or enlarging the center.

[LOCKED REGIONS THAT MUST REMAIN FULLY VISIBLE]
- Preserve all marketing copy, headline text, subheadline text, CTA buttons, logos, dates, disclaimers, mascots, and background layout blocks unless a specific element is itself the policy violation.
- Every existing text block and CTA must remain fully readable and fully inside the canvas.
- The top title area, bottom footer area, left edge content, and right CTA area are protected layout zones. They must not be truncated, cropped, shifted off canvas, or reflowed into a new composition.

[AGGRESSIVE PERSONA RECAST RULE]
- If recognizable real-world public figures, athletes, influencers, celebrities, or personality-rights risks are present, you MUST fully rebuild the entire human character region into generic fictional commercial characters.
- Do NOT merely retouch the face. Do NOT preserve the original likeness. Do NOT keep the original facial identity.
- You must change all identity-bearing cues together: face shape, eyes, nose, mouth, jawline, hairstyle, hairline, facial hair, skin detailing, body silhouette, shoulder line, pose-adjacent outline, jersey styling, jersey colors, jersey stripes, jersey logos, famous numbers, and other iconic markers.
- If necessary, regenerate the full upper body or full visible body region of the violating person so the result no longer resembles the original celebrity at all.
- The replacement person may keep the same general placement in the ad, but does NOT need to preserve the exact original face, hair, clothing details, or silhouette.
- Prefer clearly synthetic, commercial, game-like, or stylized sports characters over minimally edited realistic celebrity faces whenever needed to eliminate resemblance.

[LOCALIZE DAMAGE, NOT LIKENESS]
- Preserve the advertisement layout, background, copy, CTA, logo, and non-violating supporting elements.
- But for violating celebrity/personality-rights regions, prioritize full de-identification over minimal edit distance.
- It is acceptable to replace the entire person region and adjacent identity cues if that is required for true compliance.
- Do not leave behind recognizable remnants of the original person in the face, jersey, hair, body shape, or iconic styling.

[MANDATORY REMEDIATION: TROPHY / IP REPLACEMENT]
- If a protected or recognizable real-world trophy or copyrighted competition object is present, replace only that object with a generic original victory trophy.
- Keep its approximate placement and scale so surrounding text and CTA layout are not disturbed.

[MANDATORY REMEDIATION: ADULT CONTENT]
- If any human or illustrated character shows excessive cleavage, intimate exposure, or sexually suggestive styling, redraw only the violating clothing/body area into modest, professional, fully covered attire.
- Keep the person’s composition footprint stable unless a larger character-region rebuild is required for de-identification.

[MANDATORY REMEDIATION: DECEPTIVE UI]
- Remove fake play buttons, fake close icons, fake system UI, or deceptive notification overlays only when they are present and violating.
- Fill those removed regions seamlessly without disturbing nearby valid text or CTA areas.

[OUTPUT STANDARD]
- Output one final remediated ad image.
- The finished image must look like the original ad survived compliance cleanup, not like a newly reimagined ad.
- Preserve the original canvas size and aspect ratio of the uploaded image.
- The most important success condition is this: no cropped headline, no cropped CTA, no cut-off logo, no cut-off border content, and no missing legal or footer text caused by the remediation.
- The second most important success condition is this: no recognizable resemblance to any real-world public figure remains."""

    sections = [aggressive_personality_prompt if aggressive_personality_recast else standard_prompt]

    normalized_analysis = analysis_summary.strip()
    if normalized_analysis:
        sections.append(f"""[DETECTED POLICY VIOLATIONS TO FIX]
- The following structured remediation instructions were produced by the compliance analysis model. Follow them exactly and prioritize them over guesses:
{normalized_analysis}""")

    normalized_user_note = user_note.strip()
    if normalized_user_note:
        sections.append(f"""[USER MICRO-ADJUSTMENTS]
- In addition to the automatic compliance remediation above, follow this specific user instruction (provided it does not violate policy): {normalized_user_note}""")

    return "\n\n".join(sections)


_RESIZE_MICRO_BANNER_SIZES = {"320x50", "640x100"}
_RESIZE_LARGE_BANNER_SIZES = {"1200x222"}
_RESIZE_ULTRA_NARROW_LEADERBOARD_SIZES = {"728x90"}
_RESIZE_LANDSCAPE_SIZES = {"1200x628", "1200x600", "640x360"}
_RESIZE_PORTRAIT_SQUARE_SIZES = {"720x720", "300x250", "480x480", "320x480", "360x640"}

_GEMINI_MICRO_BANNER_RESIZE_TEMPLATE = """You are an expert production designer specializing in high-performance responsive micro-banners. Adapt the provided input image into an ultra-thin, wide banner format with the exact resolution of {target_size} (e.g., 320x50, 640x100).

CRITICAL RESPONSIVE LIQUID-LAYOUT CONSTRAINTS:
1. PERFECT ASSET PRESERVATION: Every original textual layer, graphic logo, branding asset, and the CTA/Text block from the source image must be preserved with 100% pixel-perfect fidelity. Do not alter fonts, colors, or language.
2. SINGLE FLUID CANVAS (ANTI-ISOLATION): 
   - The background across the entire banner must be ONE single, continuous, undivided, and un-interrupted organic environment cloned directly from the source image (e.g., continuous grass, textures, and lighting). 
   - You are strictly FORBIDDEN from creating any visual vertical columns, rectangular panel partitions, vertical division lines, or tone-breaking color blocks. There must be ZERO geometric separation or isolation between the assets and the background.
3. SEAMLESS FLOATING ASSETS: 
   - The brand logo and the CTA text block must FLOAT directly on top of the native background pixels. 
   - The background textures must flow seamlessly and smoothly underneath and between the Logo, the Center Subject, and the CTA with perfect color and gradient continuity, blending them into one natural scene.
4. AGGRESSIVE VISUAL SCALE: Scale up all main assets (Logo, CTA, and the core Subject/Hero element) so they dominate the vertical space, occupying at least 80% of the banner's height.
5. HORIZONTAL POSITIONING LOGIC:
   - Position the single brand LOGO on the leftmost side, drifting slightly inward from the edge.
   - Position the main SUBJECT MATTER / HERO IMAGE perfectly in the horizontal center.
   - Position the preserved CTA / Main text block on the right side, shifted INWARD (to the left) by approximately 15% of the canvas width to maintain a strict, clear empty safety margin on the far-right edge."""

_GEMINI_LARGE_BANNER_RESIZE_TEMPLATE = """You are an expert production designer. Adapt the provided input image into a large, wide banner format with the exact resolution of {target_size}.

CRITICAL LARGE BANNER LAYOUT CONSTRAINTS:
1. PERFECT PRESERVATION (1:1): Preserve all existing assets (Logo, Text, CTA block) with identical fonts, colors, and content. The background must strictly use and extend the exact native textures, lighting, and colors of the source image with zero distortion or thematic changes. Do NOT scale assets up to fill empty space; maintain their clean, relative scale.
2. ABSOLUTE NO RECTANGULAR BOXES & SINGLE LOGO MANDATE:
   - You are strictly FORBIDDEN from drawing or rendering any rectangular background panels, solid color containers, or sharp visual bounding frames behind the Logo on the left. The background across the entire banner must be ONE single, organic, continuous un-interrupted scene.
   - Render exactly ONE single instance of the brand LOGO stack on the entire canvas, positioned on the far-left. Any duplicate or secondary logos emerging in the background artwork must be completely removed and blended over using native background elements.
3. ADAPTIVE THREE-COLUMN LAYOUT: Implement a balanced three-column layout.
   - Brand LOGO on the FAR LEFT.
   - Core SUBJECT MATTER / HERO IMAGE in the CENTER.
   - Preserved CTA / Main text block on the CENTER-RIGHT.
4. SAFE MARGIN MANDATE: Shift the entire right-hand CTA/text block INWARD (to the left) by at least 10% of the canvas width, leaving a clear empty safety margin on the far right edge. This is critical to ensure zero cropping of any characters."""

_GEMINI_OVERSAMPLED_LEADERBOARD_RESIZE_TEMPLATE = """You are a precision technical production artist and layout designer. Your only task is to generate a 2-row vertical split-screen layout sheet containing TWO completely separate, independent 728x90 cinematic web banners stacked vertically inside a single 728x180 canvas. 

The image must be perfectly divided into a Top Row (Y-axis 0px to 90px) and a Bottom Row (Y-axis 90px to 180px). Each row must act as an independent standalone 728x90 banner asset with zero asset leakage between them.

CRITICAL DUAL-ROW NO-BORDER LAYOUT CONSTRAINTS:

1. TOP ROW BANNER COMPOSITION (Y-AXIS 0px - 90px):
   - Inside this exact top half, render a complete, self-contained 728x90 banner layout.
   - **Left Logo Zone (SEAMLESS FLOATING & INTEGRATION):** Identify the primary brand logo asset from the source image. Render this complete logo asset strictly on the leftmost edge of this row. **CRITICAL NO-BORDER RULE:** Do NOT create any artificial rectangular panels, vertical colored blocks, boxes, or hard graphic shapes behind the logo. Absolutely NO dark blue or mismatched color blocks are allowed. The logo typography MUST float transparently and naturally directly on top of the organic background scenery (smoke, sky, colors) extended from the source image.
   - **Center Main Subject:** Identify the primary central subject from the source image. Shrink it heavily until it occupies a maximum of 40% of this row's vertical height (roughly 35 pixels tall). Ensure its entire top boundary (hair/hat/helmet), full face, and eyes are 100% visible and perfectly centered vertically within this top row.
   - **Right CTA Text Zone (SEAMLESS FLOATING):** Identify the CTA text block and promotional subtext lines from the right side of the source image. Render this complete text stack strictly within the rightmost 25% zone of this row, force-shrunken to fit without clipping. **CRITICAL:** The text must float organically on the continuous background scenery with zero hard shapes or boxes behind it. Maintain a strict 10% empty safety margin from the extreme right edge.

2. BOTTOM ROW BANNER COMPOSITION (Y-AXIS 90px - 180px):
   - Inside this exact bottom half, render a duplicate, independent 728x90 banner layout following the exact same structural layout rules as the Top Row.
   - **Left Logo Zone (SEAMLESS FLOATING & INTEGRATION):** Re-render the complete compressed brand logo inside the leftmost edge zone of this bottom row, floating seamlessly on the continuous background with NO hard borders, NO panel graphics, and NO artificial color blocks.
   - **Center Main Subject:** Re-render the primary central subject, shrunken down to 40% of this row's height, with the entire head, face, and eyes 100% visible and centered vertically within Y=90px to Y=180px.
   - **Right CTA Text Zone:** Re-render the complete compressed text stack strictly within the rightmost 25% zone of this bottom row, floating seamlessly with a 10% empty safety margin from the extreme right edge.

3. CONTINUOUS BACKGROUND FLOW (ZERO DIVIDER LINES):
   - For BOTH rows independently, the left logo, the 40% miniature central subject, and the right CTA text must be positioned horizontally without any graphic separations.
   - **STRICTLY FORBID any hard vertical lines, geometric divider borders, color block frames, or rectangular masks between the elements.** - The extended background environment, smoke, gradients, and textures from the source image must flow completely fluidly and unobstructed from the far-left edge to the far-right edge, acting as a single continuous panoramic canvas.
   - Ensure the horizontal dividing line at Y=90px remains clean and straight as the only sharp boundary between the Top and Bottom banners.
   - ABSOLUTE NO-ANNOTATION RULE: Do NOT render any technical annotations, measurement labels, dimension text (such as '10px', '9px', '90px'), redlines, arrows, or calibration numbers anywhere on the canvas. All instructions are strictly for layout calculation and must remain completely invisible in the final graphic."""

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

_GEMINI_LARGE_BANNER_NEGATIVE_PROMPT = (
    "text boxes, background panels, container frames, solid color blocks, "
    "bounding boxes, sharp border lines, multi-panel background, split screens, "
    "picture-in-picture, duplicate logos, cloned branding, two logos, cut off "
    "text, cropped head, missing text, deformed letters."
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
    default_negative_prompt = (
        _GEMINI_LARGE_BANNER_NEGATIVE_PROMPT
        if target_size in (_RESIZE_MICRO_BANNER_SIZES | _RESIZE_LARGE_BANNER_SIZES)
        else _GEMINI_RESIZE_NEGATIVE_PROMPT
    )
    negative_prompt = (negative_prompt_override or "").strip() or default_negative_prompt
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
