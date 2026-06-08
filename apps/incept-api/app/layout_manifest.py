from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.anchor_types import HARD_REQUIRED_ANCHOR_ROLES, normalize_anchor_role


@dataclass(frozen=True)
class AnchorBox:
    x_pct: float
    y_pct: float
    w_pct: float
    h_pct: float


@dataclass(frozen=True)
class LayoutAnchor:
    id: str
    role: str
    label: str
    bbox: AnchorBox
    must_preserve: bool = False
    priority: int = 50
    confidence: str = "medium"


@dataclass(frozen=True)
class BackgroundSafeRegion:
    x_pct: float
    y_pct: float
    w_pct: float
    h_pct: float


@dataclass
class LayoutManifest:
    source_asset_id: str | None
    source_size: dict[str, int]
    anchors: list[LayoutAnchor] = field(default_factory=list)
    background_safe_regions: list[BackgroundSafeRegion] = field(default_factory=list)
    analysis_version: str = "multi_size_renderer_v1"
    confidence_summary: dict[str, Any] = field(default_factory=dict)
    ocr: dict[str, Any] = field(default_factory=dict)
    detection: dict[str, Any] = field(default_factory=dict)
    task_manifest: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_asset_id": self.source_asset_id,
            "source_size": dict(self.source_size),
            "anchors": [asdict(anchor) for anchor in self.anchors],
            "background_safe_regions": [asdict(region) for region in self.background_safe_regions],
            "analysis_version": self.analysis_version,
            "confidence_summary": dict(self.confidence_summary),
            "ocr": dict(self.ocr),
            "detection": dict(self.detection),
            "task_manifest": dict(self.task_manifest or {}),
        }

    def to_detection_payload(self) -> list[dict[str, Any]]:
        payload: list[dict[str, Any]] = []
        for anchor in self.anchors:
            role = anchor.role
            if role == "hero_subject":
                continue
            payload.append(
                {
                    "type": role,
                    "label": anchor.label,
                    "confidence": anchor.confidence,
                    "required": anchor.must_preserve,
                    "bbox": asdict(anchor.bbox),
                }
            )
        return payload


def build_layout_manifest(
    *,
    source_asset_id: str | None,
    source_width: int,
    source_height: int,
    detected_anchors: list[dict[str, Any]],
    task_manifest: dict[str, Any] | None = None,
    detection_source: str = "unknown",
    ocr_status: str = "not_implemented",
) -> LayoutManifest:
    anchors: list[LayoutAnchor] = []
    role_counts: dict[str, int] = {}

    for item in detected_anchors:
        bbox = item.get("bbox") if isinstance(item.get("bbox"), dict) else item
        role = normalize_anchor_role(str(item.get("type") or item.get("role") or item.get("label") or ""))
        try:
            x_pct = max(0.0, min(1.0, float(bbox.get("x_pct", 0.0))))
            y_pct = max(0.0, min(1.0, float(bbox.get("y_pct", 0.0))))
            w_pct = max(0.0, min(1.0, float(bbox.get("w_pct", 0.0))))
            h_pct = max(0.0, min(1.0, float(bbox.get("h_pct", 0.0))))
        except (TypeError, ValueError):
            continue
        if w_pct <= 0 or h_pct <= 0:
            continue

        role_counts[role] = role_counts.get(role, 0) + 1
        anchors.append(
            LayoutAnchor(
                id=f"{role}_{role_counts[role]}",
                role=role,
                label=str(item.get("label") or role),
                bbox=AnchorBox(x_pct=x_pct, y_pct=y_pct, w_pct=w_pct, h_pct=h_pct),
                must_preserve=bool(item.get("required", role in HARD_REQUIRED_ANCHOR_ROLES)),
                priority=_priority_for_role(role),
                confidence=str(item.get("confidence") or "medium"),
            )
        )

    if not anchors:
        anchors.append(
            LayoutAnchor(
                id="hero_subject_1",
                role="hero_subject",
                label="full_scene",
                bbox=AnchorBox(x_pct=0.0, y_pct=0.0, w_pct=1.0, h_pct=1.0),
                must_preserve=True,
                priority=90,
                confidence="fallback",
            )
        )

    safe_regions = _build_background_safe_regions(anchors)
    confidence_summary = {
        "anchor_count": len(anchors),
        "high_confidence_count": sum(1 for anchor in anchors if anchor.confidence == "high"),
        "required_anchor_count": sum(1 for anchor in anchors if anchor.must_preserve),
    }

    return LayoutManifest(
        source_asset_id=source_asset_id,
        source_size={"w": source_width, "h": source_height},
        anchors=anchors,
        background_safe_regions=safe_regions,
        confidence_summary=confidence_summary,
        ocr={"status": ocr_status},
        detection={"source": detection_source},
        task_manifest=task_manifest,
    )


def _priority_for_role(role: str) -> int:
    if role == "logo":
        return 100
    if role == "cta":
        return 96
    if role == "headline_block":
        return 92
    if role in {"character_face", "character_head", "hero_subject"}:
        return 90
    if role == "product":
        return 88
    return 50


def _build_background_safe_regions(anchors: list[LayoutAnchor]) -> list[BackgroundSafeRegion]:
    if not anchors:
        return []
    left = min(anchor.bbox.x_pct for anchor in anchors)
    top = min(anchor.bbox.y_pct for anchor in anchors)
    right = max(anchor.bbox.x_pct + anchor.bbox.w_pct for anchor in anchors)
    bottom = max(anchor.bbox.y_pct + anchor.bbox.h_pct for anchor in anchors)

    regions: list[BackgroundSafeRegion] = []
    if left > 0.08:
        regions.append(BackgroundSafeRegion(x_pct=0.0, y_pct=0.0, w_pct=max(0.0, left), h_pct=1.0))
    if right < 0.92:
        regions.append(BackgroundSafeRegion(x_pct=min(1.0, right), y_pct=0.0, w_pct=max(0.0, 1.0 - right), h_pct=1.0))
    if top > 0.08:
        regions.append(BackgroundSafeRegion(x_pct=0.0, y_pct=0.0, w_pct=1.0, h_pct=max(0.0, top)))
    if bottom < 0.92:
        regions.append(BackgroundSafeRegion(x_pct=0.0, y_pct=min(1.0, bottom), w_pct=1.0, h_pct=max(0.0, 1.0 - bottom)))
    return regions
