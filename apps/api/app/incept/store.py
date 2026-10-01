import base64
import json
import logging
import mimetypes
import re
from collections.abc import Iterator
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from app.incept.bigquery_store import persist_generation
from app.incept.config import get_settings
from app.incept.db import delete_asset as db_delete_asset, init_db, load_assets, load_job, load_jobs, load_theme_create_presets, load_theme_create_reports, load_usage_events, upsert_asset, upsert_job, upsert_theme_create_preset, upsert_theme_create_report, upsert_usage_event
from app.incept.datetime_utils import utcnow_naive
from app.incept.models import Asset, AssetRole, AddTextRequest, CreativeThread, GenerateGifRequest, GenerationJob, GenerationMode, GenerationRequest, ImageEditRequest, JobStatus, KakaoBizboardComposeRequest, OutpaintRequest, RemediationAnalysisRequest, RemediationAnalysisResponse, RemediationAnalysisResult, RemediationViolation, RemoveBGRequest, ThemeCreatePreset, ThemeCreatePresetCreateRequest, ThemeCreatePresetFromReportRequest, ThemeCreateStyleReport, ThemeCreateStyleReportCreateRequest, ThemeCreateStyleReportDraftRequest, UsageEvent, User, Workspace
from app.incept.prompt_builder import (
    build_generation_prompt,
    build_image_remediation_prompt,
    build_reference_generation_prompt,
    build_resize_prompt,
    build_theme_create_style_modify_prompt,
    build_theme_create_style_transfer_prompt,
)
from app.incept import thread_store

logger = logging.getLogger(__name__)

KAKAO_CLEAN_PROMPT = "\n".join([
    "Please remove the text and UI elements from this image and fill the background naturally.",
])

STATIC_ROOT = Path(__file__).parent.parent.parent / "static"
STATIC_DIR = STATIC_ROOT / "generated"
UPLOAD_DIR = STATIC_ROOT / "uploads"
_GCS_CLIENT = None
_UPLOAD_SAFE_JPEG_SIZES = {"1200x628", "1200x600", "720x720"}
_RESIZE_GACHA_DISCLOSURE_SIZES = {"1200x628", "1200x600"}
_UPLOAD_SAFE_JPEG_MAX_BYTES = 500 * 1024
_MAX_PSD_RASTER_PIXELS = 64_000_000
_NON_RASTER_UPLOAD_EXTENSIONS = {".ai", ".pdf", ".svg"}
_GENERATED_TITLE_SUFFIX_PATTERNS = (
    re.compile(r"\s*-\s*resize\b.*$", re.IGNORECASE),
    re.compile(r"\s*-\s*theme create\b.*$", re.IGNORECASE),
    re.compile(r"\s*-\s*image remediation\b.*$", re.IGNORECASE),
    re.compile(r"\s*-\s*kakao bizboard\b.*$", re.IGNORECASE),
    re.compile(r"\s*-\s*kakao clean\b.*$", re.IGNORECASE),
    re.compile(r"[_\-\s]?kakao_clean\d+$", re.IGNORECASE),
    re.compile(r"[_\-\s]?kakao\d+$", re.IGNORECASE),
    re.compile(r"[_\-\s]?remediation\d+$", re.IGNORECASE),
    re.compile(r"[_\-\s]?gif\d+$", re.IGNORECASE),
    re.compile(r"[_\-\s]?video\d+$", re.IGNORECASE),
    re.compile(r"[_\-\s]?\d+x\d+v\d+$", re.IGNORECASE),
    re.compile(r"[_\-\s]?v\d+$", re.IGNORECASE),
)

# ── Projects (formerly "workspaces") ─────────────────────────────────────────
WORKSPACES: dict[str, Workspace] = {
    "wsp_q2": Workspace(
        id="wsp_q2",
        title="Q2 Campaign Assets",
        description="Lifestyle image variants for skincare launch.",
        owner_user_id="usr_jane",
        team="IM GM",
        status=JobStatus.running,
        updated_at=utcnow_naive(),
    ),
    "wsp_tiktok": Workspace(
        id="wsp_tiktok",
        title="TikTok Creatives",
        description="Short-form references, hooks, and GIF variants.",
        owner_user_id="usr_jane",
        team="Creative Studio",
        status=JobStatus.pending,
        updated_at=utcnow_naive(),
    ),
}

JOBS: dict[str, GenerationJob] = {}
ASSETS: dict[str, Asset] = {}
USAGE_EVENTS: dict[str, UsageEvent] = {}
SOURCE_ASSETS: dict[str, Asset] = {}
THEME_CREATE_REPORTS: dict[str, ThemeCreateStyleReport] = {}
THEME_CREATE_PRESETS: dict[str, ThemeCreatePreset] = {}

_LEGACY_ASSET_ROLES = {role.value for role in AssetRole}


def _coerce_asset_role(value: str | None, provider: str = "", theme: str | None = None) -> AssetRole:
    raw = (value or "").strip()
    if raw in _LEGACY_ASSET_ROLES:
        return AssetRole(raw)

    legacy_theme = (theme or "").strip()
    if legacy_theme in _LEGACY_ASSET_ROLES:
        return AssetRole(legacy_theme)

    if provider == "upload":
        return AssetRole.upload
    return AssetRole.generated


def _normalized_source_title(title: str | None) -> str:
    base_title = Path(title or "").stem.strip()
    if not base_title:
        return ""

    cleaned = base_title
    previous = None
    while cleaned and cleaned != previous:
        previous = cleaned
        for pattern in _GENERATED_TITLE_SUFFIX_PATTERNS:
            cleaned = pattern.sub("", cleaned).strip(" _-")

    return cleaned or base_title

# ── Bootstrap: init DB and load persisted data into memory ───────────────────
def _job_from_row(row: dict) -> GenerationJob:
    return GenerationJob(
        job_id=row["job_id"],
        workspace_id=row["workspace_id"],
        status=JobStatus(row["status"]),
        progress=row["progress"],
        lineage_key=row["lineage_key"] or "",
        message=row["message"] or "",
        tool_id=row["tool_id"] or "",
        title=row["title"] or "",
        output_asset_ids=json.loads(row["output_asset_ids"] or "[]"),
        thread_id=row.get("thread_id"),
        source_asset_id=row.get("source_asset_id"),
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _bootstrap() -> None:
    from app.incept.db import restore_db_from_gcs
    restore_db_from_gcs()
    init_db()
    for row in load_jobs():
        try:
            job = _job_from_row(row)
            JOBS[job.job_id] = job
        except Exception:
            logger.warning("Skipping corrupt job row: %s", row.get("job_id"))

    for row in load_assets():
        try:
            asset = Asset(
                id=row["id"],
                title=row["title"] or "",
                type=row["type"] or "image",
                gcs_uri=row["gcs_uri"] or "",
                preview_url=row["preview_url"] or "",
                provider=row["provider"] or "",
                model=row["model"] or "",
                workspace_id=row["workspace_id"] or "",
                job_id=row["job_id"] or "",
                prompt_hash=row["prompt_hash"] or "",
                created_by=row["created_by"] or "",
                created_at=datetime.fromisoformat(row["created_at"]),
                width=row["width"],
                height=row["height"],
                theme=None if (row["theme"] or "") in _LEGACY_ASSET_ROLES else row["theme"],
                asset_role=_coerce_asset_role(
                    row.get("asset_role") if isinstance(row, dict) else row["asset_role"],
                    provider=row["provider"] or "",
                    theme=row["theme"],
                ),
                analysis=__import__("json").loads(row["analysis_json"]) if row.get("analysis_json") else None,
                thread_id=row.get("thread_id"),
                parent_asset_id=row.get("parent_asset_id"),
                root_asset_id=row.get("root_asset_id"),
            )
            ASSETS[asset.id] = asset
        except Exception:
            logger.warning("Skipping corrupt asset row: %s", row.get("id"))

    for row in load_theme_create_reports():
        try:
            report = ThemeCreateStyleReport(
                report_id=row["report_id"],
                workspace_id=row["workspace_id"] or "",
                title=row["title"] or "",
                summary=row["summary"] or "",
                theme_create_mode=row["theme_create_mode"] or "style_modify",
                prompt_template=row["prompt_template"] or "",
                source_asset_id=row["source_asset_id"],
                reference_asset_ids=__import__("json").loads(row["reference_asset_ids"] or "[]"),
                source_job_id=row["source_job_id"],
                recommended_preset_name=row["recommended_preset_name"],
                visual_dna=__import__("json").loads(row["visual_dna_json"] or "[]"),
                composition_rules=__import__("json").loads(row["composition_rules_json"] or "[]"),
                do_not_copy=__import__("json").loads(row["do_not_copy_json"] or "[]"),
                tags=__import__("json").loads(row["tags_json"] or "[]"),
                taxonomy=__import__("json").loads(row["taxonomy_json"] or "{}"),
                created_by=row["created_by"] or "",
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            THEME_CREATE_REPORTS[report.report_id] = report
        except Exception:
            logger.warning("Skipping corrupt theme report row: %s", row.get("report_id"))

    for row in load_theme_create_presets():
        try:
            preset = ThemeCreatePreset(
                preset_id=row["preset_id"],
                name=row["name"] or "",
                description=row["description"] or "",
                theme_create_mode=row["theme_create_mode"] or "style_modify",
                visibility=row["visibility"] or "team",
                prompt_template=row["prompt_template"] or "",
                style_name=row["style_name"],
                style_details=row["style_details"],
                workspace_id=row["workspace_id"],
                tags=__import__("json").loads(row["tags_json"] or "[]"),
                taxonomy=__import__("json").loads(row["taxonomy_json"] or "{}"),
                source_report_id=row["source_report_id"],
                source_job_id=row["source_job_id"],
                source_asset_id=row["source_asset_id"],
                created_by=row["created_by"] or "",
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
                usage_count=int(row["usage_count"] or 0),
                is_official=bool(row["is_official"]),
            )
            THEME_CREATE_PRESETS[preset.preset_id] = preset
        except Exception:
            logger.warning("Skipping corrupt theme preset row: %s", row.get("preset_id"))

    for row in load_usage_events():
        try:
            event = UsageEvent(
                id=row["id"],
                job_id=row["job_id"] or "",
                workspace_id=row["workspace_id"] or "",
                user_id=row["user_id"] or "",
                user_email=row["user_email"] or "",
                provider=row["provider"] or "",
                model=row["model"] or "",
                operation=row["operation"] or "",
                prompt_hash=row["prompt_hash"] or "",
                variants=row["variants"] or 0,
                output_size_count=row["output_size_count"] or 0,
                output_format=row["output_format"] or "",
                estimated_provider_generations=row["estimated_provider_generations"] or 0,
                output_asset_count=row["output_asset_count"] or 0,
                estimated_cost_usd=row["estimated_cost_usd"] or 0.0,
                actual_cost_usd=row["actual_cost_usd"],
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            USAGE_EVENTS[event.id] = event
        except Exception:
            logger.warning("Skipping corrupt usage_event row: %s", row.get("id"))

    thread_store.backfill_legacy_threads(list(JOBS.values()), list(ASSETS.values()) + list(SOURCE_ASSETS.values()))
    for job in JOBS.values():
        if job.thread_id:
            upsert_job(job)
    for asset in list(ASSETS.values()) + list(SOURCE_ASSETS.values()):
        if asset.thread_id or asset.parent_asset_id or asset.root_asset_id:
            upsert_asset(asset)

_bootstrap()


def list_theme_create_reports(
    workspace_id: str | None = None,
    mode: str | None = None,
) -> list[ThemeCreateStyleReport]:
    reports = list(THEME_CREATE_REPORTS.values())
    if workspace_id:
        reports = [report for report in reports if report.workspace_id == workspace_id]
    if mode:
        reports = [report for report in reports if report.theme_create_mode.value == mode]
    return sorted(reports, key=lambda report: report.updated_at, reverse=True)


def create_theme_create_report(request: ThemeCreateStyleReportCreateRequest) -> ThemeCreateStyleReport:
    now = utcnow_naive()
    report = ThemeCreateStyleReport(
        report_id=f"tcr_{uuid4().hex[:12]}",
        workspace_id=request.workspace_id,
        title=request.title.strip() or "Untitled style report",
        summary=request.summary.strip(),
        theme_create_mode=request.theme_create_mode,
        prompt_template=request.prompt_template.strip(),
        source_asset_id=request.source_asset_id,
        reference_asset_ids=[asset_id for asset_id in request.reference_asset_ids if asset_id],
        source_job_id=request.source_job_id,
        recommended_preset_name=(request.recommended_preset_name or "").strip() or None,
        visual_dna=[item.strip() for item in request.visual_dna if item.strip()],
        composition_rules=[item.strip() for item in request.composition_rules if item.strip()],
        do_not_copy=[item.strip() for item in request.do_not_copy if item.strip()],
        tags=[item.strip() for item in request.tags if item.strip()],
        taxonomy={key: [item.strip() for item in values if item.strip()] for key, values in request.taxonomy.items() if key.strip()},
        created_by=request.created_by,
        created_at=now,
        updated_at=now,
    )
    THEME_CREATE_REPORTS[report.report_id] = report
    upsert_theme_create_report(report)
    return report


def list_theme_create_presets(
    workspace_id: str | None = None,
    mode: str | None = None,
) -> list[ThemeCreatePreset]:
    presets = list(THEME_CREATE_PRESETS.values())
    if workspace_id:
        presets = [
            preset for preset in presets
            if preset.workspace_id in (None, "", workspace_id)
        ]
    if mode:
        presets = [preset for preset in presets if preset.theme_create_mode.value == mode]
    return sorted(
        presets,
        key=lambda preset: (preset.is_official, preset.updated_at),
        reverse=True,
    )


def create_theme_create_preset(request: ThemeCreatePresetCreateRequest) -> ThemeCreatePreset:
    now = utcnow_naive()
    preset = ThemeCreatePreset(
        preset_id=f"tcp_{uuid4().hex[:12]}",
        name=request.name.strip() or "Untitled preset",
        description=request.description.strip(),
        theme_create_mode=request.theme_create_mode,
        visibility=request.visibility,
        prompt_template=request.prompt_template.strip(),
        style_name=(request.style_name or "").strip() or None,
        style_details=(request.style_details or "").strip() or None,
        workspace_id=(request.workspace_id or "").strip() or None,
        tags=[item.strip() for item in request.tags if item.strip()],
        taxonomy={key: [item.strip() for item in values if item.strip()] for key, values in request.taxonomy.items() if key.strip()},
        source_report_id=request.source_report_id,
        source_job_id=request.source_job_id,
        source_asset_id=request.source_asset_id,
        created_by=request.created_by,
        created_at=now,
        updated_at=now,
    )
    THEME_CREATE_PRESETS[preset.preset_id] = preset
    upsert_theme_create_preset(preset)
    return preset


def create_theme_create_preset_from_report(
    report_id: str,
    request: ThemeCreatePresetFromReportRequest,
    created_by: str,
) -> ThemeCreatePreset | None:
    report = THEME_CREATE_REPORTS.get(report_id)
    if not report:
        return None
    preset_request = ThemeCreatePresetCreateRequest(
        name=request.name,
        description=request.description,
        theme_create_mode=report.theme_create_mode,
        visibility=request.visibility,
        prompt_template=report.prompt_template,
        style_name=request.style_name or report.recommended_preset_name,
        style_details=request.style_details or report.summary,
        workspace_id=report.workspace_id,
        tags=report.tags,
        taxonomy=report.taxonomy,
        source_report_id=report.report_id,
        source_job_id=report.source_job_id,
        source_asset_id=report.source_asset_id,
        created_by=created_by,
    )
    return create_theme_create_preset(preset_request)


def draft_theme_create_report(
    request: ThemeCreateStyleReportDraftRequest,
    created_by: str,
) -> ThemeCreateStyleReportCreateRequest:
    from google import genai
    from google.genai import types as genai_types

    settings = get_settings()
    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )

    source_asset = ASSETS.get(request.source_asset_id) or SOURCE_ASSETS.get(request.source_asset_id)
    if not source_asset:
        raise RuntimeError("Source asset not found for report draft")

    source_bytes = _load_asset_bytes(source_asset)
    if not source_bytes:
        raise RuntimeError("Could not read source asset bytes for report draft")

    parts: list[genai_types.Part] = [
        genai_types.Part.from_text(text=(
            "You are a creative strategist helping a GM convert a successful creative workflow into a reusable preset.\n"
            "Analyze the supplied image set and workflow metadata.\n"
            "Return only valid JSON.\n\n"
            f"theme_create_mode: {request.theme_create_mode.value}\n"
            f"prompt_template: {request.prompt_template}\n"
            f"style_name: {request.style_name or ''}\n"
            f"style_details: {request.style_details or ''}\n"
            f"logo_position: {request.logo_position or ''}\n"
            f"element_position: {request.element_position or ''}\n"
            f"old_text: {request.old_text or ''}\n"
            f"new_text: {request.new_text or ''}\n"
            f"font_style: {request.font_style or ''}\n\n"
            "Summarize reusable visual DNA, composition rules, and anti-copy constraints.\n"
            "Taxonomy keys must be limited to: vertical, medium, campaign, workflow.\n"
        )),
        genai_types.Part.from_bytes(data=source_bytes, mime_type="image/png"),
    ]

    for asset_id in request.reference_asset_ids[:3]:
        asset = ASSETS.get(asset_id) or SOURCE_ASSETS.get(asset_id)
        if not asset:
            continue
        image_bytes = _load_asset_bytes(asset)
        if not image_bytes:
            continue
        parts.append(genai_types.Part.from_bytes(data=image_bytes, mime_type="image/png"))

    response_schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "recommended_preset_name": {"type": "string"},
            "visual_dna": {"type": "array", "items": {"type": "string"}},
            "composition_rules": {"type": "array", "items": {"type": "string"}},
            "do_not_copy": {"type": "array", "items": {"type": "string"}},
            "tags": {"type": "array", "items": {"type": "string"}},
            "taxonomy": {
                "type": "object",
                "properties": {
                    "vertical": {"type": "array", "items": {"type": "string"}},
                    "medium": {"type": "array", "items": {"type": "string"}},
                    "campaign": {"type": "array", "items": {"type": "string"}},
                    "workflow": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "required": ["title", "summary", "recommended_preset_name", "visual_dna", "composition_rules", "do_not_copy", "tags", "taxonomy"],
    }

    response = client.models.generate_content(
        model=settings.vertex_gemini_model,
        contents=[genai_types.Content(role="user", parts=parts)],
        config=genai_types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0.3,
        ),
    )

    data = json.loads(response.text or "{}")
    return ThemeCreateStyleReportCreateRequest(
        workspace_id=request.workspace_id,
        title=(data.get("title") or request.style_name or "Theme Create Style Report").strip(),
        summary=(data.get("summary") or "").strip(),
        theme_create_mode=request.theme_create_mode,
        prompt_template=request.prompt_template.strip(),
        source_asset_id=request.source_asset_id,
        reference_asset_ids=request.reference_asset_ids,
        recommended_preset_name=(data.get("recommended_preset_name") or request.style_name or "").strip() or None,
        visual_dna=[item.strip() for item in data.get("visual_dna", []) if isinstance(item, str) and item.strip()],
        composition_rules=[item.strip() for item in data.get("composition_rules", []) if isinstance(item, str) and item.strip()],
        do_not_copy=[item.strip() for item in data.get("do_not_copy", []) if isinstance(item, str) and item.strip()],
        tags=[item.strip() for item in data.get("tags", []) if isinstance(item, str) and item.strip()],
        taxonomy={
            key: [item.strip() for item in values if isinstance(item, str) and item.strip()]
            for key, values in (data.get("taxonomy", {}) or {}).items()
            if isinstance(key, str) and isinstance(values, list)
        },
        created_by=created_by,
    )


def _guess_asset_mime_type(asset: Asset) -> str:
    suffix = guess_asset_extension(asset).lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/png"


def _build_remediation_analysis_summary(result: RemediationAnalysisResult) -> str:
    lines = [
        f"- Asset summary: {result.summary}",
        f"- Overall risk: {result.overall_risk}",
    ]
    if result.preserve_instructions:
        lines.append("- Preserve instructions:")
        lines.extend(f"  - {item}" for item in result.preserve_instructions)
    if result.violations:
        lines.append("- Violations to fix:")
        for violation in result.violations:
            lines.extend([
                f"  - Category: {violation.category}",
                f"    Severity: {violation.severity}",
                f"    Target: {violation.target}",
                f"    Reason: {violation.reason}",
                f"    Fix: {violation.fix_instruction}",
            ])
    if result.remediation_prompt.strip():
        lines.append(f"- Consolidated remediation instruction: {result.remediation_prompt.strip()}")
    return "\n".join(lines)


def analyze_remediation_assets(
    request: RemediationAnalysisRequest,
    created_by: str,
) -> RemediationAnalysisResponse:
    from google import genai
    from google.genai import types as genai_types

    settings = get_settings()
    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )

    response_schema = {
        "type": "object",
        "properties": {
            "overall_risk": {"type": "string"},
            "summary": {"type": "string"},
            "preserve_instructions": {"type": "array", "items": {"type": "string"}},
            "violations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category": {"type": "string"},
                        "severity": {"type": "string"},
                        "target": {"type": "string"},
                        "reason": {"type": "string"},
                        "fix_instruction": {"type": "string"},
                    },
                    "required": ["category", "severity", "target", "reason", "fix_instruction"],
                },
            },
            "remediation_prompt": {"type": "string"},
        },
        "required": ["overall_risk", "summary", "preserve_instructions", "violations", "remediation_prompt"],
    }

    results: list[RemediationAnalysisResult] = []
    for asset_id in request.source_asset_ids:
        asset = ASSETS.get(asset_id) or SOURCE_ASSETS.get(asset_id)
        if not asset:
            raise RuntimeError(f"Source asset not found: {asset_id}")

        source_bytes = _load_asset_bytes(asset)
        if not source_bytes:
            raise RuntimeError(f"Could not read source asset bytes: {asset_id}")

        parts: list[genai_types.Part] = [
            genai_types.Part.from_text(text=(
                "You are a commercial advertising compliance analyst.\n"
                "Inspect the supplied image and identify ONLY policy-relevant violations that require visual remediation.\n"
                "Return only valid JSON.\n\n"
                "Goals:\n"
                "1. Detect impersonation / personality-rights risk when a person resembles a real celebrity, athlete, influencer, or public figure.\n"
                "2. Detect IP infringement such as protected trophies, official team identity cues, copyrighted characters, or trademarked branded visual assets that should not remain.\n"
                "3. Detect adult or sexualized presentation.\n"
                "4. Detect deceptive UI overlays such as fake play buttons or fake close buttons.\n"
                "5. Preserve valid brand copy, CTA, layout, logo placement, and all non-violating regions.\n\n"
                "Important constraints for your output:\n"
                "- Be specific about which regions must change.\n"
                "- Be equally specific about what must remain untouched.\n"
                "- If a celebrity athlete appears, require a full synthetic replacement of face, hair, beard, jersey identity cues, body silhouette cues, and iconic styling markers.\n"
                "- If a protected trophy appears, require replacement with an original generic trophy while preserving placement and scale.\n"
                "- The remediation prompt will be sent directly to an image-editing model, so write it as a complete direct editing instruction, not as notes.\n"
                "- The remediation prompt must explicitly describe both: (a) what to change, and (b) what to keep unchanged.\n"
                "- The remediation prompt must preserve the original full canvas, original aspect ratio, all valid copy, CTA, logos, and non-violating layout regions unless they are themselves violations.\n"
                "- For personality-rights or impersonation violations, the remediation prompt must demand a strong full-character de-identification, not a light face retouch.\n"
                "- For personality-rights or impersonation violations, the remediation prompt must instruct the image model to change face, hair, facial hair, jersey identity cues, body silhouette cues, and iconic styling markers enough to eliminate resemblance.\n"
                "- The remediation prompt must be decisive and executable by an image-editing model, not vague.\n"
                f"- User note: {(request.prompt or '').strip() or 'No extra user note.'}"
            )),
            genai_types.Part.from_bytes(data=source_bytes, mime_type=_guess_asset_mime_type(asset)),
        ]

        response = client.models.generate_content(
            model=settings.vertex_gemini_model,
            contents=[genai_types.Content(role="user", parts=parts)],
            config=genai_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=response_schema,
                temperature=0.1,
            ),
        )

        data = json.loads(response.text or "{}")
        result = RemediationAnalysisResult(
            asset_id=asset.id,
            asset_title=asset.title,
            overall_risk=(data.get("overall_risk") or "unknown").strip(),
            summary=(data.get("summary") or "").strip(),
            preserve_instructions=[item.strip() for item in data.get("preserve_instructions", []) if isinstance(item, str) and item.strip()],
            violations=[
                RemediationViolation(
                    category=(item.get("category") or "").strip(),
                    severity=(item.get("severity") or "").strip(),
                    target=(item.get("target") or "").strip(),
                    reason=(item.get("reason") or "").strip(),
                    fix_instruction=(item.get("fix_instruction") or "").strip(),
                )
                for item in data.get("violations", [])
                if isinstance(item, dict)
            ],
            remediation_prompt=(data.get("remediation_prompt") or "").strip(),
        )

        asset.analysis = {
            **(asset.analysis or {}),
            "remediation_analysis": result.model_dump(),
            "remediation_analysis_version": "v2_scan_then_fix",
            "remediation_analyzed_at": utcnow_naive().isoformat(),
            "remediation_analyzed_by": created_by,
        }
        upsert_asset(asset)
        results.append(result)

    return RemediationAnalysisResponse(results=results)


