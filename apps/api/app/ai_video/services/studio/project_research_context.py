from __future__ import annotations

from app.ai_video.models.studio import ProjectResearch


def format_approved_creative_brief(research: ProjectResearch | None) -> str:
    """Render only approved, user-governed direction into generation context."""
    if research is None or research.status != "approved" or not research.approved_direction_id:
        return ""
    direction = next(
        (
            item
            for item in research.creative_directions
            if isinstance(item, dict) and item.get("id") == research.approved_direction_id
        ),
        None,
    )
    if direction is None:
        return ""
    brief = research.brief if isinstance(research.brief, dict) else {}
    fields = [
        ("Advertiser vertical", brief.get("advertiser_vertical")),
        ("Delivery channel", brief.get("delivery_channel")),
        ("Market", brief.get("market")),
        ("Creative direction", direction.get("name")),
        ("Creative format", direction.get("creative_format")),
        ("Creative playbook", direction.get("creative_playbook")),
        ("Visual direction", direction.get("visual_direction")),
        ("Script direction", direction.get("script_direction")),
        ("Rationale", direction.get("rationale")),
    ]
    lines = [
        "Approved advertising creative brief (production authority):",
        *(f"- {label}: {value}" for label, value in fields if value not in (None, "")),
        "- References are inspiration evidence only. Do not copy scenes, branding, or protected expression.",
        "- Do not invent product claims that are not supported by approved project evidence.",
    ]
    return "\n".join(lines)


__all__ = ["format_approved_creative_brief"]
