"""Utilities for deterministic contact-sheet generation and extraction."""

from __future__ import annotations

import io
from dataclasses import dataclass

CANVAS_W = 3072
CANVAS_H = 1728
CONTACT_SHEET_SIZE = f"{CANVAS_W}x{CANVAS_H}"
CONTACT_SHEET_QUALITY = "medium"


@dataclass(frozen=True)
class ContactSheetPanel:
    target_size: str
    image_bytes: bytes
    bbox: tuple[int, int, int, int]
    source_ratio: float
    target_ratio: float
    score: float


@dataclass(frozen=True)
class ContactSheetPlan:
    family: str
    title: str
    target_sizes: list[str]
    panel_layout: dict[str, tuple[int, int, int, int]]


OUTER_MARGIN = 48
GUTTER = 40
ZONE_GAP = 56
MIXED_FAMILY = "mixed"
HERO_FAMILY = "hero"
BANNER_FAMILY = "banner"
MIXED_ORDER = [
    "720x720",
    "1200x628",
    "300x250",
    "320x480",
    "1200x600",
    "1200x222",
    "728x90",
    "640x100",
    "320x50",
]
MIXED_SLOT_BOUNDS: dict[str, tuple[int, int, int, int]] = {
    "720x720": (80, 80, 780, 780),
    "1200x628": (860, 80, 2260, 820),
    "300x250": (2460, 140, 2880, 490),
    "320x480": (120, 880, 540, 1510),
    "1200x600": (560, 860, 1760, 1460),
    "1200x222": (1832, 900, 3020, 1120),
    "728x90": (2050, 1160, 3000, 1278),
    "640x100": (2000, 1320, 2900, 1460),
    "320x50": (2130, 1520, 2642, 1600),
}
HERO_ORDER = ["1200x628", "1200x600", "320x480", "720x720", "300x250"]
BANNER_ORDER = ["1200x222", "728x90", "640x100", "320x50"]
HERO_SLOT_BOUNDS: dict[str, tuple[int, int, int, int]] = {
    "720x720": (96, 96, 980, 980),
    "1200x628": (1050, 96, 2976, 940),
    "320x480": (120, 1060, 760, 1628),
    "1200x600": (840, 1040, 2490, 1632),
    "300x250": (2550, 1090, 2976, 1460),
}
BANNER_SLOT_BOUNDS: dict[str, tuple[int, int, int, int]] = {
    "1200x222": (120, 140, 2952, 560),
    "728x90": (300, 680, 2772, 928),
    "640x100": (420, 1040, 2652, 1292),
    "320x50": (920, 1420, 2152, 1568),
}


def _parse_size(size: str) -> tuple[int | None, int | None]:
    try:
        width_text, height_text = size.lower().split("x", 1)
        return int(width_text), int(height_text)
    except Exception:
        return None, None