def _parse_size(size: str) -> tuple[int | None, int | None]:
    try:
        width, height = size.lower().split("x", 1)
        return int(width), int(height)
    except ValueError:
        return None, None


def _mark_generation_progress(
    job: GenerationJob,
    progress: int,
    message: str | None = None,
) -> bool:
    """Update a running generation job and return False if it was cancelled."""
    if job.status != JobStatus.running:
        return False
    job.progress = max(0, min(99, progress))
    if message:
        job.message = message
    job.updated_at = utcnow_naive()
    upsert_job(job)
    return True


def _load_asset_bytes(asset: Asset) -> bytes | None:
    return read_asset_bytes(asset)


def _get_asset_bucket_name() -> str | None:
    bucket = (get_settings().incept_asset_bucket or "").strip()
    if not bucket or bucket == "INCEPT_ASSET_BUCKET":
        return None
    return bucket


def _require_gcs_upload() -> bool:
    return bool(get_settings().incept_require_gcs_upload)


def _get_gcs_client():
    global _GCS_CLIENT
    if _GCS_CLIENT is not None:
        return _GCS_CLIENT
    bucket = _get_asset_bucket_name()
    if not bucket:
        return None
    try:
        from google.cloud import storage

        settings = get_settings()
        _GCS_CLIENT = storage.Client(project=settings.gcp_project_id or None)
        return _GCS_CLIENT
    except Exception:
        logger.warning("Could not initialize Google Cloud Storage client", exc_info=True)
        return None


def _guess_content_type(filename: str, fallback: str = "application/octet-stream") -> str:
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or fallback


def _build_gcs_object_path(
    *,
    category: str,
    workspace_id: str,
    created_at: datetime,
    filename: str,
    job_id: str | None = None,
) -> str:
    parts = [
        category,
        workspace_id,
        created_at.strftime("%Y"),
        created_at.strftime("%m"),
        created_at.strftime("%d"),
    ]
    if job_id:
        parts.append(job_id)
    parts.append(filename)
    return "/".join(parts)


def _upload_bytes_to_gcs(
    *,
    content: bytes,
    object_path: str,
    content_type: str,
) -> str:
    bucket_name = _get_asset_bucket_name()
    if not bucket_name:
        return ""
    client = _get_gcs_client()
    if client is None:
        message = (
            "Google Cloud Storage client could not be initialized for configured "
            f"bucket {bucket_name}. Check runtime credentials / ADC configuration."
        )
        if _require_gcs_upload():
            raise RuntimeError(message)
        logger.warning("%s Falling back to local temp storage.", message)
        return ""
    try:
        blob = client.bucket(bucket_name).blob(object_path)
        blob.upload_from_string(content, content_type=content_type)
        return f"gs://{bucket_name}/{object_path}"
    except Exception as exc:
        logger.warning("Could not upload asset to GCS path %s", object_path, exc_info=True)
        if _require_gcs_upload():
            raise RuntimeError(
                f"GCS upload failed for gs://{bucket_name}/{object_path}: {exc}"
            ) from exc
        logger.warning(
            "Falling back to local temp storage because GCS upload failed "
            "[bucket=%s object=%s error=%s]",
            bucket_name,
            object_path,
            exc,
        )
        return ""


def _record_asset_storage_status(asset: Asset, *, category: str) -> None:
    bucket_name = _get_asset_bucket_name()
    bucket_configured = bool(bucket_name)
    uploaded_to_gcs = bool(asset.gcs_uri and asset.gcs_uri.startswith("gs://"))
    storage_mode = "gcs+local-cache" if uploaded_to_gcs else "local-temp"
    storage_status = {
        "category": category,
        "uploaded_to_gcs": uploaded_to_gcs,
        "bucket_configured": bucket_configured,
        "bucket": bucket_name,
        "gcs_uri": asset.gcs_uri or None,
        "preview_url": asset.preview_url,
        "storage_mode": storage_mode,
    }
    asset.analysis = {
        **(asset.analysis or {}),
        "storage": storage_status,
    }
    if uploaded_to_gcs:
        logger.info(
            "Asset %s uploaded to GCS successfully [category=%s bucket=%s gcs_uri=%s]",
            asset.id,
            category,
            bucket_name,
            asset.gcs_uri,
        )
    else:
        if bucket_configured:
            logger.warning(
                "Asset %s stored in local temp mode because GCS upload was unavailable "
                "[category=%s bucket=%s preview_url=%s]",
                asset.id,
                category,
                bucket_name,
                asset.preview_url,
            )
        else:
            logger.info(
                "Asset %s stored in local temp mode because no GCS bucket is configured "
                "[category=%s preview_url=%s]",
                asset.id,
                category,
                asset.preview_url,
            )


def _parse_gcs_uri(gcs_uri: str) -> tuple[str, str] | None:
    text = (gcs_uri or "").strip()
    if not text.startswith("gs://"):
        return None
    remainder = text[len("gs://"):]
    if "/" not in remainder:
        return None
    bucket_name, object_path = remainder.split("/", 1)
    if not bucket_name or not object_path:
        return None
    return bucket_name, object_path


def _download_bytes_from_gcs(gcs_uri: str) -> bytes | None:
    parsed = _parse_gcs_uri(gcs_uri)
    if not parsed:
        return None
    bucket_name, object_path = parsed
    client = _get_gcs_client()
    if client is None:
        return None
    try:
        blob = client.bucket(bucket_name).blob(object_path)
        return blob.download_as_bytes()
    except Exception:
        logger.warning("Could not download asset from GCS uri %s", gcs_uri, exc_info=True)
        return None


def _delete_gcs_object(gcs_uri: str) -> None:
    parsed = _parse_gcs_uri(gcs_uri)
    if not parsed:
        return
    bucket_name, object_path = parsed
    client = _get_gcs_client()
    if client is None:
        return
    try:
        client.bucket(bucket_name).blob(object_path).delete()
    except Exception:
        logger.warning("Could not delete asset from GCS uri %s", gcs_uri, exc_info=True)


def guess_asset_extension(asset: Asset) -> str:
    for raw in (asset.preview_url, asset.gcs_uri, asset.title):
        suffix = Path((raw or "").split("?")[0]).suffix
        if suffix:
            return suffix
    if asset.type == "gif":
        return ".gif"
    return ".png"


def _derive_upload_safe_jpeg(image_bytes: bytes) -> bytes | None:
    try:
        from io import BytesIO
        from PIL import Image

        with Image.open(BytesIO(image_bytes)) as img:
            rgb = img.convert("RGB")
            smallest: bytes | None = None
            for quality in (90, 85, 80, 75, 70, 65, 60, 55, 50, 45, 40, 35, 30, 25):
                buf = BytesIO()
                rgb.save(
                    buf,
                    format="JPEG",
                    quality=quality,
                    optimize=True,
                )
                encoded = buf.getvalue()
                smallest = encoded
                if len(encoded) <= _UPLOAD_SAFE_JPEG_MAX_BYTES:
                    return encoded
            return smallest
    except Exception:
        logger.warning("Could not derive upload-safe JPEG", exc_info=True)
        return None


def _cache_asset_bytes_locally(asset: Asset, content: bytes) -> None:
    path = _resolve_asset_path(asset)
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(content)
    except Exception:
        logger.warning("Could not cache asset %s locally", asset.id, exc_info=True)


def read_asset_bytes(asset: Asset) -> bytes | None:
    path = _resolve_asset_path(asset)
    if path and path.exists():
        try:
            return path.read_bytes()
        except Exception:
            logger.warning("Could not read local bytes for asset %s", asset.id, exc_info=True)

    gcs_bytes = _download_bytes_from_gcs(asset.gcs_uri)
    if gcs_bytes is not None:
        _cache_asset_bytes_locally(asset, gcs_bytes)
        return gcs_bytes
    return None


def stream_asset_bytes(asset: Asset, *, chunk_size: int = 1024 * 1024) -> Iterator[bytes]:
    """Stream large local or GCS-backed assets without buffering the full file in memory."""
    path = _resolve_asset_path(asset)
    if path and path.exists():
        with path.open("rb") as file:
            while chunk := file.read(chunk_size):
                yield chunk
        return

    parsed = _parse_gcs_uri(asset.gcs_uri)
    if parsed:
        bucket_name, object_path = parsed
        client = _get_gcs_client()
        if client is not None:
            blob = client.bucket(bucket_name).blob(object_path)
            with blob.open("rb") as file:
                while chunk := file.read(chunk_size):
                    yield chunk
            return

    # Preserve the existing fallback for legacy assets whose bytes can still be resolved.
    content = read_asset_bytes(asset)
    if content is None:
        raise FileNotFoundError(f"Asset content not found: {asset.id}")
    yield content


def build_asset_content_path(asset_id: str) -> str:
    return f"/assets/{asset_id}/content"


def _effective_output_sizes(
    requested_sizes: list[str] | None,
    fallback_asset: Asset | None = None,
) -> list[str]:
    normalized: list[str] = []
    for size in requested_sizes or []:
        text = (size or "").strip()
        if text and text not in normalized:
            normalized.append(text)

    if normalized:
        return normalized
    if fallback_asset and fallback_asset.width and fallback_asset.height:
        return [f"{fallback_asset.width}x{fallback_asset.height}"]
    return ["1024x1024"]


