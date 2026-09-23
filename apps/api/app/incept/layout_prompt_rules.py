"""Per-size layout prompt rules for ad image generation.

These rules are distilled from the handmade resize references in
resize_reference. They are prompt-time constraints, not post-processing rules:
each requested size gets its own model call with its own layout contract.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayoutRule:
    family: str
    summary: str
    logo_rule: str
    cta_rule: str
    composition_rule: str
    negative_rule: str


def parse_size(size: str) -> tuple[int | None, int | None]:
    try:
        width_text, height_text = size.lower().split("x", 1)
        return int(width_text), int(height_text)
    except Exception:
        return None, None


def layout_family_for_size(size: str) -> str:
    width, height = parse_size(size)
    if not width or not height:
        return "unknown"

    ratio = width / height

    # 320x50, 728x90, 1200x222, 640x100, 320x100
    if ratio >= 3.2:
        return "narrow_banner"

    # 1200x628, 1200x600, 640x360, 1920x1080
    if ratio >= 1.45:
        return "wide_landscape"

    # 300x250, 720x720, 480x480, near-square mobile rectangles
    if ratio >= 0.8:
        return "compact_square"

    # 320x480, 360x640, 1080x1920
    return "portrait"


_RULES: dict[str, LayoutRule] = {
    "compact_square": LayoutRule(
        family="compact_square",
        summary="Near-square or compact rectangle, such as 300x250 or 720x720.",
        logo_rule=(
            "Logo scale: keep exactly one primary logo visible but not dominant; target logo width about 18-28% "
            "of canvas width and height under 16% of canvas height. Place it near the top or upper corner. "
            "The logo must be fully inside the canvas safe area with at least 10-14 px padding from every edge. "
            "If the logo would touch an edge, make it smaller instead of cropping it."
        ),
        cta_rule=(
            "CTA scale: keep exactly one primary CTA button; target CTA width about 30-42% of canvas width "
            "and height about 9-14% of canvas height. Place it in the lower third with at least 10-14 px "
            "padding from the bottom and side edges; it must not cover the hero subject. Prefer a smaller CTA "
            "over a giant button. If the CTA would touch an edge, make it smaller or move it inward."
        ),
        composition_rule=(
            "Use a compact ad layout: logo/top identity, hero scene or main product in the center, CTA in the lower third. "
            "The hero scene should remain the largest visual area, roughly 45-60% of the canvas. "
            "Simplify background detail instead of enlarging logo or CTA."
        ),
        negative_rule=(
            "Do not make the logo or CTA oversized. Do not crop the logo. Do not crop the CTA. Do not let logo plus CTA "
            "occupy more than about 36% of the canvas area. Do not place logo or CTA partially outside the canvas. "
            "Do not duplicate the logo or CTA. Do not crop off the hero scene."
        ),
    ),
    "portrait": LayoutRule(
        family="portrait",
        summary="Vertical mobile creative, such as 320x480, 360x640, or 1080x1920.",
        logo_rule=(
            "Logo scale: target logo width about 32-45% of canvas width, height under 12% of canvas height. "
            "Place it near the top with clear padding. The logo must be fully visible and never touch or cross the canvas edge."
        ),
        cta_rule=(
            "CTA scale: target CTA width about 48-64% of canvas width and height about 7-12% of canvas height. "
            "Place it near the bottom, centered or slightly lower-third, with clear padding. "
            "Use the smaller end of this range if the scene contains detailed characters, products, or environment."
        ),
        composition_rule=(
            "Use a vertical stacked layout: logo at top, hero scene or character/product in the middle, CTA at bottom. "
            "Keep the hero subject as the main focus, using about 50-65% of the canvas height. "
            "Reflow text into one or two readable lines if needed."
        ),
        negative_rule=(
            "Do not create a giant top logo. Do not crop the logo. Do not let the CTA cover characters or product. "
            "Do not crop heads, product edges, or important game scene content."
        ),
    ),
    "wide_landscape": LayoutRule(
        family="wide_landscape",
        summary="Wide landscape ad, such as 1200x628, 1200x600, 640x360, or 1920x1080.",
        logo_rule=(
            "Logo scale: target logo width about 16-26% of canvas width and height under 20% of canvas height. "
            "Place it in the upper-left, upper-center, or a brand-safe corner."
        ),
        cta_rule=(
            "CTA scale: target CTA width about 20-32% of canvas width and height about 10-18% of canvas height. "
            "Place it in the lower third or lower-right/center, with enough padding."
        ),
        composition_rule=(
            "Use a wide cinematic layout: preserve the broad scene, keep the main gameplay/product/character area dominant, "
            "and balance logo and CTA around it. Leave open background area for readability."
        ),
        negative_rule=(
            "Do not turn the layout into a logo-and-button poster. Do not let logo plus CTA dominate the scene. "
            "Do not crop large parts of the background or hero subject."
        ),
    ),
    "narrow_banner": LayoutRule(
        family="narrow_banner",
        summary="Very wide banner, such as 320x50, 728x90, 1200x222, 640x100, or 320x100.",
        logo_rule=(
            "Logo scale: show exactly one primary logo, target logo width about 12-18% of canvas width. "
            "Keep it on the left or left-center, fully legible, and inside the central horizontal band with "
            "clear padding. Do not repeat the logo anywhere else in the banner."
        ),
        cta_rule=(
            "CTA scale: show exactly one primary CTA button, target CTA width about 16-22% of canvas width "
            "and height about 42-62% of canvas height. Place it on the right, fully visible, with clear horizontal "
            "padding. Do not repeat the CTA text or button anywhere else in the banner."
        ),
        composition_rule=(
            "Use a left-to-right banner layout: logo on the left, compact hero scene/key subject in the center, CTA on the right. "
            "Keep all important elements inside the central band. Leave clear separation between the logo, hero scene, and CTA. "
            "Use short text only; reflow or omit secondary copy before enlarging logo or CTA."
        ),
        negative_rule=(
            "Do not use a huge logo or huge CTA. Do not stack elements vertically. Do not include a full-size scene that gets cropped. "
            "Do not duplicate the logo. Do not duplicate the CTA. Do not show partial cropped copies of the logo or CTA at the edges. "
            "Do not overlap logo and CTA with each other or with duplicate source elements. Do not create multiple banner previews inside one image."
        ),
    ),
    "endcard": LayoutRule(
        family="endcard",
        summary="Video end-card creative: 360x640 (portrait), 480x480 (square), or 640x360 (landscape).",
        logo_rule=(
            "Logo placement: center the primary logo HORIZONTALLY at the TOP of the canvas. "
            "Target logo width about 35-50% of canvas width. Add clear padding above and below. "
            "The logo must be fully visible — never touch the canvas edge."
        ),
        cta_rule=(
            "CTA placement: center the primary CTA button HORIZONTALLY at the BOTTOM of the canvas. "
            "Target CTA width about 50-65% of canvas width, height about 10-15% of canvas height. "
            "Place it in the lower quarter with generous bottom padding. Use a high-contrast button."
        ),
        composition_rule=(
            "End-card vertical layout (top to bottom): "
            "1. Brand logo — horizontally centered at the top. "
            "2. Hero scene / main character — middle area, roughly 40-50% of canvas height. "
            "3. App store badges — centered in the lower-middle area, SIDE BY SIDE on the same row: "
            "   Apple App Store badge on the LEFT, Google Play badge on the RIGHT. "
            "   Both badges at equal size, each about 28-35% of canvas width, horizontally aligned. "
            "4. CTA button — horizontally centered at the bottom, below the store badges. "
            "Preserve the source creative background, color palette, characters, and art style exactly."
        ),
        negative_rule=(
            "Do not place the logo at the bottom or center. Do not place the CTA at the top. "
            "Do not stack app store badges vertically — they MUST be side by side on one row. "
            "Do not omit either the Apple App Store or the Google Play badge. "
            "Do not change the background, art style, or characters from the source image. "
            "Do not crop the logo or CTA. Do not duplicate any badge or button."
        ),
    ),
    "unknown": LayoutRule(
        family="unknown",
        summary="Unknown ad size.",
        logo_rule="Logo scale: keep it visible and legible without dominating the canvas.",
        cta_rule="CTA scale: keep it visible, readable, and smaller than the main hero area.",
        composition_rule="Compose one complete ad for the requested size with balanced logo, CTA, and hero content.",
        negative_rule="Do not create a collage, contact sheet, or multi-size preview.",
    ),
}

# End-card sizes that route to the endcard layout family
ENDCARD_SIZES: frozenset[str] = frozenset({"360x640", "480x480", "640x360"})


def get_layout_rule(size: str) -> LayoutRule:
    if size.lower().strip() in ENDCARD_SIZES:
        return _RULES["endcard"]
    return _RULES.get(layout_family_for_size(size), _RULES["unknown"])


def build_layout_prompt_rule(size: str) -> str:
    rule = get_layout_rule(size)
    return "\n".join(
        [
            f"Layout family: {rule.family}. {rule.summary}",
            rule.composition_rule,
            rule.logo_rule,
            rule.cta_rule,
            rule.negative_rule,
        ]
    )