def _to_png(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _is_strip_size(width: int, height: int) -> bool:
    ratio = width / max(height, 1)
    return ratio >= 4.0 or height <= 140


def _sheet_family_for_size(size: str) -> str:
    width, height = _parse_size(size)
    if not width or not height:
        return HERO_FAMILY
    return BANNER_FAMILY if _is_strip_size(width, height) else HERO_FAMILY


def _scale_dimensions(width: int, height: int, scale: float) -> tuple[int, int]:
    return max(1, int(round(width * scale))), max(1, int(round(height * scale)))


def _fit_size_in_slot(
    width: int,
    height: int,
    slot: tuple[int, int, int, int],
) -> tuple[int, int, int, int]:
    left, top, right, bottom = slot
    slot_w = max(1, right - left)
    slot_h = max(1, bottom - top)
    scale = min(slot_w / width, slot_h / height)
    draw_w, draw_h = _scale_dimensions(width, height, scale)
    draw_left = left + max(0, (slot_w - draw_w) // 2)
    draw_top = top + max(0, (slot_h - draw_h) // 2)
    return (draw_left, draw_top, draw_left + draw_w, draw_top + draw_h)


def _pack_scaled_rectangles(
    entries: list[tuple[str, int, int]],
    scale: float,
    bounds: tuple[int, int, int, int],
) -> tuple[bool, dict[str, tuple[int, int, int, int]]]:
    left, top, right, bottom = bounds
    usable_w = right - left
    usable_h = bottom - top
    x = left
    y = top
    row_height = 0
    rows: list[list[tuple[str, int, int, int, int]]] = []
    current_row: list[tuple[str, int, int, int, int]] = []

    for size, width, height in entries:
        scaled_w, scaled_h = _scale_dimensions(width, height, scale)
        if scaled_w > usable_w or scaled_h > usable_h:
            return False, {}
        if current_row and x + scaled_w > right:
            rows.append(current_row)
            x = left
            y += row_height + GUTTER
            row_height = 0
            current_row = []
        if y + scaled_h > bottom:
            return False, {}
        current_row.append((size, x, y, scaled_w, scaled_h))
        x += scaled_w + GUTTER
        row_height = max(row_height, scaled_h)

    if current_row:
        rows.append(current_row)

    total_h = sum(max(item[4] for item in row) for row in rows) + GUTTER * max(0, len(rows) - 1)
    top_offset = max(0, (usable_h - total_h) // 2)
    layout: dict[str, tuple[int, int, int, int]] = {}
    cursor_y = top + top_offset
    for row in rows:
        row_h = max(item[4] for item in row)
        row_w = sum(item[3] for item in row) + GUTTER * max(0, len(row) - 1)
        left_offset = max(0, (usable_w - row_w) // 2)
        cursor_x = left + left_offset
        for size, _, _, scaled_w, scaled_h in row:
            top = cursor_y + max(0, (row_h - scaled_h) // 2)
            layout[size] = (cursor_x, top, cursor_x + scaled_w, top + scaled_h)
            cursor_x += scaled_w + GUTTER
        cursor_y += row_h + GUTTER
    return True, layout


def _fit_layout_in_bounds(
    entries: list[tuple[str, int, int]],
    bounds: tuple[int, int, int, int],
) -> dict[str, tuple[int, int, int, int]]:
    if not entries:
        return {}

    low = 0.02
    high = min(
        (bounds[2] - bounds[0]) / max(item[1] for item in entries),
        (bounds[3] - bounds[1]) / max(item[2] for item in entries),
    )
    best_layout: dict[str, tuple[int, int, int, int]] = {}
    for _ in range(28):
        mid = (low + high) / 2.0
        fits, layout = _pack_scaled_rectangles(entries, mid, bounds)
        if fits:
            best_layout = layout
            low = mid
        else:
            high = mid

    if best_layout:
        return best_layout

    _, fallback = _pack_scaled_rectangles(entries, low, bounds)
    return fallback


def _ordered_sizes_for_family(target_sizes: list[str], family: str) -> list[str]:
    cleaned = []
    seen: set[str] = set()
    for size in [size.strip() for size in target_sizes if size.strip()]:
        if size in seen:
            continue
        if family == MIXED_FAMILY or _sheet_family_for_size(size) == family:
            cleaned.append(size)
            seen.add(size)
    if family == MIXED_FAMILY:
        order = MIXED_ORDER
    else:
        order = HERO_ORDER if family == HERO_FAMILY else BANNER_ORDER
    ordered = [size for size in order if size in seen]
    ordered.extend(size for size in cleaned if size not in ordered)
    return ordered


def _fallback_bounds_for_family(family: str) -> tuple[int, int, int, int]:
    if family == MIXED_FAMILY:
        return (96, 96, CANVAS_W - 96, CANVAS_H - 96)
    if family == BANNER_FAMILY:
        return (120, 140, CANVAS_W - 120, CANVAS_H - 140)
    return (96, 96, CANVAS_W - 96, CANVAS_H - 96)


def compute_panel_layout(
    target_sizes: list[str],
    family: str | None = None,
) -> dict[str, tuple[int, int, int, int]]:
    """
    Compute a deterministic layout for a single mixed contact sheet.

    Every supported size has one fixed slot on the sheet. Each panel is fit
    into that slot with aspect-ratio-preserving scaling only so the generated
    sheet remains easy to split with CV2.
    """
    inferred_family = family or MIXED_FAMILY
    ordered_sizes = _ordered_sizes_for_family(target_sizes, inferred_family)
    if inferred_family == HERO_FAMILY:
        slot_bounds = HERO_SLOT_BOUNDS
    elif inferred_family == BANNER_FAMILY:
        slot_bounds = BANNER_SLOT_BOUNDS
    else:
        slot_bounds = MIXED_SLOT_BOUNDS

    layout: dict[str, tuple[int, int, int, int]] = {}
    fallback_entries: list[tuple[str, int, int]] = []
    for size in ordered_sizes:
        width, height = _parse_size(size)
        if not width or not height:
            continue
        slot = slot_bounds.get(size)
        if slot:
            layout[size] = _fit_size_in_slot(width, height, slot)
        else:
            fallback_entries.append((size, width, height))

    if fallback_entries:
        fallback_layout = _fit_layout_in_bounds(
            fallback_entries,
            _fallback_bounds_for_family(inferred_family),
        )
        layout.update(fallback_layout)
    return layout


def build_contact_sheet_plans(target_sizes: list[str]) -> list[ContactSheetPlan]:
    mixed_sizes = _ordered_sizes_for_family(target_sizes, MIXED_FAMILY)
    if not mixed_sizes:
        return []
    return [
        ContactSheetPlan(
            family=MIXED_FAMILY,
            title="Contact Sheet",
            target_sizes=mixed_sizes,
            panel_layout=compute_panel_layout(mixed_sizes, family=MIXED_FAMILY),
        )
    ]


def _detect_components(img) -> list[dict]:
    width, height = img.size
    pixels = img.load()
    mask = bytearray(width * height)
    for y in range(height):
        row = y * width
        for x in range(width):
            r, g, b = pixels[x, y]
            if not (r >= 245 and g >= 245 and b >= 245):
                mask[row + x] = 1

    visited = bytearray(width * height)
    min_area = max(750, int(width * height * 0.002))
    components: list[dict] = []

    for start_y in range(height):
        for start_x in range(width):
            start = start_y * width + start_x
            if not mask[start] or visited[start]:
                continue

            stack = [(start_x, start_y)]
            visited[start] = 1
            min_x = max_x = start_x
            min_y = max_y = start_y
            area = 0

            while stack:
                x, y = stack.pop()
                area += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)

                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if nx < 0 or nx >= width or ny < 0 or ny >= height:
                        continue
                    idx = ny * width + nx
                    if mask[idx] and not visited[idx]:
                        visited[idx] = 1
                        stack.append((nx, ny))

            box_w = max_x - min_x + 1
            box_h = max_y - min_y + 1
            if area < min_area or box_w < 40 or box_h < 28:
                continue
            components.append(
                {
                    "bbox": (min_x, min_y, max_x + 1, max_y + 1),
                    "area": area,
                    "w": box_w,
                    "h": box_h,
                    "ratio": box_w / box_h,
                    "cx": min_x + box_w / 2.0,
                    "cy": min_y + box_h / 2.0,
                }
            )

    return sorted(components, key=lambda item: item["area"], reverse=True)


def _assignment_score(
    component: dict,
    expected_box: tuple[int, int, int, int],
    target_ratio: float,
) -> float:
    left, top, right, bottom = expected_box
    expected_cx = (left + right) / 2.0
    expected_cy = (top + bottom) / 2.0
    expected_w = max(1, right - left)
    expected_h = max(1, bottom - top)
    distance = abs(component["cx"] - expected_cx) / expected_w + abs(component["cy"] - expected_cy) / expected_h
    ratio_delta = abs(component["ratio"] - target_ratio) / max(target_ratio, 0.01)

    actual_left, actual_top, actual_right, actual_bottom = component["bbox"]
    inter_left = max(left, actual_left)
    inter_top = max(top, actual_top)
    inter_right = min(right, actual_right)
    inter_bottom = min(bottom, actual_bottom)
    inter_w = max(0, inter_right - inter_left)
    inter_h = max(0, inter_bottom - inter_top)
    inter_area = inter_w * inter_h
    expected_area = expected_w * expected_h
    actual_area = max(1, (actual_right - actual_left) * (actual_bottom - actual_top))
    union_area = expected_area + actual_area - inter_area
    iou = inter_area / union_area if union_area > 0 else 0.0
    return ratio_delta * 1.4 + distance * 1.1 + (1.0 - iou) * 0.6


def _component_from_expected_box(
    expected_box: tuple[int, int, int, int],
) -> dict:
    left, top, right, bottom = expected_box
    width = max(1, right - left)
    height = max(1, bottom - top)
    return {
        "bbox": expected_box,
        "area": width * height,
        "w": width,
        "h": height,
        "ratio": width / height,
        "cx": left + width / 2.0,
        "cy": top + height / 2.0,
    }


def _bbox_area(box: tuple[int, int, int, int]) -> int:
    return max(1, box[2] - box[0]) * max(1, box[3] - box[1])


def _bbox_iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    inter_left = max(a[0], b[0])
    inter_top = max(a[1], b[1])
    inter_right = min(a[2], b[2])
    inter_bottom = min(a[3], b[3])
    inter_w = max(0, inter_right - inter_left)
    inter_h = max(0, inter_bottom - inter_top)
    inter_area = inter_w * inter_h
    union_area = _bbox_area(a) + _bbox_area(b) - inter_area
    return inter_area / union_area if union_area > 0 else 0.0


def _mean_luma(img, left: int, top: int, right: int, bottom: int) -> float:
    left = max(0, min(left, img.width - 1))
    right = max(left + 1, min(right, img.width))
    top = max(0, min(top, img.height - 1))
    bottom = max(top + 1, min(bottom, img.height))
    sample = img.crop((left, top, right, bottom))
    pixels = list(sample.getdata())
    if not pixels:
        return 255.0
    return sum((r + g + b) / 3.0 for r, g, b in pixels) / len(pixels)


def _score_vertical_border(img, x: int, top: int, bottom: int, side: str) -> float:
    outside_width = 10
    border_width = 3
    inside_width = 14
    if side == "left":
        outside = _mean_luma(img, x - outside_width, top, x - 1, bottom)
        inside = _mean_luma(img, x + 2, top, x + 2 + inside_width, bottom)
    else:
        outside = _mean_luma(img, x + 1, top, x + 1 + outside_width, bottom)
        inside = _mean_luma(img, x - 1 - inside_width, top, x - 1, bottom)
    border = _mean_luma(img, x - border_width // 2, top, x + border_width // 2 + 1, bottom)
    return max(0.0, outside - border) + max(0.0, inside - border) * 0.35


def _score_horizontal_border(img, y: int, left: int, right: int, side: str) -> float:
    outside_height = 10
    border_height = 3
    inside_height = 14
    if side == "top":
        outside = _mean_luma(img, left, y - outside_height, right, y - 1)
        inside = _mean_luma(img, left, y + 2, right, y + 2 + inside_height)
    else:
        outside = _mean_luma(img, left, y + 1, right, y + 1 + outside_height)
        inside = _mean_luma(img, left, y - 1 - inside_height, right, y - 1)
    border = _mean_luma(img, left, y - border_height // 2, right, y + border_height // 2 + 1)
    return max(0.0, outside - border) + max(0.0, inside - border) * 0.35


def _find_best_line(candidates: range, scorer) -> tuple[int, float]:
    best_pos = None
    best_score = float("-inf")
    for pos in candidates:
        score = scorer(pos)
        if score > best_score:
            best_score = score
            best_pos = pos
    return (best_pos if best_pos is not None else candidates.start, best_score)


def _snap_expected_box_to_border(
    img,
    expected_box: tuple[int, int, int, int],
) -> tuple[tuple[int, int, int, int], dict[str, float]]:
    left, top, right, bottom = expected_box
    width = right - left
    height = bottom - top
    x_pad = min(96, max(18, width // 8))
    y_pad = min(72, max(18, height // 8))

    vertical_top = max(0, top - y_pad // 2)
    vertical_bottom = min(img.height, bottom + y_pad // 2)
    horizontal_left = max(0, left - x_pad // 2)
    horizontal_right = min(img.width, right + x_pad // 2)

    snapped_left, left_score = _find_best_line(
        range(max(1, left - x_pad), min(img.width - 1, left + x_pad) + 1),
        lambda x: _score_vertical_border(img, x, vertical_top, vertical_bottom, "left"),
    )
    snapped_right, right_score = _find_best_line(
        range(max(1, right - x_pad), min(img.width - 1, right + x_pad) + 1),
        lambda x: _score_vertical_border(img, x, vertical_top, vertical_bottom, "right"),
    )
    snapped_top, top_score = _find_best_line(
        range(max(1, top - y_pad), min(img.height - 1, top + y_pad) + 1),
        lambda y: _score_horizontal_border(img, y, horizontal_left, horizontal_right, "top"),
    )
    snapped_bottom, bottom_score = _find_best_line(
        range(max(1, bottom - y_pad), min(img.height - 1, bottom + y_pad) + 1),
        lambda y: _score_horizontal_border(img, y, horizontal_left, horizontal_right, "bottom"),
    )

    snapped_box = (
        max(0, min(snapped_left, img.width - 2)),
        max(0, min(snapped_top, img.height - 2)),
        max(1, min(snapped_right + 1, img.width)),
        max(1, min(snapped_bottom + 1, img.height)),
    )
    if snapped_box[2] <= snapped_box[0] + 12 or snapped_box[3] <= snapped_box[1] + 12:
        return expected_box, {
            "left_score": round(left_score, 3),
            "right_score": round(right_score, 3),
            "top_score": round(top_score, 3),
            "bottom_score": round(bottom_score, 3),
            "used_expected_fallback": 1.0,
        }
    return snapped_box, {
        "left_score": round(left_score, 3),
        "right_score": round(right_score, 3),
        "top_score": round(top_score, 3),
        "bottom_score": round(bottom_score, 3),
        "used_expected_fallback": 0.0,
    }


def _select_panel_component(
    img,
    remaining_components: list[dict],
    expected_box: tuple[int, int, int, int],
    target_ratio: float,
) -> tuple[dict, bool, float]:
    snapped_box, snap_debug = _snap_expected_box_to_border(img, expected_box)
    snapped_component = _component_from_expected_box(snapped_box)
    snapped_score = _assignment_score(snapped_component, expected_box, target_ratio)
    snapped_component["snap_debug"] = snap_debug

    if not remaining_components:
        return snapped_component, False, snapped_score

    scored = [
        (_assignment_score(component, expected_box, target_ratio), index, component)
        for index, component in enumerate(remaining_components)
    ]
    scored.sort(key=lambda item: item[0])
    best_score, best_index, best_component = scored[0]

    detected_area_ratio = _bbox_area(best_component["bbox"]) / max(1, _bbox_area(expected_box))
    detected_iou = _bbox_iou(best_component["bbox"], expected_box)

    # Prefer the snapped expected box unless a detected component is both close
    # and large enough to represent the full bordered panel instead of one art fragment.
    if best_score + 0.55 < snapped_score and detected_area_ratio >= 0.55 and detected_iou >= 0.28:
        remaining_components.pop(best_index)
        return best_component, True, best_score

    return snapped_component, False, snapped_score


def _distance_between_centers(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    acx = (a[0] + a[2]) / 2.0
    acy = (a[1] + a[3]) / 2.0
    bcx = (b[0] + b[2]) / 2.0
    bcy = (b[1] + b[3]) / 2.0
    return abs(acx - bcx) + abs(acy - bcy)


def _detect_panels_globally(
    bgr_image,
    requested: list[tuple[str, int, int, float]],
    panel_layout: dict[str, tuple[int, int, int, int]] | None = None,
) -> dict[str, tuple[int, int, int, int]]:
    """
    Global panel detection: scan the full image for non-white blobs,
    then match each blob to a target size by aspect ratio.

    Does NOT rely on expected slot coordinates — works regardless of where
    the model placed each panel.

    Matching strategy:
    - Primary discriminator: aspect ratio (±25% tolerance)
    - Tie-break: process largest native-area targets first so the bigger blob
      is claimed first (handles 640x100 vs 320x50 which share the same ratio)
    """
    import cv2
    import numpy as np

    img_h, img_w = bgr_image.shape[:2]

    # ── Step 1: isolate non-white pixels ─────────────────────────────────────
    # White background is very bright (>238 all channels).
    # Panel content, borders, and text are clearly non-white.
    gray = cv2.cvtColor(bgr_image, cv2.COLOR_BGR2GRAY)
    _, white_mask = cv2.threshold(gray, 238, 255, cv2.THRESH_BINARY)
    non_white = cv2.bitwise_not(white_mask)

    # ── Step 2: close gaps WITHIN panels ─────────────────────────────────────
    # A 20×20 kernel with 2 iterations fills internal gaps up to ~40 px.
    # Inter-panel gutters are 40–56 px so they remain separated.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 20))
    filled = cv2.morphologyEx(non_white, cv2.MORPH_CLOSE, kernel, iterations=2)

    # ── Step 3: find external contours ───────────────────────────────────────
    contours, _ = cv2.findContours(filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # ── Step 4: keep only substantial blobs (≥ 1.2 % of image area) ─────────
    min_area = img_w * img_h * 0.012
    blobs: list[dict] = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < min_area or w < 50 or h < 35:
            continue
        blobs.append({
            "bbox": (x, y, x + w, y + h),
            "area": area,
            "ratio": w / max(h, 1),
            "width": w,
        })

    if not blobs:
        return {}

    # ── Step 5: greedy matching (largest native area first) ───────────────────
    # Sorting by descending tw×th ensures that when two targets share the same
    # aspect ratio (e.g. 640×100 and 320×50 both ≈ 6.4), the larger one claims
    # the larger blob before the smaller one gets a chance.
    order = sorted(
        range(len(requested)),
        key=lambda i: requested[i][1] * requested[i][2],
        reverse=True,
    )
    used: set[int] = set()
    result: dict[str, tuple[int, int, int, int]] = {}

    # Build a lookup of expected slot positions for position-based penalty
    # (imported here to avoid circular imports)
    try:
        _slot_lookup = {**MIXED_SLOT_BOUNDS, **HERO_SLOT_BOUNDS, **BANNER_SLOT_BOUNDS}
    except Exception:
        _slot_lookup = {}

    max_native_w = max((tw for _, tw, _, _ in requested), default=1)

    for i in order:
        size, tw, th, target_ratio = requested[i]
        best_score = float("inf")
        best_bi = -1

        # Expected slot center (if known) for position penalty
        expected_box = panel_layout.get(size) if panel_layout else _slot_lookup.get(size)
        if expected_box:
            exp_cx = (expected_box[0] + expected_box[2]) / 2.0
            exp_cy = (expected_box[1] + expected_box[3]) / 2.0
        else:
            exp_cx = exp_cy = None

        for bi, blob in enumerate(blobs):
            if bi in used:
                continue

            ratio_delta = abs(blob["ratio"] - target_ratio) / max(target_ratio, 0.01)
            if ratio_delta > 0.25:          # 25% aspect-ratio tolerance
                continue

            # Width fraction: blobs for wider panels should be wider
            blob_w_frac = blob["width"] / img_w
            target_w_frac = tw / max_native_w
            w_delta = abs(blob_w_frac - target_w_frac)

            # Position penalty: blobs far from the expected slot are penalised.
            # Normalised by image diagonal so scale doesn't matter.
            # This prevents sub-blobs from wrong regions stealing the match.
            if exp_cx is not None:
                blob_cx = (blob["bbox"][0] + blob["bbox"][2]) / 2.0
                blob_cy = (blob["bbox"][1] + blob["bbox"][3]) / 2.0
                diag = (img_w ** 2 + img_h ** 2) ** 0.5
                pos_delta = ((blob_cx - exp_cx) ** 2 + (blob_cy - exp_cy) ** 2) ** 0.5 / diag
            else:
                pos_delta = 0.0

            score = ratio_delta * 2.0 + w_delta * 0.7 + pos_delta * 1.8
            if score < best_score:
                best_score = score
                best_bi = bi

        if best_bi >= 0:
            result[size] = blobs[best_bi]["bbox"]
            used.add(best_bi)

    return result


def split_contact_sheet(
    image_bytes: bytes,
    target_sizes: list[str],
    panel_layout: dict[str, tuple[int, int, int, int]] | None = None,
) -> tuple[dict[str, ContactSheetPanel], dict]:
    """Split a fixed-template contact sheet into exact-size image assets."""
    from PIL import Image
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "OpenCV is required for contact-sheet split. "
            "Install it into services/api/.venv with: "
            r"services\api\.venv\Scripts\python.exe -m pip install opencv-python-headless"
        ) from exc

    if panel_layout is None:
        panel_layout = compute_panel_layout(target_sizes)

    requested: list[tuple[str, int, int, float]] = []
    for size in target_sizes:
        width, height = _parse_size(size)
        if width and height:
            requested.append((size, width, height, width / height))
    if not requested:
        return {}, {"status": "failed", "reason": "no_valid_target_sizes"}

    with Image.open(io.BytesIO(image_bytes)) as source:
        rgba = source.convert("RGBA")
        rgb = rgba.convert("RGB")

    bgr = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        return {}, {"status": "failed", "reason": "cv2_decode_failed"}

    # ── Pre-processing: erase small dark label badges ─────────────────────
    # The model sometimes adds small dimension labels (e.g. "320x50") as dark
    # pills near panel borders.  These are typically very small (<0.4% of image)
    # and very dark (mean BGR < 80).  Fill them with white before detection.
    img_h_pre, img_w_pre = bgr.shape[:2]
    gray_pre = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    _, very_dark = cv2.threshold(gray_pre, 80, 255, cv2.THRESH_BINARY_INV)
    label_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    very_dark = cv2.morphologyEx(very_dark, cv2.MORPH_CLOSE, label_kernel, iterations=1)
    label_contours, _ = cv2.findContours(very_dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    max_label_area = img_w_pre * img_h_pre * 0.004   # labels < 0.4 % of image
    for lc in label_contours:
        x, y, w, h = cv2.boundingRect(lc)
        if w * h < max_label_area and max(w, h) < 400:
            bgr[y:y + h, x:x + w] = 255   # fill with white

    # ── Global detection: find panels anywhere in the image ──────────────────
    detected_bboxes = _detect_panels_globally(bgr, requested, panel_layout=panel_layout)
    fallback_count = 0

    panels: dict[str, ContactSheetPanel] = {}
    panel_debug: dict[str, dict] = {}

    for size, target_w, target_h, target_ratio in requested:
        # Prefer globally detected bbox; fall back to expected slot only if needed
        bbox = detected_bboxes.get(size)
        used_detected = bbox is not None
        if bbox is None:
            bbox = panel_layout.get(size)
            fallback_count += 1
        if bbox is None:
            continue

        left, top, right, bottom = bbox
        panel_w = max(1, right - left)
        panel_h = max(1, bottom - top)

        # Tiny inset to trim any residual border pixels
        inset = min(8, max(2, min(panel_w, panel_h) // 60))
        crop_box = (
            min(max(left + inset, 0), rgb.width),
            min(max(top + inset, 0), rgb.height),
            min(max(right - inset, 0), rgb.width),
            min(max(bottom - inset, 0), rgb.height),
        )
        if crop_box[2] <= crop_box[0] or crop_box[3] <= crop_box[1]:
            continue

        panel = rgba.crop(crop_box).resize((target_w, target_h), Image.Resampling.LANCZOS)
        src_ratio = panel_w / max(panel_h, 1)
        score = abs(src_ratio - target_ratio) / max(target_ratio, 0.01)

        panels[size] = ContactSheetPanel(
            target_size=size,
            image_bytes=_to_png(panel),
            bbox=bbox,
            source_ratio=round(src_ratio, 4),
            target_ratio=target_ratio,
            score=score,
        )
        panel_debug[size] = {
            "bbox": list(bbox),
            "expected_bbox": list(panel_layout.get(size) or []),
            "source_ratio": round(src_ratio, 4),
            "target_ratio": round(target_ratio, 4),
            "score": round(score, 4),
            "used_global_detection": used_detected,
        }

    missing = [size for size, _, _, _ in requested if size not in panels]
    if missing:
        return {}, {"status": "failed", "reason": "missing_after_crop", "missing": missing}

    return panels, {
        "status": "passed",
        "mode": "global_detection_split",
        "sheet_size": [rgb.width, rgb.height],
        "panels_requested": len(requested),
        "panels_detected_globally": len(detected_bboxes),
        "panels_from_fallback": fallback_count,
        "panels": panel_debug,
    }


def annotate_contact_sheet(
    image_bytes: bytes,
    split_report: dict,
) -> bytes:
    """Overlay deterministic size labels on top of the contact sheet preview."""
    from PIL import Image, ImageDraw, ImageFont

    with Image.open(io.BytesIO(image_bytes)) as source:
        canvas = source.convert("RGBA")

    draw = ImageDraw.Draw(canvas, "RGBA")
    font = ImageFont.load_default()

    panels = split_report.get("panels", {}) if isinstance(split_report, dict) else {}
    panel_layout = split_report.get("panel_layout", {}) if isinstance(split_report, dict) else {}
    requested_sizes = split_report.get("requested_sizes", []) if isinstance(split_report, dict) else []

    labeled_boxes: dict[str, list[int]] = {}
    for size, panel_data in panels.items():
        bbox = panel_data.get("bbox") if isinstance(panel_data, dict) else None
        if isinstance(bbox, list) and len(bbox) == 4:
            labeled_boxes[size] = bbox

    for size in requested_sizes:
        if size in labeled_boxes:
            continue
        expected = panel_layout.get(size) if isinstance(panel_layout, dict) else None
        if isinstance(expected, list) and len(expected) == 4:
            labeled_boxes[size] = expected

    for size, bbox in labeled_boxes.items():
        left, top, _, _ = bbox
        text = size
        text_box = draw.textbbox((0, 0), text, font=font)
        text_w = text_box[2] - text_box[0]
        text_h = text_box[3] - text_box[1]
        chip_left = max(8, left + 8)
        chip_top = max(8, top + 8)
        chip_right = chip_left + text_w + 14
        chip_bottom = chip_top + text_h + 10
        draw.rounded_rectangle(
            (chip_left, chip_top, chip_right, chip_bottom),
            radius=10,
            fill=(10, 17, 31, 210),
            outline=(255, 255, 255, 80),
            width=1,
        )
        draw.text((chip_left + 7, chip_top + 5), text, fill=(255, 255, 255, 255), font=font)

    return _to_png(canvas)