async def _export_master_images_to_assets(
    *,
    job: GenerationJob,
    raw_outputs: list[bytes],
    workspace_id: str,
    created_by: str,
    provider: str,
    model: str,
    label: str,
    theme: str | None,
    requested_sizes: list[str] | None,
    source_asset: Asset | None,
    context_assets: list[Asset] | None = None,
    created_at: datetime | None = None,
    include_kakao_gacha_disclosure: bool = False,
) -> list[Asset]:
    from app.incept.composite import add_kakao_gacha_disclosure, resize_to_exact

    def _display_label(size_value: str, variant_index: int) -> str:
        base_source_title = ""
        if source_asset and source_asset.title:
            base_source_title = _normalized_source_title(source_asset.title)
        cleaned_label = (label or "Generated").strip()
        if cleaned_label.lower().startswith("resize") and base_source_title:
            return f"{base_source_title}_{size_value}v{variant_index}"
        if cleaned_label.lower() == "theme create" and base_source_title:
            return f"{base_source_title}_v{variant_index}"
        if cleaned_label.lower() == "image remediation" and base_source_title:
            return f"{base_source_title}_remediation{variant_index}"
        if cleaned_label.lower() == "kakao bizboard" and base_source_title:
            return f"{base_source_title}_kakao{variant_index}"
        if cleaned_label.lower() == "kakao clean" and base_source_title:
            return base_source_title
        if base_source_title:
            return f"{base_source_title} - {cleaned_label} {size_value} v{variant_index}"
        return f"{cleaned_label} {size_value} v{variant_index}"

    target_sizes = _effective_output_sizes(requested_sizes, source_asset)

    created_assets: list[Asset] = []
    now = created_at or utcnow_naive()

    for size in target_sizes:
        width, height = _parse_size(size)
        for idx, raw in enumerate(raw_outputs):
            output_bytes = raw
            analysis: dict | None = {"adaptation": {"mode": "direct_output"}}

            if width and height:
                try:
                    current_w, current_h = _read_image_size(raw)
                    if current_w == width and current_h == height:
                        output_bytes = raw
                        analysis = {"adaptation": {"mode": "direct_output"}}
                    else:
                        output_bytes = resize_to_exact(raw, width, height)
                        analysis = {"adaptation": {"mode": "simple_resize"}}
                except Exception:
                    analysis = {"adaptation": {"mode": "fallback_original"}}

            # If dimensions are still missing, read from the final output bytes
            if not width or not height:
                width, height = _read_image_size(output_bytes)

            if include_kakao_gacha_disclosure and size in _RESIZE_GACHA_DISCLOSURE_SIZES:
                output_bytes = add_kakao_gacha_disclosure(output_bytes)
                analysis = {
                    **(analysis or {}),
                    "kakao_gacha_disclosure": True,
                }

            asset_id = f"{job.lineage_key}_{size}_{idx + 1}_img"
            asset_bytes = output_bytes
            asset_extension = ".png"
            content_type = "image/png"
            asset_analysis = dict(analysis or {})

            if size in _UPLOAD_SAFE_JPEG_SIZES:
                jpg_bytes = _derive_upload_safe_jpeg(output_bytes)
                if jpg_bytes:
                    asset_bytes = jpg_bytes
                    asset_extension = ".jpg"
                    content_type = "image/jpeg"
                    asset_analysis.update({
                        "derived_format": "jpg",
                        "upload_safe": True,
                        "upload_safe_target_bytes": _UPLOAD_SAFE_JPEG_MAX_BYTES,
                        "upload_safe_actual_bytes": len(jpg_bytes),
                    })

            preview_url = _save_image_file(
                asset_id,
                base64.b64encode(asset_bytes).decode(),
                asset_extension,
            )
            asset = Asset(
                id=asset_id,
                title=_display_label(size, idx + 1),
                type="image",
                gcs_uri="",
                preview_url=preview_url,
                provider=provider,
                model=model,
                workspace_id=workspace_id,
                job_id=job.job_id,
                prompt_hash="",
                created_by=created_by,
                created_at=now,
                width=width,
                height=height,
                theme=theme,
                asset_role=AssetRole.generated,
                analysis=asset_analysis,
                thread_id=job.thread_id,
                parent_asset_id=source_asset.id if source_asset else None,
                root_asset_id=_inherit_root_asset_id(source_asset, asset_id),
            )
            asset.gcs_uri = _upload_bytes_to_gcs(
                content=asset_bytes,
                object_path=_build_gcs_object_path(
                    category="generated",
                    workspace_id=workspace_id,
                    created_at=now,
                    job_id=job.job_id,
                    filename=f"{asset_id}{asset_extension}",
                ),
                content_type=content_type,
            )
            _record_asset_storage_status(asset, category="generated")
            ASSETS[asset_id] = asset
            upsert_asset(asset)
            created_assets.append(asset)

    return created_assets


async def _export_oversampled_728x180_resize_assets(
    *,
    job: GenerationJob,
    raw_outputs: list[bytes],
    workspace_id: str,
    created_by: str,
    provider: str,
    model: str,
    label: str,
    theme: str | None,
    source_asset: Asset | None,
    created_at: datetime | None = None,
) -> list[Asset]:
    from app.incept.composite import split_728x180_into_two_728x90

    created_assets: list[Asset] = []
    now = created_at or utcnow_naive()
    base_source_title = _normalized_source_title(source_asset.title) if source_asset and source_asset.title else ""

    output_counter = 0
    for idx, raw in enumerate(raw_outputs):
        top_bytes, bottom_bytes = split_728x180_into_two_728x90(raw)
        for crop_index, (crop_label, output_bytes) in enumerate(
            (("top", top_bytes), ("bottom", bottom_bytes)),
            start=1,
        ):
            output_counter += 1
            asset_id = f"{job.lineage_key}_728x90_from_728x180_{idx + 1}_{crop_index}_img"
            preview_url = _save_image_file(asset_id, base64.b64encode(output_bytes).decode())
            if base_source_title:
                asset_title = f"{base_source_title}_728x90v{output_counter}"
            else:
                asset_title = f"Resize_728x90v{output_counter}"
            asset = Asset(
                id=asset_id,
                title=asset_title,
                type="image",
                gcs_uri="",
                preview_url=preview_url,
                provider=provider,
                model=model,
                workspace_id=workspace_id,
                job_id=job.job_id,
                prompt_hash="",
                created_by=created_by,
                created_at=now,
                width=728,
                height=90,
                theme=theme,
                asset_role=AssetRole.generated,
                analysis={
                    "adaptation": {
                        "mode": "oversampled_split",
                        "source_size": "728x180",
                        "delivered_size": "728x90",
                        "crop_position": crop_label,
                    }
                },
                thread_id=job.thread_id,
                parent_asset_id=source_asset.id if source_asset else None,
                root_asset_id=_inherit_root_asset_id(source_asset, asset_id),
            )
            asset.gcs_uri = _upload_bytes_to_gcs(
                content=output_bytes,
                object_path=_build_gcs_object_path(
                    category="generated",
                    workspace_id=workspace_id,
                    created_at=now,
                    job_id=job.job_id,
                    filename=f"{asset_id}.png",
                ),
                content_type="image/png",
            )
            _record_asset_storage_status(asset, category="generated")
            ASSETS[asset_id] = asset
            upsert_asset(asset)
            created_assets.append(asset)

    return created_assets


def _thread_title_from_prompt(prompt: str, fallback: str = "New thread") -> str:
    text = " ".join(prompt.strip().split())
    if not text:
        return fallback
    return text[:72]


def _resolve_thread_for_request(
    *,
    workspace_id: str,
    created_by: str,
    generation_mode: GenerationMode,
    thread_id: str | None,
    prompt: str,
    source_asset_id: str | None = None,
) -> CreativeThread:
    source_asset = _get_asset(source_asset_id) if source_asset_id else None
    preferred_thread_id = thread_id or source_asset.thread_id if source_asset else thread_id
    origin_asset_id = source_asset.id if source_asset else None
    return thread_store.ensure_thread(
        workspace_id=workspace_id,
        title=_thread_title_from_prompt(prompt),
        generation_mode=generation_mode,
        created_by=created_by,
        thread_id=preferred_thread_id,
        origin_asset_id=origin_asset_id,
    )


def _inherit_root_asset_id(source_asset: Asset | None, fallback_asset_id: str) -> str:
    if source_asset and source_asset.root_asset_id:
        return source_asset.root_asset_id
    if source_asset:
        return source_asset.id
    return fallback_asset_id


def list_workspaces() -> list[Workspace]:
    return sorted(WORKSPACES.values(), key=lambda item: item.updated_at, reverse=True)


def list_threads(workspace_id: str | None = None, created_by: str | None = None) -> list[CreativeThread]:
    assets = list(ASSETS.values()) + list(SOURCE_ASSETS.values())
    jobs = list(JOBS.values())
    threads = thread_store.hydrate_thread_summaries(assets=assets, jobs=jobs)
    if workspace_id:
        threads = [thread for thread in threads if thread.workspace_id == workspace_id]
    if created_by:
        threads = [thread for thread in threads if thread.created_by == created_by]
    return threads


def list_jobs(
    workspace_id: str | None = None,
    created_by: str | None = None,
) -> list[GenerationJob]:
    jobs = list(JOBS.values())
    if workspace_id:
        jobs = [job for job in jobs if job.workspace_id == workspace_id]
    if created_by:
        owned_thread_ids = {
            thread.thread_id
            for thread in thread_store.list_threads(workspace_id)
            if thread.created_by == created_by
        }
        owned_asset_ids = {
            asset.id
            for asset in list(ASSETS.values()) + list(SOURCE_ASSETS.values())
            if asset.created_by == created_by and (not workspace_id or asset.workspace_id == workspace_id)
        }
        jobs = [
            job
            for job in jobs
            if (
                (job.thread_id and job.thread_id in owned_thread_ids)
                or (job.source_asset_id and job.source_asset_id in owned_asset_ids)
                or any(asset_id in owned_asset_ids for asset_id in job.output_asset_ids)
            )
        ]
    return sorted(jobs, key=lambda item: item.created_at, reverse=True)


def get_job(job_id: str) -> GenerationJob | None:
    cached_job = JOBS.get(job_id)
    try:
        persisted_row = load_job(job_id)
        persisted_job = _job_from_row(persisted_row) if persisted_row else None
    except Exception:
        logger.warning("Could not refresh persisted job %s", job_id, exc_info=True)
        return cached_job

    if not persisted_job:
        return cached_job
    if not cached_job or persisted_job.updated_at >= cached_job.updated_at:
        JOBS[job_id] = persisted_job
        return persisted_job
    return cached_job


def delete_asset(asset_id: str) -> bool:
    """Remove asset from memory, local cache, GCS, and SQLite. Returns True if found."""
    asset = ASSETS.pop(asset_id, None)
    if not asset:
        # also check SOURCE_ASSETS (uploads)
        asset = SOURCE_ASSETS.pop(asset_id, None)
    if not asset:
        return False

    # Delete file from disk
    try:
        if asset.preview_url.startswith("/static/generated/"):
            path = STATIC_DIR / asset.preview_url[len("/static/generated/"):]
        elif asset.preview_url.startswith("/static/uploads/"):
            path = UPLOAD_DIR / asset.preview_url[len("/static/uploads/"):]
        else:
            path = None
        if path and path.exists():
            path.unlink()
    except Exception:
        logger.warning("Could not delete file for asset %s", asset_id)

    if asset.gcs_uri:
        _delete_gcs_object(asset.gcs_uri)

    db_delete_asset(asset_id)
    return True


def list_assets(workspace_id: str | None = None, created_by: str | None = None) -> list[Asset]:
    values = list(ASSETS.values()) + list(SOURCE_ASSETS.values())
    if workspace_id:
        values = [asset for asset in values if asset.workspace_id == workspace_id]
    if created_by:
        values = [asset for asset in values if asset.created_by == created_by]
    return sorted(values, key=lambda item: item.created_at, reverse=True)


def list_usage_events(workspace_id: str | None = None) -> list[UsageEvent]:
    values = USAGE_EVENTS.values()
    if workspace_id:
        values = [event for event in values if event.workspace_id == workspace_id]
    return sorted(values, key=lambda item: item.created_at, reverse=True)


def _maybe_convert_psd(content: bytes, filename: str) -> tuple[bytes, str, str, dict[str, object] | None]:
    """Flatten a PSD to PNG before it can be used as an image reference.

    The image-generation providers only ever receive a PNG working copy.  A
    malformed or unsupported PSD must fail the upload rather than silently
    becoming a source image that later falls back to text-only generation.
    """
    if not filename.lower().endswith(".psd"):
        return content, filename, "", None
    try:
        from psd_tools import PSDImage
        import io as _io
        psd = PSDImage.open(_io.BytesIO(content))
        width, height = int(psd.width), int(psd.height)
        if width <= 0 or height <= 0 or width * height > _MAX_PSD_RASTER_PIXELS:
            raise ValueError(
                "PSD dimensions are not supported for conversion. "
                f"Maximum is {_MAX_PSD_RASTER_PIXELS:,} pixels."
            )
        buf = _io.BytesIO()
        psd.composite().save(buf, format="PNG")
        png_bytes = buf.getvalue()
        if not png_bytes:
            raise ValueError("PSD contains no composite image.")
        png_filename = Path(filename).stem + ".png"
        logger.info("PSD converted to PNG: %s → %s (%d MB → %d MB)",
                    filename, png_filename, len(content) // 1_000_000, len(png_bytes) // 1_000_000)
        return png_bytes, png_filename, "image/png", {
            "source_format": "psd",
            "rasterized_from_psd": True,
            "model_input_mime_type": "image/png",
            "source_width": width,
            "source_height": height,
        }
    except Exception as exc:
        logger.warning("PSD conversion failed for %s", filename, exc_info=True)
        raise ValueError(
            "This PSD could not be converted to a PNG working image. "
            "Flatten the document in Photoshop and upload the exported PNG instead."
        ) from exc


def _uploaded_asset_type(filename: str, content_type: str | None) -> str:
    """Classify an upload without treating audio as an image fallback."""
    inferred_mime = (content_type or _guess_content_type(filename, "application/octet-stream")).lower()
    extension = Path(filename).suffix.lower()
    if inferred_mime.startswith("video/"):
        return "video"
    if inferred_mime.startswith("audio/"):
        return "audio"
    if inferred_mime == "text/html" or extension in {".html", ".htm"}:
        return "playable"
    if inferred_mime in {"application/zip", "application/x-zip-compressed"} or extension == ".zip":
        return "report"
    if extension in _NON_RASTER_UPLOAD_EXTENSIONS:
        return "report"
    return "image"


def save_uploaded_asset(
    workspace_id: str,
    filename: str,
    content: bytes,
    asset_role: str,
    user_id: str,
    thread_id: str | None = None,
    content_type: str | None = None,
) -> Asset:
    content, filename, converted_mime, conversion_analysis = _maybe_convert_psd(content, filename)
    if converted_mime:
        content_type = converted_mime
    inferred_mime = (content_type or _guess_content_type(filename, "application/octet-stream")).lower()
    asset_type = _uploaded_asset_type(filename, inferred_mime)

    img_w, img_h = (None, None)
    if asset_type == "image":
        # Read actual pixel dimensions so they're available for downstream image ops.
        img_w, img_h = _read_image_size(content)
        if img_w is None or img_h is None:
            raise ValueError(
                "Unsupported or invalid raster image. Upload PNG, JPEG, WebP, GIF, TIFF, BMP, "
                "or a PSD that can be flattened to PNG."
            )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    asset_id = f"asset_upload_{uuid4().hex[:12]}"
    ext = Path(filename).suffix or ".png"
    dest = UPLOAD_DIR / f"{asset_id}{ext}"
    dest.write_bytes(content)
    created_at = utcnow_naive()

    asset = Asset(
        id=asset_id,
        title=filename,
        type=asset_type,
        gcs_uri="",
        preview_url=f"/static/uploads/{asset_id}{ext}",
        provider="upload",
        model="",
        workspace_id=workspace_id,
        job_id="",
        prompt_hash="",
        created_by=user_id,
        created_at=created_at,
        width=img_w,
        height=img_h,
        theme=None,
        asset_role=_coerce_asset_role(asset_role, provider="upload"),
        analysis=conversion_analysis,
        thread_id=thread_id,
    )
    object_path = _build_gcs_object_path(
        category="uploads",
        workspace_id=workspace_id,
        created_at=created_at,
        filename=f"{asset_id}{ext}",
    )
    asset.gcs_uri = _upload_bytes_to_gcs(
        content=content,
        object_path=object_path,
        content_type=inferred_mime,
    ) or f"local://uploads/{asset_id}{ext}"
    _record_asset_storage_status(asset, category="uploads")
    SOURCE_ASSETS[asset_id] = asset
    upsert_asset(asset)
    return asset


def _read_image_size(image_bytes: bytes) -> tuple[int | None, int | None]:
    """Return (width, height) by reading the image with Pillow. Never raises."""
    try:
        from PIL import Image
        import io as _io
        with Image.open(_io.BytesIO(image_bytes)) as img:
            return img.width, img.height
    except Exception:
        return None, None


def _aspect_bucket(size: str) -> str:
    width, height = _parse_size(size)
    if not width or not height:
        return "unknown"
    ratio = width / height
    if ratio >= 4:
        return "banner"
    if ratio >= 1.4:
        return "landscape"
    if ratio <= 0.75:
        return "portrait"
    return "standard"


def _single_size_prompt_text(prompt: str, target_size: str, requested_sizes: list[str]) -> str:
    """Remove other target sizes from a per-size model call to avoid contact sheets."""
    import re

    text = prompt or ""
    for size in requested_sizes:
        if size != target_size:
            text = re.sub(rf"(?<!\d){re.escape(size)}(?!\d)", "", text, flags=re.IGNORECASE)

    # Remove generic multi-output language while keeping the user's creative brief.
    text = re.sub(
        r"\b(all|multiple|several|various)\s+(sizes|formats|aspect ratios|versions)\b",
        "this size",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\bevery requested size\b", "this size", text, flags=re.IGNORECASE)
    text = re.sub(r"\brequested sizes\b", "this size", text, flags=re.IGNORECASE)
    text = re.sub(r"\bacross\s+this size\b", "for this size", text, flags=re.IGNORECASE)
    text = re.sub(r"\bacross\s+all\s+\w+\b", "for this size", text, flags=re.IGNORECASE)
    text = re.sub(r"\bad set\b", "single ad", text, flags=re.IGNORECASE)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+,", ",", text)
    return text.strip(" ,;") or prompt


def _estimate_provider_generations(request: GenerationRequest) -> int:
    aspect_buckets = {_aspect_bucket(size) for size in request.output_sizes}
    return request.variants * max(1, len(aspect_buckets))


def _estimate_cost_usd(request: GenerationRequest, provider_generations: int) -> float:
    if request.provider == "openai":
        return round(provider_generations * 0.04, 4)
    if request.provider == "gemini":
        return round(provider_generations * 0.04, 4)
    return 0.0


def _month_window(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return the current UTC calendar-month window without a reset job."""
    current = now or utcnow_naive()
    start = datetime(current.year, current.month, 1)
    if current.month == 12:
        return start, datetime(current.year + 1, 1, 1)
    return start, datetime(current.year, current.month + 1, 1)


def current_monthly_studio_spend_usd(user: User, now: datetime | None = None) -> float:
    """All metered Studio operations share one per-user monthly allowance."""
    start, end = _month_window(now)
    return round(sum(
        event.actual_cost_usd if event.actual_cost_usd is not None else event.estimated_cost_usd
        for event in USAGE_EVENTS.values()
        if event.user_id == user.id and start <= event.created_at < end
    ), 4)


def monthly_budget_reset_message(budget_limit: float, now: datetime | None = None) -> str:
    _start, reset_at = _month_window(now)
    return (
        f"Monthly Studio budget reached (${budget_limit:.2f}). "
        f"Your allowance resets automatically on {reset_at.strftime('%B')} 1, {reset_at.year} (UTC). "
        "Please try again after it resets."
    )


def assert_image_budget_available(request: GenerationRequest, user: User) -> None:
    """Enforce the shared per-user Studio budget before image generation."""
    settings = get_settings()
    budget_limit = max(0.0, settings.studio_user_budget_usd)
    if budget_limit <= 0:
        return
    current_spend = current_monthly_studio_spend_usd(user)
    estimated_request_cost = _estimate_cost_usd(request, _estimate_provider_generations(request))
    if current_spend + estimated_request_cost > budget_limit:
        raise RuntimeError(monthly_budget_reset_message(budget_limit))


_SUPPORTED_OPENAI_MODELS = frozenset(
    {
        "dall-e-2",
        "dall-e-3",
        "gpt-image-2",          # current default OpenAI model
        "chatgpt-image-latest",
        # Legacy — kept for backward compatibility with existing assets
        "gpt-image-1",
        "gpt-image-1-mini",
        "gpt-image-1.5",
        "gpt-image-2-2026-04-21",
    }
)


async def _generate_images_openai(
    prompt: str,
    model: str,
    variants: int,
    openai_size: str = "1024x1024",
    quality: str | None = None,
) -> list[str]:
    """Call OpenAI and return list of base64 PNG strings."""
    from openai import AsyncOpenAI

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Fall back to the configured default if the model is not recognised
    if model not in _SUPPORTED_OPENAI_MODELS:
        model = settings.openai_image_model

    # gpt-image-1 family does NOT support response_format — it always returns
    # b64_json by default.  Only the legacy dall-e-* models need it specified.
    _LEGACY_DALLE = {"dall-e-2", "dall-e-3"}

    b64_images: list[str] = []

    if model == "dall-e-3":
        # dall-e-3 only supports n=1 per call — loop to produce multiple variants
        for _ in range(min(variants, 4)):
            response = await client.images.generate(
                model="dall-e-3",
                prompt=prompt[:4000],
                n=1,
                size="1024x1024",
                response_format="b64_json",
            )
            if response.data[0].b64_json:
                b64_images.append(response.data[0].b64_json)
    elif model == "dall-e-2":
        response = await client.images.generate(
            model="dall-e-2",
            prompt=prompt[:4000],
            n=min(variants, 4),
            size="1024x1024",
            response_format="b64_json",
        )
        b64_images = [d.b64_json for d in response.data if d.b64_json]
    else:
        # gpt-image-1, gpt-image-1-mini, gpt-image-2 — response_format unsupported;
        # pass the aspect-ratio-matched size for better composition.
        response = await client.images.generate(
            model=model,
            prompt=prompt[:4000],
            n=min(variants, 4),
            size=openai_size,
            **({"quality": quality} if quality else {}),
        )
        b64_images = [d.b64_json for d in response.data if d.b64_json]

    return b64_images


def _normalize_reference_image_for_openai(image_bytes: bytes) -> bytes:
    """Return a PNG version of a reference image for multipart image input."""
    import io as _io
    from PIL import Image

    with Image.open(_io.BytesIO(image_bytes)) as img:
        normalized = img.convert("RGBA")
        buf = _io.BytesIO()
        normalized.save(buf, format="PNG")
        return buf.getvalue()


async def _generate_images_openai_from_references(
    prompt: str,
    reference_images: list[bytes],
    model: str,
    variants: int,
    openai_size: str = "1024x1024",
    quality: str = "high",
) -> list[str]:
    """Generate a new image using one or more image references as conditioning."""
    import io as _io
    from openai import AsyncOpenAI

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    edit_model = model if model in _SUPPORTED_OPENAI_MODELS else settings.openai_image_model
    if edit_model in {"dall-e-2", "dall-e-3"}:
        edit_model = settings.openai_image_model
    if edit_model not in _SUPPORTED_OPENAI_MODELS:
        edit_model = "gpt-image-2"

    image_inputs = []
    for idx, image_bytes in enumerate(reference_images[:8]):
        try:
            png_bytes = _normalize_reference_image_for_openai(image_bytes)
        except Exception:
            logger.warning("Skipping unreadable reference image %s", idx + 1)
            continue
        image_inputs.append((f"reference_{idx + 1}.png", _io.BytesIO(png_bytes), "image/png"))

    if not image_inputs:
        return await _generate_images_openai(prompt, model, variants, openai_size=openai_size)

    try:
        kwargs: dict = {
            "model": edit_model,
            "image": image_inputs,
            "prompt": prompt[:8000],
            "n": min(variants, 4),
            "size": openai_size,
            "quality": quality,
        }
        if edit_model in {"gpt-image-1", "gpt-image-1.5"}:
            kwargs["input_fidelity"] = "high"
        response = await client.images.edit(**kwargs)
    except Exception:
        logger.exception("Reference-conditioned generation failed")
        raise

    return [d.b64_json for d in response.data if d.b64_json]


async def _edit_image_openai(
    original_bytes: bytes,
    mask_bytes: bytes | None,
    prompt: str,
    model: str,
    variants: int,
) -> list[str]:
    """
    Call OpenAI images.edit (inpainting) and return list of base64 PNG strings.

    OpenAI mask convention:
      - Transparent pixels → the model FILLS those areas (edit zone)
      - Opaque pixels      → the model PRESERVES those areas
    """
    import io as _io
    from openai import AsyncOpenAI

    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Preserve modern GPT Image edit requests instead of silently downgrading
    # them to older models with weaker editing fidelity.
    edit_model = model if model in _SUPPORTED_OPENAI_MODELS else settings.openai_image_model
    if edit_model == "dall-e-3":
        edit_model = settings.openai_image_model
    if edit_model not in _SUPPORTED_OPENAI_MODELS:
        edit_model = "gpt-image-2"

    img_file = ("original.png", _io.BytesIO(original_bytes), "image/png")
    kwargs: dict = dict(
        model=edit_model,
        image=img_file,
        prompt=prompt[:4000],
        n=min(variants, 4),
        size="auto",
    )
    if mask_bytes:
        kwargs["mask"] = ("mask.png", _io.BytesIO(mask_bytes), "image/png")

    response = await client.images.edit(**kwargs)
    return [d.b64_json for d in response.data if d.b64_json]


def _is_gemini_image_model(model: str) -> bool:
    """Return True for Gemini models that use generate_content instead of generate_images."""
    return model.lower().startswith("gemini-")


async def _generate_images_gemini(
    prompt: str,
    model: str,
    variants: int,
    *,
    target_size: str | None = None,
    image_size: str | None = None,
) -> list[str]:
    """
    Call Gemini via generate_content() for text-to-image generation.

    Gemini image models cannot use the Imagen generate_images/edit_image endpoints.
    They must be called via generate_content with response_modalities=["IMAGE"].
    """
    import asyncio as _asyncio
    from google import genai
    from google.genai import types as genai_types

    settings = get_settings()
    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )
    aspect_ratio = _vertex_aspect_ratio_for_size(target_size)

    import concurrent.futures as _cf

    def _call_once() -> str | None:
        try:
            image_config_kwargs: dict[str, str] = {}
            if aspect_ratio:
                image_config_kwargs["aspect_ratio"] = aspect_ratio
            if image_size:
                image_config_kwargs["image_size"] = image_size
            response = client.models.generate_content(
                model=model,
                contents=prompt[:4000],
                config=genai_types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                    image_config=genai_types.ImageConfig(**image_config_kwargs) if image_config_kwargs else None,
                ),
            )
            for candidate in (response.candidates or []):
                for part in (candidate.content.parts if candidate.content else []):
                    inline = getattr(part, "inline_data", None)
                    if inline:
                        raw = inline.data
                        if isinstance(raw, bytes):
                            return base64.b64encode(raw).decode()
                        if isinstance(raw, str):
                            return raw
        except Exception:
            logger.exception("Gemini image generation failed for one variant")
        return None

    n = min(variants, 4)
    loop = _asyncio.get_event_loop()
    with _cf.ThreadPoolExecutor(max_workers=n) as pool:
        raw = await _asyncio.gather(*[loop.run_in_executor(pool, _call_once) for _ in range(n)])
    results = [r for r in raw if r is not None]
    if not results:
        raise RuntimeError(f"All {n} Gemini image generation variant(s) failed — check model/location config")
    return results


async def _generate_images_gemini_from_references(
    prompt: str,
    reference_images: list[bytes],
    model: str,
    variants: int,
    target_size: str | None = None,
    image_size: str | None = None,
) -> list[str]:
    """
    Call Gemini via generate_content() for image editing with reference images.

    The model receives the prompt + reference images as inline_data parts and
    returns an edited image in the target aspect ratio.
    """
    import asyncio as _asyncio
    from google import genai
    from google.genai import types as genai_types

    if not reference_images:
        return await _generate_images_gemini(
            prompt,
            model,
            variants,
            target_size=target_size,
            image_size=image_size,
        )

    settings = get_settings()
    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )

    import concurrent.futures as _cf

    # Build multimodal content: prompt text + reference image(s) — shared across all variant calls
    parts: list[genai_types.Part] = [genai_types.Part(text=prompt[:4000])]
    for img_bytes in reference_images[:4]:
        try:
            png = _normalize_reference_image_for_openai(img_bytes)
            parts.append(genai_types.Part.from_bytes(data=png, mime_type="image/png"))
        except Exception:
            logger.warning("Skipping unreadable reference image for Gemini edit")

    if len(parts) < 2:
        logger.warning("No valid reference images; falling back to text-only Gemini generation")
        return await _generate_images_gemini(
            prompt,
            model,
            variants,
            target_size=target_size,
            image_size=image_size,
        )

    contents = [genai_types.Content(role="user", parts=parts)]
    aspect_ratio = _vertex_aspect_ratio_for_size(target_size)

    def _call_once() -> tuple[str | None, str | None]:
        try:
            image_config_kwargs: dict[str, str] = {}
            if aspect_ratio:
                image_config_kwargs["aspect_ratio"] = aspect_ratio
            if image_size:
                image_config_kwargs["image_size"] = image_size
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                    image_config=genai_types.ImageConfig(**image_config_kwargs) if image_config_kwargs else None,
                ),
            )
            text_parts: list[str] = []
            for candidate in (response.candidates or []):
                for part in (candidate.content.parts if candidate.content else []):
                    inline = getattr(part, "inline_data", None)
                    if inline:
                        raw = inline.data
                        if isinstance(raw, bytes):
                            return base64.b64encode(raw).decode(), None
                        if isinstance(raw, str):
                            return raw, None
                    text_value = getattr(part, "text", None)
                    if isinstance(text_value, str) and text_value.strip():
                        text_parts.append(text_value.strip())
        except Exception as exc:
            logger.exception("Gemini image edit failed for one variant")
            return None, f"{exc.__class__.__name__}: {exc}"
        return None, " ".join(text_parts)[:500] if text_parts else None

    n = min(variants, 4)
    loop = _asyncio.get_event_loop()
    with _cf.ThreadPoolExecutor(max_workers=n) as pool:
        raw = await _asyncio.gather(*[loop.run_in_executor(pool, _call_once) for _ in range(n)])
    images = [image for image, _ in raw if image is not None]
    if images:
        return images

    text_responses = [text for _, text in raw if text]
    if text_responses:
        raise RuntimeError(
            f"Gemini returned no image data. Model text response: {text_responses[0]}"
        )
    raise RuntimeError("Gemini returned no image data for this image-edit request")


async def _generate_kakao_clean_image(
    *,
    prompt: str,
    source_image: bytes,
    model: str,
) -> list[str]:
    """Dedicated Gemini image-clean call for Kakao assets.

    This path is intentionally narrower than the generic reference-edit helper:
    one input image, one output image, image-only response requested.
    """
    import asyncio as _asyncio
    from google import genai
    from google.genai import types as genai_types

    settings = get_settings()
    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )

    normalized = _normalize_reference_image_for_openai(source_image)
    parts = [
        genai_types.Part(text=prompt[:4000]),
        genai_types.Part.from_bytes(data=normalized, mime_type="image/png"),
    ]
    contents = [genai_types.Content(role="user", parts=parts)]

    def _extract_image_or_text(response) -> tuple[str | None, str | None]:
        text_parts: list[str] = []
        for candidate in (response.candidates or []):
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                inline = getattr(part, "inline_data", None)
                if inline:
                    raw = inline.data
                    if isinstance(raw, bytes):
                        return base64.b64encode(raw).decode(), None
                    if isinstance(raw, str):
                        return raw, None
                text_value = getattr(part, "text", None)
                if isinstance(text_value, str) and text_value.strip():
                    text_parts.append(text_value.strip())
            finish_reason = getattr(candidate, "finish_reason", None)
            if finish_reason and not text_parts:
                text_parts.append(f"finish_reason={finish_reason}")
        return None, " ".join(text_parts)[:500] if text_parts else None

    def _call_once() -> tuple[str | None, str | None]:
        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=genai_types.GenerateContentConfig(
                    response_modalities=["IMAGE", "TEXT"],
                ),
            )
            return _extract_image_or_text(response)
        except Exception:
            logger.exception("Kakao Gemini clean failed during generate_content call")
            return None, None

    loop = _asyncio.get_event_loop()
    image, text = await loop.run_in_executor(None, _call_once)
    if image:
        return [image]
    if text:
        raise RuntimeError(f"Gemini returned no image data. Model text response: {text}")
    raise RuntimeError("Gemini returned no image data for Kakao clean")


async def _generate_images_vertex(
    prompt: str,
    model: str,
    variants: int,
) -> list[str]:
    """Call Vertex AI Imagen via ADC and return list of base64 PNG strings.

    Requires:
    - VERTEX_AI_ENABLED=true
    - GCP_PROJECT_ID set
    - ADC configured: `gcloud auth application-default login`
    """
    import asyncio
    from google import genai
    from google.genai import types as genai_types

    settings = get_settings()

    # Normalize model name — "gemini-image" is our internal alias
    if model in ("gemini-image", "gemini", ""):
        model = settings.vertex_imagen_model

    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )

    def _sync_generate() -> list[str]:
        response = client.models.generate_images(
            model=model,
            prompt=prompt[:4000],
            config=genai_types.GenerateImagesConfig(
                number_of_images=min(variants, 4),
                output_mime_type="image/png",
            ),
        )
        results: list[str] = []
        for gen_image in response.generated_images:
            img = gen_image.image
            if img is None:
                continue
            # image_bytes is the raw PNG bytes in google-genai >= 1.x
            raw: bytes | None = getattr(img, "image_bytes", None)
            if raw is None:
                # Fallback: save through PIL if available
                try:
                    import io
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")  # type: ignore[arg-type]
                    raw = buf.getvalue()
                except Exception:
                    continue
            results.append(base64.b64encode(raw).decode())
        return results

    # google-genai generate_images is synchronous — run in thread executor
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_generate)


def _vertex_aspect_ratio_for_size(size: str | None) -> str | None:
    """Resize is deliberately prompt-led for every target canvas.

    Gemini receives only the source image and the user-visible Resize prompt;
    we do not impose ``image_config.aspect_ratio`` or coerce any request to a
    nearest native ratio before generation. The target size remains part of
    the prompt and is used for the final exported asset dimensions.
    """
    return None


async def _generate_images_vertex_from_references(
    prompt: str,
    reference_images: list[bytes],
    model: str,
    variants: int,
    target_size: str | None = None,
) -> list[str]:
    """Call Vertex AI Imagen edit with uploaded references and return base64 PNG strings."""
    import asyncio
    import tempfile
    from google import genai
    from google.genai import types as genai_types

    settings = get_settings()

    requested_model = model
    if requested_model in ("gemini-image", "gemini", ""):
        requested_model = settings.vertex_imagen_model
    if "generate" in requested_model or requested_model == settings.vertex_imagen_model:
        model = settings.vertex_imagen_edit_model
    else:
        model = requested_model

    normalized_references: list[genai_types.RawReferenceImage] = []
    temp_paths: list[str] = []
    for idx, image_bytes in enumerate(reference_images[:8]):
        try:
            png_bytes = _normalize_reference_image_for_openai(image_bytes)
        except Exception:
            logger.warning("Skipping unreadable Vertex reference image %s", idx + 1)
            continue
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        temp_file.write(png_bytes)
        temp_file.flush()
        temp_file.close()
        temp_paths.append(temp_file.name)
        normalized_references.append(
            genai_types.RawReferenceImage(
                reference_id=idx + 1,
                reference_image=genai_types.Image.from_file(location=temp_file.name),
            )
        )

    if not normalized_references:
        return await _generate_images_vertex(prompt, model, variants)

    client = genai.Client(
        vertexai=True,
        project=settings.gcp_project_id,
        location=settings.gcp_location,
    )
    aspect_ratio = _vertex_aspect_ratio_for_size(target_size)

    def _sync_edit() -> list[str]:
        try:
            config_kwargs: dict[str, object] = {
                "number_of_images": min(variants, 4),
                "output_mime_type": "image/png",
            }
            if aspect_ratio:
                config_kwargs["aspect_ratio"] = aspect_ratio
            response = client.models.edit_image(
                model=model,
                prompt=prompt[:4000],
                reference_images=normalized_references,
                config=genai_types.EditImageConfig(**config_kwargs),
            )
            results: list[str] = []
            for gen_image in response.generated_images:
                img = gen_image.image
                if img is None:
                    continue
                raw: bytes | None = getattr(img, "image_bytes", None)
                if raw is None:
                    try:
                        import io

                        buf = io.BytesIO()
                        img.save(buf, format="PNG")  # type: ignore[arg-type]
                        raw = buf.getvalue()
                    except Exception:
                        continue
                results.append(base64.b64encode(raw).decode())
            return results
        finally:
            for temp_path in temp_paths:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_edit)


def _save_image_file(asset_id: str, b64_data: str, extension: str = ".png") -> str:
    """Save base64 image bytes to disk and return preview URL path."""
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    image_bytes = base64.b64decode(b64_data)
    normalized_ext = extension if extension.startswith(".") else f".{extension}"
    dest = STATIC_DIR / f"{asset_id}{normalized_ext}"
    dest.write_bytes(image_bytes)
    return f"/static/generated/{asset_id}{normalized_ext}"


def create_image_generation_job(request: GenerationRequest, user: User) -> GenerationJob:
    """Create job record synchronously and return immediately.

    Returns status=running when a real provider is available (background task will
    do the actual generation). Returns status=completed with mock assets otherwise.
    """
    settings = get_settings()
    job_id = f"job_{uuid4().hex[:12]}"
    lineage_key = f"llg_ast_{uuid4().hex[:16]}"
    now = utcnow_naive()

    is_openai_real = bool(settings.openai_api_key and request.provider == "openai")
    is_vertex_real = bool(
        settings.vertex_ai_enabled
        and settings.gcp_project_id
        and request.provider == "gemini"
    )
    # Gemini image generation via generate_content (separate from Imagen/Vertex)
    is_vertex_gemini_real = bool(
        settings.vertex_gemini_enabled
        and settings.gcp_project_id
        and request.provider == "gemini"
        and _is_gemini_image_model(request.model or settings.vertex_gemini_image_model)
    )
    is_real = is_openai_real or is_vertex_real or is_vertex_gemini_real
    thread = _resolve_thread_for_request(
        workspace_id=request.workspace_id,
        created_by=user.id,
        generation_mode=request.generation_mode,
        thread_id=request.thread_id,
        prompt=request.theme or request.prompt,
        source_asset_id=request.source_asset_id,
    )

    if is_openai_real:
        model = request.model if request.model not in ("gemini-image", "gemini", "") else settings.openai_image_model
        if model not in _SUPPORTED_OPENAI_MODELS:
            model = settings.openai_image_model
        tool_id = "openai-gpt-image-1"
        message = f"Generating images with OpenAI {model}…"
    elif is_vertex_gemini_real:
        model = request.model or settings.vertex_gemini_image_model
        tool_id = "vertex-gemini-image"
        message = f"Generating images with Gemini {model}…"
    elif is_vertex_real:
        model = request.model or settings.vertex_imagen_model
        tool_id = "vertex-imagen-3"
        message = f"Generating images with Vertex AI Imagen ({model})…"
    else:
        model = request.model or settings.openai_image_model
        tool_id = "openai-gpt-image-1" if request.provider == "openai" else "vertex-imagen-3"
        message = _build_mock_message(request)

    job = GenerationJob(
        job_id=job_id,
        workspace_id=request.workspace_id,
        status=JobStatus.running if is_real else JobStatus.completed,
        progress=0 if is_real else 100,
        lineage_key=lineage_key,
        message=message,
        tool_id=tool_id,
        title=f"Image generation — {request.provider}",
        output_asset_ids=[],
        thread_id=thread.thread_id,
        source_asset_id=request.source_asset_id,
        created_at=now,
        updated_at=now,
    )
    JOBS[job_id] = job

    if not is_real:
        _fill_mock_assets(job, request, user, lineage_key, model, now)

    return job


def _build_mock_message(request: GenerationRequest) -> str:
    total = len(request.output_sizes) * request.variants
    if request.provider == "gemini":
        hint = "Set VERTEX_AI_ENABLED=true + GCP_PROJECT_ID and run `gcloud auth application-default login`."
    else:
        hint = "Set OPENAI_API_KEY to generate real images."
    return f"Mock: {total} outputs — {request.variants} variants × {len(request.output_sizes)} sizes. {hint}"


def _fill_mock_assets(
    job: GenerationJob,
    request: GenerationRequest,
    user: User,
    lineage_key: str,
    model: str,
    now: datetime,
) -> None:
    prompt_hash = sha256(request.prompt.encode()).hexdigest()[:16]
    output_types = ["image", "gif"] if request.output_format == "image_and_gif" else [request.output_format]
    asset_ids: list[str] = []
    source_asset = _get_asset(request.source_asset_id) if request.source_asset_id else None
    base_source_title = _normalized_source_title(source_asset.title) if source_asset and source_asset.title else ""
    cleaned_theme = (request.theme or "Generated").strip()

    for size in request.output_sizes:
        width, height = _parse_size(size)
        for idx in range(request.variants):
            for output_type in output_types:
                suffix = "gif" if output_type == "gif" else "img"
                asset_id = f"{lineage_key}_{size}_{idx + 1}_{suffix}"
                if base_source_title:
                    placeholder_title = f"{base_source_title} - {cleaned_theme} {size} v{idx + 1}"
                else:
                    placeholder_title = f"{cleaned_theme} {size} v{idx + 1}"
                asset = Asset(
                    id=asset_id,
                    title=placeholder_title,
                    type=output_type,
                    gcs_uri="",
                    preview_url="/static/placeholder.png",
                    provider=request.provider,
                    model=model,
                    workspace_id=request.workspace_id,
                    job_id=job.job_id,
                    prompt_hash=prompt_hash,
                    created_by=user.id,
                    created_at=now,
                    width=width,
                    height=height,
                    theme=request.theme,
                    thread_id=job.thread_id,
                    parent_asset_id=source_asset.id if source_asset else None,
                    root_asset_id=_inherit_root_asset_id(source_asset, asset_id),
                )
                ASSETS[asset_id] = asset
                asset_ids.append(asset_id)

    job.output_asset_ids = asset_ids
    _record_usage(job, request, user, model, prompt_hash, now)


def _record_usage(
    job: GenerationJob,
    request: GenerationRequest,
    user: User,
    model: str,
    prompt_hash: str,
    now: datetime,
) -> None:
    provider_generations = _estimate_provider_generations(request)
    usage_id = f"use_{uuid4().hex[:12]}"
    usage_event = UsageEvent(
        id=usage_id,
        job_id=job.job_id,
        workspace_id=request.workspace_id,
        user_id=user.id,
        user_email=user.email,
        provider=request.provider,
        model=model,
        operation="image_generation",
        prompt_hash=prompt_hash,
        variants=request.variants,
        output_size_count=len(request.output_sizes),
        output_format=request.output_format,
        estimated_provider_generations=provider_generations,
        output_asset_count=len(job.output_asset_ids),
        estimated_cost_usd=_estimate_cost_usd(request, provider_generations),
        created_at=now,
    )
    USAGE_EVENTS[usage_id] = usage_event
    upsert_usage_event(usage_event)

    workspace = WORKSPACES.get(request.workspace_id)
    if workspace:
        workspace.status = JobStatus.completed
        workspace.updated_at = now

    # Persist job + assets to SQLite so history survives restarts
    upsert_job(job)
    for aid in job.output_asset_ids:
        if aid in ASSETS:
            upsert_asset(ASSETS[aid])

    if job.thread_id:
        latest_asset_id = job.output_asset_ids[-1] if job.output_asset_ids else None
        cover_asset_id = job.output_asset_ids[0] if job.output_asset_ids else None
        thread_store.touch_thread(
            job.thread_id,
            latest_job_id=job.job_id,
            latest_asset_id=latest_asset_id,
            cover_asset_id=cover_asset_id,
            title=request.theme or None,
        )

    persist_generation(job, [ASSETS[aid] for aid in job.output_asset_ids if aid in ASSETS], usage_event)


async def _dispatch_generation(
    prompt: str,
    *,
    provider: str,
    model: str,
    variants: int,
    reference_images: list[bytes],
    openai_size: str = "1024x1024",
    target_size: str | None = None,
    image_size: str | None = None,
) -> list[str]:
    """
    Unified dispatch for image generation.

    Routes to the correct API based on provider + model:
      - provider="gemini" + Gemini model  → generate_content (Gemini native API)
      - provider="gemini" + Imagen model  → generate_images / edit_image (Vertex Imagen API)
      - provider="openai"                 → OpenAI images API
    """
    if provider == "gemini":
        if _is_gemini_image_model(model):
            # Gemini image models use generate_content, NOT generate_images/edit_image
            if reference_images:
                return await _generate_images_gemini_from_references(
                    prompt,
                    reference_images=reference_images,
                    model=model,
                    variants=variants,
                    target_size=target_size,
                    image_size=image_size,
                )
            return await _generate_images_gemini(
                prompt,
                model,
                variants,
                target_size=target_size,
                image_size=image_size,
            )
        else:
            # Imagen models use the Vertex Predict endpoint
            if reference_images:
                return await _generate_images_vertex_from_references(
                    prompt,
                    reference_images=reference_images,
                    model=model,
                    variants=variants,
                    target_size=target_size,
                )
            return await _generate_images_vertex(prompt, model, variants)
    else:
        # OpenAI
        if reference_images:
            return await _generate_images_openai_from_references(
                prompt,
                reference_images=reference_images,
                model=model,
                variants=variants,
                openai_size=openai_size,
            )
        return await _generate_images_openai(prompt, model, variants, openai_size=openai_size)


async def run_generation_background(job_id: str, request: GenerationRequest, user: User) -> None:
    """Background task — dispatches to OpenAI or Vertex AI and updates job state."""
    job = JOBS.get(job_id)
    if not job:
        return

    settings = get_settings()
    lineage_key = job.lineage_key
    now = utcnow_naive()
    prompt_hash = sha256(request.prompt.encode()).hexdigest()[:16]

    # Resolve the effective model for each provider
    if request.provider == "gemini":
        model = request.model or settings.vertex_imagen_model
        provider_label = f"Vertex AI Imagen ({model})"
    else:
        model = request.model if request.model not in ("gemini-image", "gemini", "") else settings.openai_image_model
        if model not in _SUPPORTED_OPENAI_MODELS:
            model = settings.openai_image_model
        provider_label = f"OpenAI {model}"

    try:
        if not _mark_generation_progress(job, 10, f"Preparing {provider_label} generation..."):
            return

        context_asset_ids = list(dict.fromkeys(
            request.reference_asset_ids + request.source_asset_ids + request.client_asset_ids
        ))
        context_assets = [asset for aid in context_asset_ids if (asset := _get_asset(aid))]
        preserve_elements: list[str] = []
        if any(asset.asset_role == AssetRole.client_logo for asset in context_assets):
            preserve_elements.append("brand logo")
        if any(asset.asset_role == AssetRole.client_character for asset in context_assets):
            preserve_elements.append("main character identity")
        if any(asset.asset_role == AssetRole.client_product for asset in context_assets):
            preserve_elements.append("product packshot")
        if request.generation_mode == GenerationMode.style_match:
            preserve_elements.append("reference layout hierarchy")
        elif request.generation_mode == GenerationMode.theme_create:
            preserve_elements.append("theme readability")

        primary_size = request.output_sizes[0] if request.output_sizes else "1200x628"
        requested_sizes = request.output_sizes or [primary_size]
        source_asset = _get_asset(job.source_asset_id) if job.source_asset_id else None
        if not source_asset:
            source_asset = next(
                (_get_asset(asset_id) for asset_id in request.source_asset_ids if _get_asset(asset_id)),
                None,
            )

        if request.generation_mode == GenerationMode.resize:
            if not _mark_generation_progress(job, 15, "Planning simple resize prompts..."):
                return

            source_bytes = _load_asset_bytes(source_asset) if source_asset else None
            if not source_bytes:
                raise RuntimeError("Resize requires a readable source image")

            from app.incept.composite import get_openai_size

            resize_user_note = request.prompt.replace(
                "Resize the source image to the requested ad sizes.",
                "",
                1,
            ).strip()
            resize_preserve_elements = preserve_elements or None
            resize_prompt_overrides = {
                size.strip(): value.strip()
                for size, value in (request.resize_prompt_overrides or {}).items()
                if size and isinstance(value, str) and value.strip()
            }
            resize_negative_prompt_override = (
                request.resize_negative_prompt_override.strip()
                if isinstance(request.resize_negative_prompt_override, str)
                and request.resize_negative_prompt_override.strip()
                else None
            )
            generated_raw_by_size: dict[str, list[bytes]] = {}
            actual_prompt_by_size: dict[str, str] = {}
            total_sizes = max(1, len(requested_sizes))

            for size_index, size in enumerate(requested_sizes):
                start_progress = 20 + int((size_index / total_sizes) * 45)
                if not _mark_generation_progress(
                    job,
                    start_progress,
                    f"Generating resize {size_index + 1}/{total_sizes}: {size}...",
                ):
                    return

                generation_size = {"728x90": "728x180"}.get(size, size)
                target_w, target_h = _parse_size(generation_size)
                openai_size = get_openai_size(target_w or 1024, target_h or 1024, model)
                override_prompt = resize_prompt_overrides.get(size)
                if override_prompt:
                    enriched_prompt = override_prompt
                    if resize_negative_prompt_override and "negative prompt:" not in override_prompt.lower():
                        enriched_prompt = (
                            f"{override_prompt}\n\nNegative Prompt: "
                            f"{resize_negative_prompt_override}"
                        )
                else:
                    enriched_prompt = build_resize_prompt(
                        target_size=size,
                        user_note=resize_user_note,
                        preserve_elements=resize_preserve_elements,
                        negative_prompt_override=resize_negative_prompt_override,
                    )
                actual_prompt_by_size[size] = enriched_prompt
                b64_images = await _dispatch_generation(
                    enriched_prompt,
                    provider=request.provider,
                    model=model,
                    variants=request.variants,
                    reference_images=[source_bytes],
                    openai_size=openai_size,
                    target_size=generation_size,
                )
                generated_raw_by_size[size] = [
                    base64.b64decode(b64) for b64 in b64_images if b64
                ]
                if not generated_raw_by_size[size]:
                    raise RuntimeError(
                        f"Resize returned no image output for {size}; the job was not completed."
                    )

                done_progress = 20 + int(((size_index + 1) / total_sizes) * 45)
                if not _mark_generation_progress(
                    job,
                    done_progress,
                    f"Generated resize {size_index + 1}/{total_sizes}: {size}.",
                ):
                    return

            if not _mark_generation_progress(job, 76, "Exporting resize outputs..."):
                return

            asset_ids: list[str] = []
            created_assets: list[Asset] = []
            for size_index, size in enumerate(requested_sizes):
                export_progress = 76 + int((size_index / total_sizes) * 14)
                if not _mark_generation_progress(
                    job,
                    export_progress,
                    f"Saving resize output {size_index + 1}/{total_sizes}: {size}...",
                ):
                    return

                if size == "728x90":
                    exported_assets = await _export_oversampled_728x180_resize_assets(
                        job=job,
                        raw_outputs=generated_raw_by_size.get(size, []),
                        workspace_id=request.workspace_id,
                        created_by=user.id,
                        provider=request.provider,
                        model=model,
                        label=request.theme or "Resize",
                        theme=request.theme,
                        source_asset=source_asset,
                        created_at=now,
                    )
                else:
                    exported_assets = await _export_master_images_to_assets(
                        job=job,
                        raw_outputs=generated_raw_by_size.get(size, []),
                        workspace_id=request.workspace_id,
                        created_by=user.id,
                        provider=request.provider,
                        model=model,
                        label=request.theme or "Resize",
                        theme=request.theme,
                        requested_sizes=[size],
                        source_asset=source_asset,
                        context_assets=[source_asset] if source_asset else [],
                        created_at=now,
                        include_kakao_gacha_disclosure=request.resize_include_gacha_disclosure,
                    )
                for asset in exported_assets:
                    asset.prompt_hash = prompt_hash
                    asset.analysis = {
                        **(asset.analysis or {}),
                        "source_prompt": request.prompt,
                        "request_prompt": request.prompt,
                        "actual_resize_prompt": actual_prompt_by_size.get(size, request.prompt),
                        "target_size": size,
                        "resize_requested_size": size,
                        "resize_prompt_override_used": size in resize_prompt_overrides,
                        "resize_negative_prompt_override": resize_negative_prompt_override,
                        "resize_include_gacha_disclosure": bool(
                            request.resize_include_gacha_disclosure and size in _RESIZE_GACHA_DISCLOSURE_SIZES
                        ),
                        "resize_generation_canvas_size": {"728x90": "728x180"}.get(size, size),
                        "resize_pipeline": (
                            "v2_oversampled_split_generation"
                            if size == "728x90"
                            else "v2_simple_per_size_generation"
                        ),
                    }
                    upsert_asset(asset)
                    asset_ids.append(asset.id)
                created_assets.extend(exported_assets)

            if job.status != JobStatus.running:
                return

            if request.include_gif and asset_ids:
                try:
                    from app.incept.gif_generator import generate_cta_pulse_gif, is_gif_allowed_for_size

                    gif_asset_ids: list[str] = []
                    for asset_id in asset_ids:
                        asset_obj = ASSETS.get(asset_id)
                        if not asset_obj or not asset_obj.preview_url:
                            continue
                        size_str = (
                            f"{asset_obj.width}x{asset_obj.height}"
                            if asset_obj.width and asset_obj.height
                            else ""
                        )
                        if not is_gif_allowed_for_size(size_str):
                            continue
                        img_bytes = read_asset_bytes(asset_obj)
                        if not img_bytes:
                            continue
                        gif_bytes = generate_cta_pulse_gif(
                            image_bytes=img_bytes,
                            target_size=size_str,
                            anchors=(asset_obj.analysis or {}).get("anchors") if asset_obj.analysis else None,
                        )
                        gif_asset_id = f"{asset_id}_gif"
                        gif_path = STATIC_DIR / f"{gif_asset_id}.gif"
                        gif_path.write_bytes(gif_bytes)
                        gif_preview_url = f"/static/generated/{gif_asset_id}.gif"
                        gif_asset = Asset(
                            id=gif_asset_id,
                            title=f"{asset_obj.title} (GIF)",
                            type="gif",
                            gcs_uri="",
                            preview_url=gif_preview_url,
                            provider=request.provider,
                            model=model,
                            workspace_id=request.workspace_id,
                            job_id=job_id,
                            prompt_hash=prompt_hash,
                            created_by=user.id,
                            created_at=now,
                            width=asset_obj.width,
                            height=asset_obj.height,
                            theme=asset_obj.theme,
                            asset_role=AssetRole.generated,
                            thread_id=job.thread_id,
                            parent_asset_id=asset_id,
                            root_asset_id=asset_id,
                        )
                        gif_asset.gcs_uri = _upload_bytes_to_gcs(
                            content=gif_bytes,
                            object_path=_build_gcs_object_path(
                                category="gifs",
                                workspace_id=request.workspace_id,
                                created_at=now,
                                job_id=job_id,
                                filename=f"{gif_asset_id}.gif",
                            ),
                            content_type="image/gif",
                        )
                        _record_asset_storage_status(gif_asset, category="gifs")
                        ASSETS[gif_asset_id] = gif_asset
                        upsert_asset(gif_asset)
                        gif_asset_ids.append(gif_asset_id)
                    if gif_asset_ids:
                        asset_ids = asset_ids + gif_asset_ids
                        logger.info("Generated %d GIF(s) for resize job %s", len(gif_asset_ids), job_id)
                except Exception:
                    logger.warning("GIF generation failed for resize job %s — skipping", job_id, exc_info=True)

            job.output_asset_ids = asset_ids
            job.status = JobStatus.completed
            job.progress = 100
            job.message = (
                f"Generated {len(asset_ids)} resize assets with {provider_label}: "
                f"{request.variants} variants × {len(requested_sizes)} sizes."
            )
            job.updated_at = utcnow_naive()

            if job.thread_id:
                thread_store.add_assistant_message(
                    job.thread_id,
                    text=f"Generated resize images: {request.prompt}",
                    asset_ids=asset_ids,
                    job_id=job_id,
                )

            _record_usage(job, request, user, model, prompt_hash, now)
            return

        if request.generation_mode == GenerationMode.theme_create:
            if not _mark_generation_progress(job, 15, "Planning Theme Create prompt..."):
                return

            from app.incept.composite import get_openai_size

            mode = request.theme_create_mode
            if mode is None:
                raise RuntimeError("Theme Create mode is required")

            source_assets = [_get_asset(asset_id) for asset_id in request.source_asset_ids]
            source_assets = [asset for asset in source_assets if asset]
            reference_assets = [_get_asset(asset_id) for asset_id in request.reference_asset_ids]
            reference_assets = [asset for asset in reference_assets if asset]
            client_assets = [_get_asset(asset_id) for asset_id in request.client_asset_ids]
            client_assets = [asset for asset in client_assets if asset]

            source_bytes_list = [_load_asset_bytes(asset) for asset in source_assets]
            source_bytes_list = [data for data in source_bytes_list if data]
            reference_bytes_list = [_load_asset_bytes(asset) for asset in reference_assets]
            reference_bytes_list = [data for data in reference_bytes_list if data]
            client_bytes_list = [_load_asset_bytes(asset) for asset in client_assets]
            client_bytes_list = [data for data in client_bytes_list if data]

            if mode == "style_modify":
                if not source_bytes_list:
                    raise RuntimeError("Theme Create Style Modify requires a source image")
                enriched_prompt = build_theme_create_style_modify_prompt(
                    style_name=(request.theme_create_style_name or "").strip(),
                    style_details=(request.theme_create_style_details or "").strip(),
                    prompt_template=(request.prompt or "").strip(),
                )
                reference_image_bytes = [source_bytes_list[0]]
            elif mode == "style_transfer":
                if len(source_bytes_list) < 1 or len(reference_bytes_list) < 1:
                    raise RuntimeError("Theme Create Style Transfer requires a source image and a style reference image")
                enriched_prompt = build_theme_create_style_transfer_prompt(
                    prompt_template=(request.prompt or "").strip(),
                )
                reference_image_bytes = [source_bytes_list[0], reference_bytes_list[0]]
            else:
                raise RuntimeError(f"Unsupported Theme Create mode: {mode}")

            # Gemini image editing accepts a fixed set of native aspect ratios.
            # Theme Create intentionally exposes only the two production canvases
            # below; use Resize for arbitrary ad sizes after this step.
            requested_theme_sizes = request.output_sizes or ["1920x1080"]
            # A browser tab opened before the native-size update may still send
            # the former fixed Theme Create canvas. Upgrade that legacy request
            # rather than making the user lose an otherwise valid generation.
            requested_theme_sizes = [
                "1920x1080" if size == "1200x628" else size
                for size in requested_theme_sizes
            ]
            supported_theme_sizes = {"1920x1080", "1080x1920"}
            unsupported_theme_sizes = [size for size in requested_theme_sizes if size not in supported_theme_sizes]
            if unsupported_theme_sizes:
                raise ValueError(
                    "Theme Create supports only Gemini-native 16:9 (1920x1080) "
                    "or 9:16 (1080x1920) output. Use Resize for other dimensions."
                )
            generated_raw_by_size: dict[str, list[bytes]] = {}
            actual_prompt_by_size: dict[str, str] = {}
            total_sizes = max(1, len(requested_theme_sizes))

            for size_index, size in enumerate(requested_theme_sizes):
                start_progress = 20 + int((size_index / total_sizes) * 45)
                if not _mark_generation_progress(
                    job,
                    start_progress,
                    f"Generating Theme Create {size_index + 1}/{total_sizes}: {size}...",
                ):
                    return

                target_w, target_h = _parse_size(size)
                openai_size = get_openai_size(target_w or 1024, target_h or 1024, model)
                actual_prompt_by_size[size] = enriched_prompt
                b64_images = await _dispatch_generation(
                    enriched_prompt,
                    provider=request.provider,
                    model=model,
                    variants=request.variants,
                    reference_images=reference_image_bytes,
                    openai_size=openai_size,
                    target_size=size,
                )
                generated_raw_by_size[size] = [
                    base64.b64decode(b64) for b64 in b64_images if b64
                ]
                if not generated_raw_by_size[size]:
                    raise RuntimeError(
                        f"Theme Create returned no image output for {size}; the job was not completed."
                    )

                done_progress = 20 + int(((size_index + 1) / total_sizes) * 45)
                if not _mark_generation_progress(
                    job,
                    done_progress,
                    f"Generated Theme Create {size_index + 1}/{total_sizes}: {size}.",
                ):
                    return

            if not _mark_generation_progress(job, 76, "Exporting Theme Create outputs..."):
                return

            asset_ids: list[str] = []
            for size_index, size in enumerate(requested_theme_sizes):
                export_progress = 76 + int((size_index / total_sizes) * 14)
                if not _mark_generation_progress(
                    job,
                    export_progress,
                    f"Saving Theme Create output {size_index + 1}/{total_sizes}: {size}...",
                ):
                    return

                exported_assets = await _export_master_images_to_assets(
                    job=job,
                    raw_outputs=generated_raw_by_size.get(size, []),
                    workspace_id=request.workspace_id,
                    created_by=user.id,
                    provider=request.provider,
                    model=model,
                    label=request.theme or "Theme Create",
                    theme=request.theme,
                    requested_sizes=[size],
                    source_asset=source_assets[0] if source_assets else None,
                    context_assets=[*source_assets, *reference_assets, *client_assets],
                    created_at=now,
                )
                for asset in exported_assets:
                    asset.prompt_hash = prompt_hash
                    asset.analysis = {
                        **(asset.analysis or {}),
                        "source_prompt": request.prompt,
                        "request_prompt": request.prompt,
                        "actual_theme_create_prompt": actual_prompt_by_size.get(size, request.prompt),
                        "target_size": size,
                        "theme_create_mode": mode,
                        "theme_create_pipeline": "v1_fixed_mode_prompt",
                    }
                    upsert_asset(asset)
                    asset_ids.append(asset.id)

            job.output_asset_ids = asset_ids
            job.status = JobStatus.completed
            job.progress = 100
            job.message = (
                f"Generated {len(asset_ids)} Theme Create assets with {provider_label}: "
                f"{request.variants} variants × {len(requested_theme_sizes)} sizes."
            )
            job.updated_at = utcnow_naive()

            if job.thread_id:
                thread_store.add_assistant_message(
                    job.thread_id,
                    text=f"Generated Theme Create images: {request.prompt}",
                    asset_ids=asset_ids,
                    job_id=job_id,
                )

            _record_usage(job, request, user, model, prompt_hash, now)
            return

        if request.generation_mode == GenerationMode.remediation:
            if not _mark_generation_progress(job, 15, "Planning remediation prompt..."):
                return

            from app.incept.composite import get_openai_size

            if not source_asset:
                raise RuntimeError("Image remediation requires a source image")

            source_bytes = _load_asset_bytes(source_asset)
            if not source_bytes:
                raise RuntimeError("Image remediation requires a readable source image")

            source_width = source_asset.width
            source_height = source_asset.height
            if not source_width or not source_height:
                source_width, source_height = _read_image_size(source_bytes)
            original_size = (
                f"{source_width}x{source_height}"
                if source_width and source_height
                else None
            )
            requested_remediation_sizes = request.output_sizes or ([original_size] if original_size else ["1200x628"])
            if request.remediation_analysis:
                matching_analysis = next(
                    (item for item in request.remediation_analysis if item.asset_id == source_asset.id),
                    request.remediation_analysis[0],
                )
            else:
                matching_analysis = analyze_remediation_assets(
                    RemediationAnalysisRequest(
                        workspace_id=request.workspace_id,
                        source_asset_ids=[source_asset.id],
                        prompt=request.prompt or "",
                        created_by=user.id,
                    ),
                    user.id,
                ).results[0]

            analysis_summary = _build_remediation_analysis_summary(matching_analysis)
            direct_model_prompt = (matching_analysis.remediation_prompt or "").strip()
            user_note = (request.prompt or "").strip()
            if direct_model_prompt:
                enriched_prompt = direct_model_prompt
                if user_note:
                    enriched_prompt = (
                        f"{direct_model_prompt}\n\n"
                        f"Additional user note: {user_note}"
                    )
            else:
                violation_categories = {
                    (violation.category or "").strip().lower()
                    for violation in matching_analysis.violations
                    if (violation.category or "").strip()
                }
                aggressive_personality_recast = bool(
                    violation_categories
                    & {
                        "personality_rights",
                        "impersonation",
                        "celebrity",
                        "celebrity_ip",
                        "likeness",
                    }
                )
                enriched_prompt = build_image_remediation_prompt(
                    analysis_summary=analysis_summary,
                    user_note=user_note,
                    aggressive_personality_recast=aggressive_personality_recast,
                )
            generated_raw_by_size: dict[str, list[bytes]] = {}
            total_sizes = max(1, len(requested_remediation_sizes))

            for size_index, size in enumerate(requested_remediation_sizes):
                start_progress = 20 + int((size_index / total_sizes) * 45)
                if not _mark_generation_progress(
                    job,
                    start_progress,
                    f"Generating remediation {size_index + 1}/{total_sizes}: {size}...",
                ):
                    return

                target_w, target_h = _parse_size(size)
                openai_size = get_openai_size(target_w or 1200, target_h or 628, model)
                b64_images = await _dispatch_generation(
                    enriched_prompt,
                    provider=request.provider,
                    model=model,
                    variants=request.variants,
                    reference_images=[source_bytes],
                    openai_size=openai_size,
                    target_size=size,
                )
                generated_raw_by_size[size] = [
                    base64.b64decode(b64) for b64 in b64_images if b64
                ]

                done_progress = 20 + int(((size_index + 1) / total_sizes) * 45)
                if not _mark_generation_progress(
                    job,
                    done_progress,
                    f"Generated remediation {size_index + 1}/{total_sizes}: {size}.",
                ):
                    return

            if not _mark_generation_progress(job, 76, "Exporting remediation outputs..."):
                return

            asset_ids: list[str] = []
            for size_index, size in enumerate(requested_remediation_sizes):
                export_progress = 76 + int((size_index / total_sizes) * 14)
                if not _mark_generation_progress(
                    job,
                    export_progress,
                    f"Saving remediation output {size_index + 1}/{total_sizes}: {size}...",
                ):
                    return

                exported_assets = await _export_master_images_to_assets(
                    job=job,
                    raw_outputs=generated_raw_by_size.get(size, []),
                    workspace_id=request.workspace_id,
                    created_by=user.id,
                    provider=request.provider,
                    model=model,
                    label=request.theme or "Image Remediation",
                    theme=request.theme,
                    requested_sizes=[size],
                    source_asset=source_asset,
                    context_assets=[source_asset],
                    created_at=now,
                )
                for asset in exported_assets:
                    asset.prompt_hash = prompt_hash
                    asset.analysis = {
                        **(asset.analysis or {}),
                        "source_prompt": request.prompt,
                        "request_prompt": request.prompt,
                        "actual_remediation_prompt": enriched_prompt,
                        "remediation_analysis": matching_analysis.model_dump(),
                        "target_size": size,
                        "remediation_pipeline": "v1_fixed_system_prompt",
                    }
                    upsert_asset(asset)
                    asset_ids.append(asset.id)

            job.output_asset_ids = asset_ids
            job.status = JobStatus.completed
            job.progress = 100
            job.message = (
                f"Generated {len(asset_ids)} remediation assets with {provider_label}: "
                f"{request.variants} variants × {len(requested_remediation_sizes)} sizes."
            )
            job.updated_at = utcnow_naive()

            if job.thread_id:
                thread_store.add_assistant_message(
                    job.thread_id,
                    text=f"Generated remediation images: {request.prompt or 'Auto-remediation'}",
                    asset_ids=asset_ids,
                    job_id=job_id,
                )

            _record_usage(job, request, user, model, prompt_hash, now)
            return

        if not _mark_generation_progress(job, 15, "Planning generation prompts..."):
            return

        from app.incept.composite import get_openai_size
        reference_image_bytes = [
            data
            for asset in context_assets[:8]
            if (data := _load_asset_bytes(asset))
        ]
        generation_prompt_base = request.prompt
        generation_preserve_elements = preserve_elements or None
        generated_raw_by_size: dict[str, list[bytes]] = {}
        total_sizes = max(1, len(requested_sizes))

        for size_index, size in enumerate(requested_sizes):
            start_progress = 20 + int((size_index / total_sizes) * 45)
            if not _mark_generation_progress(
                job,
                start_progress,
                f"Generating {size_index + 1}/{total_sizes}: {size}...",
            ):
                return

            target_w, target_h = _parse_size(size)
            openai_size = get_openai_size(target_w or 1024, target_h or 1024, model)
            size_prompt_base = _single_size_prompt_text(
                generation_prompt_base,
                target_size=size,
                requested_sizes=requested_sizes,
            )
            prompt_builder = (
                build_reference_generation_prompt if reference_image_bytes else build_generation_prompt
            )
            enriched_prompt = prompt_builder(
                user_request=size_prompt_base,
                target_size=size,
                style_hint=request.theme or None,
                preserve_elements=generation_preserve_elements,
            )
            b64_images = await _dispatch_generation(
                enriched_prompt,
                provider=request.provider,
                model=model,
                variants=request.variants,
                reference_images=reference_image_bytes,
                openai_size=openai_size,
                target_size=size,
            )
            generated_raw_by_size[size] = [
                base64.b64decode(b64) for b64 in b64_images if b64
            ]
            done_progress = 20 + int(((size_index + 1) / total_sizes) * 45)
            if not _mark_generation_progress(
                job,
                done_progress,
                f"Generated {size_index + 1}/{total_sizes}: {size}.",
            ):
                return

        if not _mark_generation_progress(job, 70, "Preparing exact-size assets..."):
            return

        asset_ids: list[str] = []
        created_assets: list[Asset] = []
        for size_index, size in enumerate(requested_sizes):
            export_progress = 74 + int((size_index / total_sizes) * 18)
            if not _mark_generation_progress(
                job,
                export_progress,
                f"Rendering output {size_index + 1}/{total_sizes}: {size}...",
            ):
                return
            exported_assets = await _export_master_images_to_assets(
                job=job,
                raw_outputs=generated_raw_by_size.get(size, []),
                workspace_id=request.workspace_id,
                created_by=user.id,
                provider=request.provider,
                model=model,
                label=request.theme or "Generated",
                theme=request.theme,
                requested_sizes=[size],
                source_asset=source_asset,
                context_assets=context_assets,
                created_at=now,
            )
            for asset in exported_assets:
                asset.prompt_hash = prompt_hash
                asset.analysis = {
                    **(asset.analysis or {}),
                    "source_prompt": request.prompt,
                }
                upsert_asset(asset)
                asset_ids.append(asset.id)
            created_assets.extend(exported_assets)
            done_progress = 74 + int(((size_index + 1) / total_sizes) * 18)
            if not _mark_generation_progress(
                job,
                done_progress,
                f"Rendered output {size_index + 1}/{total_sizes}: {size}.",
            ):
                return

        if not _mark_generation_progress(job, 94, "Finalizing generated assets..."):
            return

        job.output_asset_ids = asset_ids
        job.status = JobStatus.completed
        job.progress = 100
        job.message = (
            f"Generated {len(asset_ids)} assets with {provider_label}: "
            f"{request.variants} variants × {len(requested_sizes)} sizes."
        )
        job.updated_at = utcnow_naive()

        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text=f"Generated images: {request.prompt}",
                asset_ids=asset_ids,
                job_id=job_id,
            )

        _record_usage(job, request, user, model, prompt_hash, now)

    except Exception as exc:
        logger.exception("Image generation failed for job %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        error_summary = f"{exc.__class__.__name__}: {str(exc)}"[:500]
        job.message = (
            f"Image generation failed: {error_summary}"
        )
        job.updated_at = utcnow_naive()
        upsert_job(job)


def create_edit_job(request: "ImageEditRequest", user: User) -> GenerationJob:
    """Create a job record for an inpainting edit. Background task fills it."""
    job_id = f"job_{uuid4().hex[:12]}"
    lineage_key = f"llg_edit_{uuid4().hex[:16]}"
    now = utcnow_naive()
    source_asset = _get_asset(request.asset_id)
    thread = _resolve_thread_for_request(
        workspace_id=request.workspace_id,
        created_by=user.id,
        generation_mode=GenerationMode.free_create,
        thread_id=request.thread_id,
        prompt=request.theme or request.prompt,
        source_asset_id=source_asset.id if source_asset else None,
    )

    job = GenerationJob(
        job_id=job_id,
        workspace_id=request.workspace_id,
        status=JobStatus.running,
        progress=0,
        lineage_key=lineage_key,
        message="Editing image…",
        tool_id="gemini-image-edit" if _is_gemini_image_model(request.model) else "openai-image-edit",
        title=f"Image edit — {request.prompt[:40]}",
        output_asset_ids=[],
        thread_id=thread.thread_id,
        source_asset_id=source_asset.id if source_asset else None,
        created_at=now,
        updated_at=now,
    )
    JOBS[job_id] = job
    upsert_job(job)
    return job


def create_generate_gif_job(request: "GenerateGifRequest", user: User) -> GenerationJob:
    source_asset = _get_asset(request.asset_id)
    thread = _resolve_thread_for_request(
        workspace_id=request.workspace_id,
        created_by=user.id,
        generation_mode=GenerationMode.free_create,
        thread_id=request.thread_id,
        prompt="Generate GIF",
        source_asset_id=source_asset.id if source_asset else None,
    )
    return _make_simple_job(
        "generate-gif",
        "Generate GIF",
        request.workspace_id,
        thread_id=thread.thread_id,
        source_asset_id=source_asset.id if source_asset else None,
    )


def create_kakao_clean_job(request: "KakaoCleanRequest", user: User) -> GenerationJob:
    source_asset = _get_asset(request.asset_id)
    thread = _resolve_thread_for_request(
        workspace_id=request.workspace_id,
        created_by=user.id,
        generation_mode=GenerationMode.free_create,
        thread_id=request.thread_id,
        prompt="Kakao Clean",
        source_asset_id=source_asset.id if source_asset else None,
    )
    return _make_simple_job(
        "kakao-clean",
        "Kakao Clean",
        request.workspace_id,
        thread_id=thread.thread_id,
        source_asset_id=source_asset.id if source_asset else None,
    )


def create_kakao_bizboard_job(
    request: "KakaoBizboardComposeRequest",
    user: User,
) -> GenerationJob:
    source_asset = _get_asset(request.cleaned_asset_id)
    thread = _resolve_thread_for_request(
        workspace_id=request.workspace_id,
        created_by=user.id,
        generation_mode=GenerationMode.free_create,
        thread_id=request.thread_id,
        prompt=request.main_copy or "Kakao Bizboard",
        source_asset_id=source_asset.id if source_asset else None,
    )
    return _make_simple_job(
        "kakao-bizboard",
        "Kakao Bizboard",
        request.workspace_id,
        thread_id=thread.thread_id,
        source_asset_id=source_asset.id if source_asset else None,
    )


async def run_kakao_clean_background(
    job_id: str,
    request: "KakaoCleanRequest",
    user: User,
) -> None:
    job = JOBS.get(job_id)
    if not job:
        return

    settings = get_settings()
    effective_model = settings.vertex_gemini_image_model
    now = utcnow_naive()

    try:
        original_asset = _get_asset(request.asset_id)
        if not original_asset:
            raise ValueError(f"Asset {request.asset_id} not found")

        original_bytes = read_asset_bytes(original_asset)
        if not original_bytes:
            raise FileNotFoundError(f"Image bytes not found for {request.asset_id}")
        job.progress = 20
        job.updated_at = utcnow_naive()
        upsert_job(job)

        b64_images = await _generate_kakao_clean_image(
            prompt=KAKAO_CLEAN_PROMPT,
            source_image=original_bytes,
            model=effective_model,
        )
        if not b64_images:
            raise RuntimeError("Kakao clean returned no image data")

        job.progress = 80
        job.updated_at = utcnow_naive()
        upsert_job(job)

        raw_outputs = [base64.b64decode(b64) for b64 in b64_images if b64]
        created_assets = await _export_master_images_to_assets(
            job=job,
            raw_outputs=raw_outputs,
            workspace_id=request.workspace_id,
            created_by=user.id,
            provider="gemini",
            model=effective_model,
            label="Kakao Clean",
            theme="Kakao Clean",
            requested_sizes=[],
            source_asset=original_asset,
            context_assets=[original_asset],
            created_at=now,
        )
        asset_ids = [asset.id for asset in created_assets]
        prompt_hash = sha256(KAKAO_CLEAN_PROMPT.encode()).hexdigest()[:16]
        for asset in created_assets:
            asset.prompt_hash = prompt_hash
            upsert_asset(asset)

        job.output_asset_ids = asset_ids
        job.status = JobStatus.completed
        job.progress = 100
        job.message = "Kakao clean completed."
        job.updated_at = utcnow_naive()
        upsert_job(job)

        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text="Kakao cleaned image",
                asset_ids=asset_ids,
                job_id=job_id,
            )
            thread_store.touch_thread(
                job.thread_id,
                latest_job_id=job.job_id,
                latest_asset_id=asset_ids[-1] if asset_ids else None,
                cover_asset_id=asset_ids[0] if asset_ids else None,
                title="Kakao Clean",
            )
    except Exception as exc:
        logger.exception("Kakao clean failed for job %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        error_summary = f"{exc.__class__.__name__}: {str(exc)}"[:500]
        job.message = f"Kakao clean failed: {error_summary}"
        job.updated_at = utcnow_naive()
        upsert_job(job)


async def run_generate_gif_background(
    job_id: str,
    request: "GenerateGifRequest",
    user: User,
) -> None:
    job = JOBS.get(job_id)
    if not job:
        return

    now = utcnow_naive()

    try:
        source_asset = _get_asset(request.asset_id)
        if not source_asset:
            raise ValueError(f"Asset {request.asset_id} not found")
        if source_asset.type == "gif":
            raise ValueError("Selected asset is already a GIF")

        if not _mark_generation_progress(job, 20, "Loading source image for GIF generation..."):
            return

        image_bytes = read_asset_bytes(source_asset)
        if not image_bytes:
            raise FileNotFoundError(f"Image bytes not found for {request.asset_id}")
        width = source_asset.width
        height = source_asset.height
        if not width or not height:
            width, height = _read_image_size(image_bytes)
        size_str = f"{width}x{height}" if width and height else ""

        from app.incept.gif_generator import generate_cta_pulse_gif, is_gif_allowed_for_size

        if not size_str or not is_gif_allowed_for_size(size_str):
            raise ValueError(
                "GIF generation is only supported for 320x50, 728x90, 1200x222, "
                "640x100, 300x250, 360x640, 640x360, and 480x480."
            )

        if not _mark_generation_progress(job, 55, f"Generating CTA pulse GIF for {size_str}..."):
            return

        gif_bytes = generate_cta_pulse_gif(
            image_bytes=image_bytes,
            target_size=size_str,
            anchors=(source_asset.analysis or {}).get("anchors") if source_asset.analysis else None,
        )

        gif_asset_id = f"{job.lineage_key}_{size_str}_gif"
        gif_path = STATIC_DIR / f"{gif_asset_id}.gif"
        gif_path.write_bytes(gif_bytes)
        gif_preview_url = f"/static/generated/{gif_asset_id}.gif"
        prompt_hash = sha256(f"generate-gif|{request.asset_id}|{size_str}".encode()).hexdigest()[:16]
        gif_base_title = _normalized_source_title(source_asset.title) if source_asset.title else "Generated"
        gif_asset = Asset(
            id=gif_asset_id,
            title=f"{gif_base_title}_gif1",
            type="gif",
            gcs_uri="",
            preview_url=gif_preview_url,
            provider="internal",
            model="cta-pulse-gif",
            workspace_id=request.workspace_id,
            job_id=job.job_id,
            prompt_hash=prompt_hash,
            created_by=user.id,
            created_at=now,
            width=width,
            height=height,
            theme=source_asset.theme,
            asset_role=AssetRole.generated,
            analysis={
                "source_prompt": "Generate CTA pulse GIF from existing static asset.",
                "gif_pipeline": "cta_pulse_v1",
                "target_size": size_str,
            },
            thread_id=job.thread_id,
            parent_asset_id=source_asset.id,
            root_asset_id=_inherit_root_asset_id(source_asset, gif_asset_id),
        )
        gif_asset.gcs_uri = _upload_bytes_to_gcs(
            content=gif_bytes,
            object_path=_build_gcs_object_path(
                category="gifs",
                workspace_id=request.workspace_id,
                created_at=now,
                job_id=job.job_id,
                filename=f"{gif_asset_id}.gif",
            ),
            content_type="image/gif",
        )
        _record_asset_storage_status(gif_asset, category="gifs")
        ASSETS[gif_asset_id] = gif_asset
        upsert_asset(gif_asset)

        job.output_asset_ids = [gif_asset_id]
        job.status = JobStatus.completed
        job.progress = 100
        job.message = f"Generated GIF for {size_str}."
        job.updated_at = utcnow_naive()
        upsert_job(job)

        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text=f"Generated GIF from {source_asset.title}",
                asset_ids=[gif_asset_id],
                job_id=job_id,
            )
            thread_store.touch_thread(
                job.thread_id,
                latest_job_id=job.job_id,
                latest_asset_id=gif_asset_id,
                cover_asset_id=gif_asset_id,
                title=source_asset.theme or source_asset.title or "Generated GIF",
            )
    except Exception as exc:
        logger.exception("Generate GIF failed for job %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        job.message = f"Generate GIF failed: {str(exc).strip() or exc.__class__.__name__}"
        job.updated_at = utcnow_naive()
        upsert_job(job)


async def run_kakao_bizboard_background(
    job_id: str,
    request: "KakaoBizboardComposeRequest",
    user: User,
) -> None:
    job = JOBS.get(job_id)
    if not job:
        return

    now = utcnow_naive()

    try:
        cleaned_asset = _get_asset(request.cleaned_asset_id)
        if not cleaned_asset:
            raise ValueError(f"Cleaned asset {request.cleaned_asset_id} not found")

        composed_asset = _get_asset(request.composed_asset_id)
        if not composed_asset:
            raise ValueError(f"Composed asset {request.composed_asset_id} not found")

        composed_bytes = read_asset_bytes(composed_asset)
        if not composed_bytes:
            raise FileNotFoundError(
                f"Composed image bytes not found for {request.composed_asset_id}"
            )
        job.progress = 40
        job.message = "Finalizing Kakao Bizboard asset..."
        job.updated_at = utcnow_naive()
        upsert_job(job)

        created_assets = await _export_master_images_to_assets(
            job=job,
            raw_outputs=[composed_bytes],
            workspace_id=request.workspace_id,
            created_by=user.id,
            provider="kakao",
            model="bizboard-template",
            label="Kakao Bizboard",
            theme="Kakao Bizboard",
            requested_sizes=["960x300"],
            source_asset=cleaned_asset,
            context_assets=[cleaned_asset],
            created_at=now,
        )
        asset_ids = [asset.id for asset in created_assets]

        prompt_hash_source = "|".join([
            request.template,
            request.main_copy.strip(),
            request.sub_copy.strip(),
            request.app_download_copy.strip(),
            request.additional_info.strip(),
            "gacha" if request.gacha else "standard",
        ])
        prompt_hash = sha256(prompt_hash_source.encode()).hexdigest()[:16]
        for asset in created_assets:
            asset.prompt_hash = prompt_hash
            upsert_asset(asset)

        delete_asset(request.composed_asset_id)

        job.output_asset_ids = asset_ids
        job.status = JobStatus.completed
        job.progress = 100
        job.message = "Kakao Bizboard completed."
        job.updated_at = utcnow_naive()
        upsert_job(job)

        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text=f"Kakao Bizboard: {request.main_copy}",
                asset_ids=asset_ids,
                job_id=job_id,
            )
            thread_store.touch_thread(
                job.thread_id,
                latest_job_id=job.job_id,
                latest_asset_id=asset_ids[-1] if asset_ids else None,
                cover_asset_id=asset_ids[0] if asset_ids else None,
                title="Kakao Bizboard",
            )
    except Exception as exc:
        logger.exception("Kakao Bizboard failed for job %s", job_id)
        error_summary = str(exc).strip() or exc.__class__.__name__
        job.status = JobStatus.failed
        job.progress = 0
        job.message = f"Kakao Bizboard failed: {error_summary}"
        job.updated_at = utcnow_naive()
        upsert_job(job)


async def run_edit_background(
    job_id: str,
    request: "ImageEditRequest",
    user: User,
) -> None:
    """Run a direct image edit without legacy orchestration steps."""
    job = JOBS.get(job_id)
    if not job:
        return

    now = utcnow_naive()

    try:
        original_asset = _get_asset(request.asset_id)
        if not original_asset:
            raise ValueError(f"Asset {request.asset_id} not found")

        original_bytes = read_asset_bytes(original_asset)
        if not original_bytes:
            raise FileNotFoundError(f"Image bytes not found for {request.asset_id}")
        mask_bytes: bytes | None = None
        if request.mask_data:
            mask_b64 = request.mask_data
            if "," in mask_b64:
                mask_b64 = mask_b64.split(",", 1)[1]
            mask_bytes = base64.b64decode(mask_b64)

        job.progress = 15
        job.updated_at = utcnow_naive()

        logo_assets = [_get_asset(aid) for aid in (request.extra_asset_ids or []) if _get_asset(aid)]
        job.progress = 25
        job.updated_at = utcnow_naive()

        if _is_gemini_image_model(request.model):
            reference_images = [original_bytes]
            for asset in logo_assets:
                asset_bytes = _load_asset_bytes(asset)
                if asset_bytes:
                    reference_images.append(asset_bytes)

            b64_images = await _generate_images_gemini_from_references(
                prompt=request.prompt,
                reference_images=reference_images,
                model=request.model,
                variants=request.variants,
                target_size=_effective_output_sizes(request.output_sizes, original_asset)[0],
            )
            if not b64_images:
                raise RuntimeError("Gemini image edit returned no image data")

            job.progress = 80
            job.updated_at = utcnow_naive()

            prompt_hash = sha256(request.prompt.encode()).hexdigest()[:16]
            raw_outputs = [base64.b64decode(b64) for b64 in b64_images if b64]
            created_assets = await _export_master_images_to_assets(
                job=job,
                raw_outputs=raw_outputs,
                workspace_id=request.workspace_id,
                created_by=user.id,
                provider="gemini",
                model=request.model,
                label=request.theme or "Edit",
                theme=request.theme or original_asset.theme,
                requested_sizes=request.output_sizes,
                source_asset=original_asset,
                context_assets=[original_asset, *logo_assets],
                created_at=now,
            )
            asset_ids = [asset.id for asset in created_assets]
            for asset in created_assets:
                asset.prompt_hash = prompt_hash
                upsert_asset(asset)

            job.output_asset_ids = asset_ids
            job.status = JobStatus.completed
            job.progress = 100
            job.message = f"Edited {len(asset_ids)} image(s)."
            job.updated_at = utcnow_naive()
            upsert_job(job)

            if job.thread_id:
                thread_store.add_assistant_message(
                    job.thread_id,
                    text=f"Edited image: {request.prompt}",
                    asset_ids=asset_ids,
                    job_id=job_id,
                )
                thread_store.touch_thread(
                    job.thread_id,
                    latest_job_id=job.job_id,
                    latest_asset_id=asset_ids[-1] if asset_ids else None,
                    cover_asset_id=asset_ids[0] if asset_ids else None,
                    title=request.theme or original_asset.theme or None,
                )
            return

        if not mask_bytes:
            job.status = JobStatus.failed
            job.progress = 0
            job.message = "Manual mask required for non-Gemini edits."
            job.updated_at = utcnow_naive()
            upsert_job(job)
            return

        job.progress = 40
        job.updated_at = utcnow_naive()

        b64_images = await _edit_image_openai(
            original_bytes=original_bytes,
            mask_bytes=mask_bytes,
            prompt=request.prompt,
            model=request.model,
            variants=request.variants,
        )

        job.progress = 80
        job.updated_at = utcnow_naive()

        # ── Save output assets ──────────────────────────────────────────────
        prompt_hash = sha256(request.prompt.encode()).hexdigest()[:16]
        raw_outputs: list[bytes] = []
        for b64 in b64_images:
            try:
                raw_outputs.append(base64.b64decode(b64))
            except Exception:
                logger.warning("Could not decode edited output for job %s", job_id)

        created_assets = await _export_master_images_to_assets(
            job=job,
            raw_outputs=raw_outputs,
            workspace_id=request.workspace_id,
            created_by=user.id,
            provider="openai",
            model=request.model,
            label=request.theme or "Edit",
            theme=request.theme or original_asset.theme,
            requested_sizes=request.output_sizes,
            source_asset=original_asset,
            context_assets=[original_asset, *logo_assets],
            created_at=now,
        )
        asset_ids = [asset.id for asset in created_assets]
        for asset in created_assets:
            asset.prompt_hash = prompt_hash
            upsert_asset(asset)

        job.output_asset_ids = asset_ids
        job.status = JobStatus.completed
        job.progress = 100
        job.message = f"Edited {len(asset_ids)} image(s)."
        job.updated_at = utcnow_naive()
        upsert_job(job)

        # ── Update session ──────────────────────────────────────────────────
        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text=f"Edited image: {request.prompt}",
                asset_ids=asset_ids,
                job_id=job_id,
            )
            thread_store.touch_thread(
                job.thread_id,
                latest_job_id=job.job_id,
                latest_asset_id=asset_ids[-1] if asset_ids else None,
                cover_asset_id=asset_ids[0] if asset_ids else None,
                title=request.theme or original_asset.theme or None,
            )
    except Exception as exc:
        logger.exception("Image edit failed for job %s", job_id)
        job.status = JobStatus.failed
        job.progress = 0
        error_summary = f"{exc.__class__.__name__}: {str(exc)}"[:500]
        job.message = f"Image edit failed for model {request.model}: {error_summary}"
        job.updated_at = utcnow_naive()
        upsert_job(job)


# ── Shared helper ─────────────────────────────────────────────────────────────

def _get_asset(asset_id: str) -> "Asset | None":
    """Look up asset in both ASSETS and SOURCE_ASSETS (uploads)."""
    return ASSETS.get(asset_id) or SOURCE_ASSETS.get(asset_id)


def _resolve_asset_path(asset: Asset) -> "Path | None":
    if asset.preview_url == "/static/placeholder.png":
        return STATIC_ROOT / "placeholder.png"
    if asset.preview_url.startswith("/static/generated/"):
        return STATIC_DIR / asset.preview_url[len("/static/generated/"):]
    if asset.preview_url.startswith("/static/uploads/"):
        return UPLOAD_DIR / asset.preview_url[len("/static/uploads/"):]
    return None


def _make_simple_job(
    tool_id: str,
    title: str,
    workspace_id: str,
    thread_id: str | None = None,
    source_asset_id: str | None = None,
) -> GenerationJob:
    job_id = f"job_{uuid4().hex[:12]}"
    lineage_key = f"llg_{tool_id}_{uuid4().hex[:12]}"
    now = utcnow_naive()
    job = GenerationJob(
        job_id=job_id,
        workspace_id=workspace_id,
        status=JobStatus.running,
        progress=0,
        lineage_key=lineage_key,
        message=f"{title}…",
        tool_id=tool_id,
        title=title,
        output_asset_ids=[],
        thread_id=thread_id,
        source_asset_id=source_asset_id,
        created_at=now,
        updated_at=now,
    )
    JOBS[job_id] = job
    upsert_job(job)
    return job


def _save_output_asset(
    job: GenerationJob,
    b64: str,
    label: str,
    provider: str,
    model: str,
    workspace_id: str,
    created_by: str,
    width: "int | None" = None,
    height: "int | None" = None,
    theme: "str | None" = None,
    idx: int = 0,
    parent_asset_id: str | None = None,
    root_asset_id: str | None = None,
) -> Asset:
    asset_id = f"{job.lineage_key}_out_{idx + 1}_img"
    preview_url = _save_image_file(asset_id, b64)

    # Auto-detect dimensions if not provided by the caller
    if width is None or height is None:
        try:
            raw = base64.b64decode(b64)
            width, height = _read_image_size(raw)
        except Exception:
            pass

    now = utcnow_naive()
    asset = Asset(
        id=asset_id,
        title=label,
        type="image",
        gcs_uri="",
        preview_url=preview_url,
        provider=provider,
        model=model,
        workspace_id=workspace_id,
        job_id=job.job_id,
        prompt_hash="",
        created_by=created_by,
        created_at=now,
        width=width,
        height=height,
        theme=theme,
        asset_role=AssetRole.generated,
        thread_id=job.thread_id,
        parent_asset_id=parent_asset_id,
        root_asset_id=root_asset_id or asset_id,
    )
    raw = base64.b64decode(b64)
    asset.gcs_uri = _upload_bytes_to_gcs(
        content=raw,
        object_path=_build_gcs_object_path(
            category="generated",
            workspace_id=workspace_id,
            created_at=now,
            job_id=job.job_id,
            filename=f"{asset_id}.png",
        ),
        content_type="image/png",
    )
    ASSETS[asset_id] = asset
    upsert_asset(asset)
    return asset


# ── Outpaint ──────────────────────────────────────────────────────────────────

def create_outpaint_job(request: OutpaintRequest, user: User) -> GenerationJob:
    source_asset = _get_asset(request.asset_id)
    thread = _resolve_thread_for_request(
        workspace_id=request.workspace_id,
        created_by=user.id,
        generation_mode=GenerationMode.free_create,
        thread_id=request.thread_id,
        prompt=request.prompt or "Outpainting",
        source_asset_id=source_asset.id if source_asset else None,
    )
    return _make_simple_job(
        "outpaint",
        "Outpainting",
        request.workspace_id,
        thread_id=thread.thread_id,
        source_asset_id=source_asset.id if source_asset else None,
    )


async def run_outpaint_background(job_id: str, request: OutpaintRequest, user: User) -> None:
    job = JOBS.get(job_id)
    if not job:
        return

    try:
        original = _get_asset(request.asset_id)
        if not original:
            raise ValueError(f"Asset {request.asset_id} not found")

        original_bytes = read_asset_bytes(original)
        if not original_bytes:
            raise FileNotFoundError("Image bytes not found")

        job.progress = 15
        job.updated_at = utcnow_naive()

        from app.incept.composite import create_outpaint_inputs
        expanded_bytes, mask_bytes = create_outpaint_inputs(
            original_bytes, request.direction, request.ratio, request.target_size
        )

        job.progress = 30
        job.updated_at = utcnow_naive()

        prompt = request.prompt or (
            f"Seamlessly extend this image {request.direction}ward. "
            "Match the existing art style, lighting, colors, characters, and scene. "
            "Continue any elements at the edges naturally."
        )

        b64_list = await _edit_image_openai(
            original_bytes=expanded_bytes,
            mask_bytes=mask_bytes,
            prompt=prompt,
            model=request.model,
            variants=1,
        )

        job.progress = 80
        raw_outputs = [base64.b64decode(b64) for b64 in b64_list]
        created_assets = await _export_master_images_to_assets(
            job=job,
            raw_outputs=raw_outputs,
            workspace_id=request.workspace_id,
            created_by=user.id,
            provider="openai",
            model=request.model,
            label=f"Outpaint {request.direction}",
            theme="outpaint",
            requested_sizes=request.output_sizes,
            source_asset=original,
            context_assets=[original],
        )
        asset_ids = [asset.id for asset in created_assets]

        job.output_asset_ids = asset_ids
        job.status = JobStatus.completed
        job.progress = 100
        job.message = f"Outpainted {request.direction}."
        job.updated_at = utcnow_naive()
        upsert_job(job)
        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text=f"Outpainted image {request.direction}",
                asset_ids=asset_ids,
                job_id=job_id,
            )
            thread_store.touch_thread(
                job.thread_id,
                latest_job_id=job.job_id,
                latest_asset_id=asset_ids[-1] if asset_ids else None,
                cover_asset_id=asset_ids[0] if asset_ids else None,
                title=original.theme or None,
            )

    except Exception:
        logger.exception("Outpaint failed for job %s", job_id)
        job.status = JobStatus.failed
        job.message = "Outpaint failed. Check OPENAI_API_KEY and logs."
        job.updated_at = utcnow_naive()
        upsert_job(job)


# ── Background removal ────────────────────────────────────────────────────────

def create_remove_bg_job(request: RemoveBGRequest, user: User) -> GenerationJob:
    source_asset = _get_asset(request.asset_id)
    thread = _resolve_thread_for_request(
        workspace_id=request.workspace_id,
        created_by=user.id,
        generation_mode=GenerationMode.free_create,
        thread_id=request.thread_id,
        prompt=request.replacement_prompt or "Background removal",
        source_asset_id=source_asset.id if source_asset else None,
    )
    return _make_simple_job(
        "remove-bg",
        "Background Removal",
        request.workspace_id,
        thread_id=thread.thread_id,
        source_asset_id=source_asset.id if source_asset else None,
    )


async def run_remove_bg_background(job_id: str, request: RemoveBGRequest, user: User) -> None:
    job = JOBS.get(job_id)
    if not job:
        return

    try:
        original = _get_asset(request.asset_id)
        if not original:
            raise ValueError(f"Asset {request.asset_id} not found")

        original_bytes = read_asset_bytes(original)
        if not original_bytes:
            raise FileNotFoundError("Image bytes not found")

        job.progress = 20
        job.updated_at = utcnow_naive()

        from app.incept.composite import remove_background
        result_bytes, used_rembg = remove_background(original_bytes)

        if not used_rembg or request.replacement_prompt:
            # Fall back to images.edit for replacement or when rembg unavailable
            prompt = (
                request.replacement_prompt
                or "Remove the background completely. Make the background fully transparent."
            )
            b64_list = await _edit_image_openai(
                original_bytes=original_bytes,
                mask_bytes=None,
                prompt=prompt,
                model=request.model,
                variants=1,
            )
            job.progress = 80
            raw_outputs = [base64.b64decode(b64) for b64 in b64_list]
            created_assets = await _export_master_images_to_assets(
                job=job,
                raw_outputs=raw_outputs,
                workspace_id=request.workspace_id,
                created_by=user.id,
                provider="openai",
                model=request.model,
                label="Background removed",
                theme="no-bg",
                requested_sizes=request.output_sizes,
                source_asset=original,
                context_assets=[original],
            )
            asset_ids = [asset.id for asset in created_assets]
        else:
            # rembg succeeded: save result directly without AI call
            job.progress = 80
            created_assets = await _export_master_images_to_assets(
                job=job,
                raw_outputs=[result_bytes],
                workspace_id=request.workspace_id,
                created_by=user.id,
                provider="rembg",
                model="rembg",
                label="Background removed",
                theme="no-bg",
                requested_sizes=request.output_sizes,
                source_asset=original,
                context_assets=[original],
            )
            asset_ids = [asset.id for asset in created_assets]

        job.output_asset_ids = asset_ids
        job.status = JobStatus.completed
        job.progress = 100
        job.message = "Background removed."
        job.updated_at = utcnow_naive()
        upsert_job(job)
        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text="Removed background",
                asset_ids=asset_ids,
                job_id=job_id,
            )
            thread_store.touch_thread(
                job.thread_id,
                latest_job_id=job.job_id,
                latest_asset_id=asset_ids[-1] if asset_ids else None,
                cover_asset_id=asset_ids[0] if asset_ids else None,
                title=original.theme or None,
            )

    except Exception:
        logger.exception("Remove-BG failed for job %s", job_id)
        job.status = JobStatus.failed
        job.message = "Background removal failed."
        job.updated_at = utcnow_naive()
        upsert_job(job)


# ── Text overlay ──────────────────────────────────────────────────────────────

def create_add_text_job(request: AddTextRequest, user: User) -> GenerationJob:
    source_asset = _get_asset(request.asset_id)
    thread = _resolve_thread_for_request(
        workspace_id=request.workspace_id,
        created_by=user.id,
        generation_mode=GenerationMode.free_create,
        thread_id=request.thread_id,
        prompt=request.text or "Text overlay",
        source_asset_id=source_asset.id if source_asset else None,
    )
    return _make_simple_job(
        "add-text",
        f"Text: {request.text[:30]}",
        request.workspace_id,
        thread_id=thread.thread_id,
        source_asset_id=source_asset.id if source_asset else None,
    )


async def run_add_text_background(job_id: str, request: AddTextRequest, user: User) -> None:
    """Text overlay is pure Pillow — no AI call needed, completes instantly."""
    job = JOBS.get(job_id)
    if not job:
        return

    try:
        original = _get_asset(request.asset_id)
        if not original:
            raise ValueError(f"Asset {request.asset_id} not found")

        original_bytes = read_asset_bytes(original)
        if not original_bytes:
            raise FileNotFoundError("Image bytes not found")

        job.progress = 30
        job.updated_at = utcnow_naive()

        from app.incept.composite import add_text_overlay
        result_bytes = add_text_overlay(
            image_bytes=original_bytes,
            text=request.text,
            position=request.position,
            font_size_ratio=request.font_size_ratio,
        )

        created_assets = await _export_master_images_to_assets(
            job=job,
            raw_outputs=[result_bytes],
            workspace_id=request.workspace_id,
            created_by=user.id,
            provider="pillow",
            model="pillow",
            label=f"Text: {request.text[:20]}",
            theme=request.text[:40],
            requested_sizes=request.output_sizes,
            source_asset=original,
            context_assets=[original],
        )
        asset_ids = [asset.id for asset in created_assets]

        job.output_asset_ids = asset_ids
        job.status = JobStatus.completed
        job.progress = 100
        job.message = f"Text added: {request.text[:40]}"
        job.updated_at = utcnow_naive()
        upsert_job(job)
        if job.thread_id:
            thread_store.add_assistant_message(
                job.thread_id,
                text=f"Added text: {request.text[:40]}",
                asset_ids=asset_ids,
                job_id=job_id,
            )
            thread_store.touch_thread(
                job.thread_id,
                latest_job_id=job.job_id,
                latest_asset_id=asset_ids[-1] if asset_ids else None,
                cover_asset_id=asset_ids[0] if asset_ids else None,
                title=original.theme or request.text[:40],
            )

    except Exception:
        logger.exception("Add-text failed for job %s", job_id)
        job.status = JobStatus.failed
        job.message = "Text overlay failed."
        job.updated_at = utcnow_naive()
        upsert_job(job)
