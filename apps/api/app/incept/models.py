from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.incept.datetime_utils import utcnow_naive


class Role(str, Enum):
    user = "user"
    manager = "manager"
    admin = "admin"


class ToolStatus(str, Enum):
    enabled = "enabled"
    mock = "mock"
    disabled = "disabled"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    pending = "pending"
    needs_clarification = "needs_clarification"


class AssetRole(str, Enum):
    upload = "upload"
    working = "working"
    reference_ad = "reference_ad"
    client_character = "client_character"
    client_logo = "client_logo"
    client_product = "client_product"
    client_background = "client_background"
    brand_element = "brand_element"
    generated = "generated"


class GenerationMode(str, Enum):
    free_create = "free_create"
    style_match = "style_match"
    theme_create = "theme_create"
    resize = "resize"
    remediation = "remediation"
    video = "video"


class ThemeCreateMode(str, Enum):
    style_modify = "style_modify"
    style_transfer = "style_transfer"
    asset_text_replace = "asset_text_replace"


class ThemeCreatePresetVisibility(str, Enum):
    private = "private"
    team = "team"
    global_ = "global"


class VideoGenerationMode(str, Enum):
    image_to_video = "image_to_video"
    playable_to_video = "playable_to_video"
    competitor_style_transfer = "competitor_style_transfer"
    video_to_playable = "video_to_playable"
    first_last_frame = "first_last_frame"
    extend_video = "extend_video"
    reference_character = "reference_character"
    prompt_assist = "prompt_assist"
    multi_shot_storyboard = "multi_shot_storyboard"
    video_remediation = "video_remediation"
    synthetic_recast = "synthetic_recast"


class VideoProductionStage(str, Enum):
    direction = "direction"
    script = "script"
    design = "design"
    storyboard = "storyboard"
    generate = "generate"
    # Retained only so older stored records can be read; normalization moves
    # them to Edit because audio is no longer a separate production stage.
    audio = "audio"
    edit = "edit"
    deliver = "deliver"


class VideoProductionAssetLink(BaseModel):
    asset_id: str
    role: Literal["reference", "brand", "character", "product", "logo", "background", "audio", "generated"] = "reference"
    label: str = ""
    source_note: str = ""
    rights_note: str = ""


class VideoProductionBeat(BaseModel):
    start_seconds: float = 0
    end_seconds: float = 0
    title: str = ""
    purpose: str = ""


class VideoProductionDialogueLine(BaseModel):
    """One exact spoken line in a script scene.

    Keeping dialogue structured prevents the video prompt from having to guess
    who speaks, which language they use, or whether the speaker is visible.
    """

    speaker: str = ""
    text: str = ""
    on_camera: bool = True
    voice_description: str = ""
    delivery: str = ""


class VideoProductionScene(BaseModel):
    id: str
    title: str
    setting: str = ""
    action: str = ""
    dialogue_or_copy: str = ""
    spoken_language: str = ""
    dialogue: list[VideoProductionDialogueLine] = Field(default_factory=list)
    on_screen_text: list[str] = Field(default_factory=list)
    camera_direction: str = ""
    sound_direction: str = ""
    continuity_notes: str = ""
    restrictions: list[str] = Field(default_factory=list)
    character_keys: list[str] = Field(default_factory=list)
    environment_key: str = ""
    prop_keys: list[str] = Field(default_factory=list)
    ui_keys: list[str] = Field(default_factory=list)


class VideoProductionScript(BaseModel):
    revision: int = 1
    status: Literal["draft", "locked"] = "draft"
    creative_goal: str = ""
    audience: str = ""
    logline: str = ""
    style_bible: list[str] = Field(default_factory=list)
    beats: list[VideoProductionBeat] = Field(default_factory=list)
    scenes: list[VideoProductionScene] = Field(default_factory=list)
    brand_rules: list[str] = Field(default_factory=list)
    asset_manifest: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    raw_script: str = ""
    # The editable reading copy and the structured scenes/beats must remain
    # tied together.  Locking rejects a manually edited reading copy until the
    # Screenwriter has explicitly restructured it into the durable plan.
    structured_raw_script_hash: str = ""
    updated_at: datetime = Field(default_factory=utcnow_naive)


class VideoProductionCreativeDirection(BaseModel):
    status: Literal["draft", "approved"] = "draft"
    # User-approved subset of the Strategist's proposed reusable visual states.
    # Empty preserves legacy productions by treating every handoff row as active.
    confirmed_pack_keys: list[str] = Field(default_factory=list)
    reference_summary: str = ""
    # A durable, evidence-only record produced before strategy.  Keeping it
    # separate from the adaptation prevents a later role from silently
    # replacing what was actually present in the reference video.
    reference_analysis: dict[str, Any] = Field(default_factory=dict)
    commercial_type: str = ""
    strengths_to_adapt: list[str] = Field(default_factory=list)
    story_structure: list[str] = Field(default_factory=list)
    scene_and_character_notes: list[str] = Field(default_factory=list)
    camera_and_pacing: list[str] = Field(default_factory=list)
    music_direction: list[str] = Field(default_factory=list)
    asset_request: list[str] = Field(default_factory=list)
    originality_guardrails: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    # The Creative Strategist chooses representative moments from a reference
    # video. Design extracts these as stills instead of sending the full video
    # to the image model.
    reference_frame_plan: list[dict[str, Any]] = Field(default_factory=list)
    # Contract handed to the Production Designer. It identifies which visual
    # state each future Pack needs and whether it needs a brand asset, a
    # reference-frame briefing, or can be generated from an original prompt.
    design_handoff: list[dict[str, Any]] = Field(default_factory=list)
    # Strategist's explicit audit of visual entities in the story. The handoff
    # is reconciled against this inventory before it reaches Design.
    visual_inventory: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    output_language: str = ""
    analyzed_asset_ids: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utcnow_naive)


class VideoProductionDesignSheet(BaseModel):
    """A controlled contact sheet used to lock a reusable production asset state."""

    id: str
    title: str
    kind: Literal["character_consistency", "scene_style"] = "scene_style"
    asset_pack_type: Literal["character", "environment", "prop", "ui", "lighting", "transition"] = "environment"
    purpose: str = ""
    # A Pack exists only when it serves one or more script scenes. Storyboard
    # later replaces these stable scene links with concrete shot IDs.
    scene_ids: list[str] = Field(default_factory=list)
    reason_for_new_pack: str = ""
    # A manually created Pack is an exact user-authored generation request.
    # Its prompt must never be rewritten or augmented by Pack-type rules.
    user_authored: bool = False
    # Asset Packs lock reusable ingredients. Scene compositions assemble those
    # approved ingredients into a single storyboard-ready visual candidate.
    design_mode: Literal["asset", "scene"] = "asset"
    # Scene compositions normally inherit the production ratio, but may be
    # explicitly framed for a different deliverable.
    output_aspect_ratio: Literal["project", "16:9", "9:16"] = "project"
    handoff_key: str = ""
    source_mode: Literal["prompt_only", "brand_asset", "reference_frame"] = "prompt_only"
    source_notes: str = ""
    prompt: str = ""
    crop_plan: list[str] = Field(default_factory=list)
    asset_ids: list[str] = Field(default_factory=list)
    # New sheets use one controlled 2x2 asset sheet in grid_asset_id. The selected
    # quadrant is exported as selected_asset_id for later storyboard keyframes.
    # panel_asset_ids is retained only so older productions can still be opened.
    panel_asset_ids: list[str] = Field(default_factory=list)
    grid_asset_id: str | None = None
    selected_panel: int | None = Field(default=None, ge=0, le=3)
    selected_asset_id: str | None = None
    # Multiple locked states may be useful later: a Character Pack can retain
    # front/three-quarter/back views while a Transition Pack keeps both sides.
    approved_panel_asset_ids: dict[str, str] = Field(default_factory=dict)
    approved_asset_ids: list[str] = Field(default_factory=list)
    job_id: str | None = None
    status: Literal["draft", "generating", "ready", "failed", "approved"] = "draft"
    # A user-actionable explanation for a terminal generation failure. Kept on
    # the pack (rather than only the transient Job) so the Design board remains
    # diagnosable after a refresh or when reopening a production.
    failure_reason: str | None = None


class VideoProductionDesignBible(BaseModel):
    status: Literal["draft", "approved"] = "draft"
    visual_identity: list[str] = Field(default_factory=list)
    character_and_product_rules: list[str] = Field(default_factory=list)
    logo_and_copy_rules: list[str] = Field(default_factory=list)
    keyframe_rules: list[str] = Field(default_factory=list)
    continuity_rules: list[str] = Field(default_factory=list)
    missing_assets: list[str] = Field(default_factory=list)
    character_consistency_sheets: list[VideoProductionDesignSheet] = Field(default_factory=list)
    scene_style_sheets: list[VideoProductionDesignSheet] = Field(default_factory=list)
    # The canonical Design inventory. Legacy category arrays above remain so
    # saved productions can still be opened without a migration.
    asset_packs: list[VideoProductionDesignSheet] = Field(default_factory=list)
    lighting_and_color_cards: list[str] = Field(default_factory=list)
    motion_blueprints: list[str] = Field(default_factory=list)
    transition_rules: list[str] = Field(default_factory=list)
    keyframe_prompts: list[str] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utcnow_naive)


class VideoProductionShot(BaseModel):
    id: str
    order: int
    scene_id: str = ""
    title: str
    start_seconds: float = 0
    duration_seconds: float = 4
    # Veo supports fixed output lengths. Keep this separate from the scripted
    # timeline duration so a 5-second story beat can render as a 6-second
    # video without rewriting the approved Working Script.
    generation_duration_seconds: Literal[4, 6, 8] | None = None
    # Generate two alternatives by default. Video generation is probabilistic;
    # retaining alternatives is materially more useful than retrying blindly.
    generation_variants: Literal[1, 2] = 2
    # The generation mode is an explicit production decision, not something
    # inferred only at request time.  This lets the UI explain why an end
    # frame or a prior take is required before a costly render is submitted.
    generation_mode: Literal["image_to_video", "first_last_frame", "extend"] = "image_to_video"
    # Extend uses an already generated Take as the provider input. It is kept
    # separate from selected_video_asset_id so a user can compare/keep a cut
    # while continuing a different alternative.
    extend_source_video_asset_id: str | None = None
    purpose: str = ""
    visual: str = ""
    action: str = ""
    camera: str = ""
    dialogue_or_copy: str = ""
    veo_prompt: str = ""
    continuity: str = ""
    audio_cue: str = ""
    transition: str = "cut"
    asset_ids: list[str] = Field(default_factory=list)
    # Explicit links turn a storyboard card into a reproducible production
    # unit. They are independent cropped states, never the original grid.
    character_state_asset_id: str | None = None
    # Dialogue and reaction shots often need two separately locked identities.
    # Keep the primary state above for backwards compatibility and store any
    # additional performers here.
    additional_character_state_asset_ids: list[str] = Field(default_factory=list)
    environment_state_asset_id: str | None = None
    prop_ui_asset_ids: list[str] = Field(default_factory=list)
    lighting_rule: str = ""
    motion_blueprint: str = ""
    transition_in_asset_id: str | None = None
    transition_out_asset_id: str | None = None
    keyframe_asset_id: str | None = None
    # Optional end state for a shot. It is reviewable in Storyboard even when
    # the selected video provider only consumes the start frame today.
    end_keyframe_asset_id: str | None = None
    # A frame extracted from a usable earlier take and promoted to this
    # shot's start frame. It preserves the lineage needed to diagnose and
    # reproduce cross-shot continuity decisions.
    bridge_source_video_asset_id: str | None = None
    bridge_timestamp_seconds: float | None = Field(default=None, ge=0)
    # The Director inspects selected first/last scene images before Veo runs.
    # It can flag a pair that needs a bridging frame rather than encouraging a
    # model to hide an impossible move with a hard cut.
    first_last_frame_status: Literal["not_set", "ready", "needs_intermediate"] = "not_set"
    first_last_frame_note: str = ""
    # A structured, reviewable preflight.  The Director can be uncertain, but
    # it must never silently promise that two unrelated images will interpolate
    # cleanly.  `recommended_strategy` maps directly to a user-visible editing
    # choice instead of a free-form canvas edge.
    motion_feasibility: Literal["not_checked", "safe", "review", "blocked"] = "not_checked"
    recommended_transition_strategy: Literal["cut", "match_cut", "continuous", "bridge"] = "cut"
    motion_risk_reasons: list[str] = Field(default_factory=list)
    # Audio timing is a planning aid, not a claim that a video model will
    # lip-sync.  It lets the editor choose a plausible Take length before
    # generation and preserves the result for a later TTS/lip-sync tool.
    estimated_dialogue_seconds: float | None = Field(default=None, ge=0)
    estimated_audio_seconds: float | None = Field(default=None, ge=0)
    keyframe_job_id: str | None = None
    video_asset_ids: list[str] = Field(default_factory=list)
    # The user-owned take choice used by the Edit timeline. Regeneration keeps
    # prior takes available instead of silently replacing the cut.
    selected_video_asset_id: str | None = None
    # A storyboard frame may be intentionally excluded from a particular cut
    # without deleting its generated takes or losing its history.
    include_in_edit: bool = True
    # Non-destructive source trim offsets used by the Edit timeline. `None`
    # means use the natural end of the chosen take.
    trim_in_seconds: float = Field(default=0, ge=0)
    trim_out_seconds: float | None = Field(default=None, gt=0)
    video_job_id: str | None = None
    # Takes are immutable historical outputs. A source edit only marks them
    # stale; it never removes an expensive generation or the user's cut.
    source_signature: str = ""
    take_source_signature: str = ""
    take_outdated: bool = False
    status: Literal["draft", "approved", "generating", "ready", "failed"] = "draft"


class VideoProductionAudioCue(BaseModel):
    shot_id: str = ""
    start_seconds: float = 0
    end_seconds: float = 0
    purpose: str = ""
    music_direction: str = ""
    sfx: list[str] = Field(default_factory=list)


class VideoProductionAudioPlan(BaseModel):
    """A reviewable soundtrack brief generated before Lyria is invoked."""

    status: Literal["draft", "generating", "ready", "failed"] = "draft"
    music_prompt: str = ""
    bpm: int | None = None
    intensity: str = ""
    instrumental: bool = True
    cue_sheet: list[VideoProductionAudioCue] = Field(default_factory=list)
    music_asset_ids: list[str] = Field(default_factory=list)
    job_id: str | None = None
    updated_at: datetime = Field(default_factory=utcnow_naive)


class VideoProductionEditOverlay(BaseModel):
    """A deterministic post-generation layer; never ask Veo to draw it."""

    id: str = Field(default_factory=lambda: f"overlay_{uuid4().hex[:10]}")
    kind: Literal["logo", "store_badges", "subtitle", "image"] = "image"
    asset_id: str | None = None
    text: str = ""
    start_seconds: float = Field(default=0, ge=0)
    end_seconds: float | None = Field(default=None, gt=0)
    position: Literal["top_left", "top_right", "bottom_center", "center"] = "bottom_center"


class VideoProductionTakeReview(BaseModel):
    take_id: str
    shot_id: str
    score: int = Field(default=0, ge=0, le=100)
    verdict: Literal["use", "trim", "regenerate", "reject"] = "trim"
    reasons: list[str] = Field(default_factory=list)
    flags: list[Literal["unreadable_text", "brand_mismatch", "identity_drift", "hard_cut", "bad_motion", "audio_issue"]] = Field(default_factory=list)
    suggested_trim_in_seconds: float = Field(default=0, ge=0)
    suggested_trim_out_seconds: float | None = Field(default=None, gt=0)


class VideoProductionEditPlan(BaseModel):
    overlays: list[VideoProductionEditOverlay] = Field(default_factory=list)
    take_reviews: list[VideoProductionTakeReview] = Field(default_factory=list)
    review_status: Literal["draft", "reviewing", "ready", "failed"] = "draft"
    review_summary: str = ""
    reviewed_at: datetime | None = None
    # Render-time checks are deterministic guardrails.  They make the final
    # edit reviewable without pretending that a model judgement is a hard
    # export decision.
    qc_status: Literal["not_run", "pass", "warning"] = "not_run"
    qc_issues: list[str] = Field(default_factory=list)
    final_duration_seconds: float | None = None
    # Portable, user-editable representation of the non-destructive timeline.
    # UI controls remain the easy path; this is for precise or repeatable cuts.
    timeline_json: dict[str, object] = Field(default_factory=dict)


class VideoProductionConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    # Attachments belong to the turn as well as the project gallery, so the
    # Copilot can distinguish "these images" from all historical assets.
    asset_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow_naive)


class VideoProductionConfirmation(BaseModel):
    """A proposed high-impact Copilot action waiting for an explicit user yes."""

    id: str = Field(default_factory=lambda: f"confirm_{uuid4().hex[:10]}")
    question: str = ""
    reason: str = ""
    proposed_action: str = ""
    stage: str = "direction"
    choices: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow_naive)


class VideoProductionCanvasState(BaseModel):
    """Presentation-only state for the constrained production canvas.

    The actual production graph is always derived from Project State. Canvas
    coordinates and collapsed groups can be saved freely, but arbitrary graph
    edges are intentionally not stored here.
    """

    node_positions: dict[str, dict[str, float]] = Field(default_factory=dict)
    collapsed_groups: list[str] = Field(default_factory=list)
    selected_node_id: str | None = None


class VideoProductionRevision(BaseModel):
    revision: int
    label: str = ""
    summary: str = ""
    created_at: datetime = Field(default_factory=utcnow_naive)


class VideoProductionScriptRevision(BaseModel):
    """A bounded, readable checkpoint of a reviewed working script."""

    revision_id: str = Field(default_factory=lambda: f"vsr_{uuid4().hex}")
    revision: int = Field(ge=1)
    status: Literal["draft", "locked"]
    reason: str
    actor_user_id: str = "system"
    raw_script: str
    scene_count: int = Field(ge=0)
    beat_count: int = Field(ge=0)
    script: VideoProductionScript | None = None
    created_at: datetime = Field(default_factory=utcnow_naive)


class VideoProductionEvent(BaseModel):
    """A compact, durable activity record for one production revision.

    The event is deliberately a factual state-transition receipt, not an
    unbounded copy of prompts or model output. Detailed production state stays
    in the project record; this log lets an operator understand when a saved
    transition occurred after refresh or on another instance.
    """

    event_id: str
    production_id: str
    workspace_id: str
    event_type: str
    summary: str
    state_revision: int = Field(ge=1)
    actor_user_id: str = "system"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utcnow_naive)


class VideoProductionModelSelection(BaseModel):
    """One server-validated provider/model choice owned by a production."""

    provider: str = ""
    model: str = ""


class VideoProductionProviderSelection(BaseModel):
    """Project-scoped model choices for each independently billable operation."""

    text: VideoProductionModelSelection = Field(default_factory=VideoProductionModelSelection)
    image: VideoProductionModelSelection = Field(default_factory=VideoProductionModelSelection)
    video: VideoProductionModelSelection = Field(default_factory=VideoProductionModelSelection)
    audio: VideoProductionModelSelection = Field(default_factory=VideoProductionModelSelection)


class VideoProductionProviderOption(BaseModel):
    provider: str
    model: str
    label: str


class VideoProductionProviderCapabilities(BaseModel):
    text: list[VideoProductionProviderOption] = Field(default_factory=list)
    image: list[VideoProductionProviderOption] = Field(default_factory=list)
    video: list[VideoProductionProviderOption] = Field(default_factory=list)
    audio: list[VideoProductionProviderOption] = Field(default_factory=list)


class VideoProductionSetup(BaseModel):
    """User-confirmed market and creative constraints for one video."""

    target_market: str = ""
    target_audience: str = ""
    video_type: str = ""
    visual_style: str = ""
    spoken_language: str = ""
    subtitle_language: str = ""
    platform: str = ""
    conversion_goal: str = ""
    provider_selection: VideoProductionProviderSelection = Field(default_factory=VideoProductionProviderSelection)
    confirmed: bool = False


class VideoProduction(BaseModel):
    production_id: str
    workspace_id: str
    created_by: str
    title: str = "Untitled video"
    stage: VideoProductionStage = VideoProductionStage.direction
    brief: str = ""
    target_seconds: Literal[15, 30, 60] = 30
    aspect_ratio: Literal["16:9", "9:16"] = "16:9"
    resolution: Literal["720p", "1080p"] = "720p"
    # Revision and branch metadata make major upstream experiments safe. A
    # branch reuses existing assets but owns its own Project State thereafter.
    state_revision: int = 1
    parent_production_id: str | None = None
    branch_label: str = ""
    archived_at: datetime | None = None
    archived_by: str | None = None
    revisions: list[VideoProductionRevision] = Field(default_factory=list)
    script_revisions: list[VideoProductionScriptRevision] = Field(default_factory=list)
    canvas_state: VideoProductionCanvasState = Field(default_factory=VideoProductionCanvasState)
    pending_confirmation: VideoProductionConfirmation | None = None
    video_setup: VideoProductionSetup = Field(default_factory=VideoProductionSetup)
    reference_asset_ids: list[str] = Field(default_factory=list)
    asset_links: list[VideoProductionAssetLink] = Field(default_factory=list)
    # Contract-driven pipeline state. Dict storage keeps existing productions
    # readable while the typed contracts validate each agent handoff.
    production_contract: dict[str, Any] = Field(default_factory=dict)
    creative_contract: dict[str, Any] = Field(default_factory=dict)
    asset_contract: dict[str, Any] = Field(default_factory=dict)
    creative_direction: VideoProductionCreativeDirection = Field(default_factory=VideoProductionCreativeDirection)
    script: VideoProductionScript = Field(default_factory=VideoProductionScript)
    design_bible: VideoProductionDesignBible = Field(default_factory=VideoProductionDesignBible)
    shots: list[VideoProductionShot] = Field(default_factory=list)
    storyboard_approved_at: datetime | None = None
    storyboard_approved_revision: int | None = None
    edit_plan: VideoProductionEditPlan = Field(default_factory=VideoProductionEditPlan)
    audio_plan: VideoProductionAudioPlan = Field(default_factory=VideoProductionAudioPlan)
    conversation: list[VideoProductionConversationMessage] = Field(default_factory=list)
    final_asset_id: str | None = None
    render_job_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow_naive)
    updated_at: datetime = Field(default_factory=utcnow_naive)

    @field_validator("stage", mode="before")
    @classmethod
    def migrate_legacy_brief_stage(cls, value: object) -> object:
        # Existing saved productions used `brief` before Direction became explicit.
        return "direction" if value == "brief" else value


class VideoProductionCreateRequest(BaseModel):
    workspace_id: str
    title: str = "Untitled video"
    target_seconds: Literal[15, 30, 60] = 30
    aspect_ratio: Literal["16:9", "9:16"] = "16:9"
    resolution: Literal["720p", "1080p"] = "720p"
    brief: str = ""
    video_setup: VideoProductionSetup | None = None


class VideoProductionUpdateRequest(BaseModel):
    title: str | None = None
    stage: VideoProductionStage | None = None
    brief: str | None = None
    target_seconds: Literal[15, 30, 60] | None = None
    aspect_ratio: Literal["16:9", "9:16"] | None = None
    resolution: Literal["720p", "1080p"] | None = None
    video_setup: VideoProductionSetup | None = None
    reference_asset_ids: list[str] | None = None
    asset_links: list[VideoProductionAssetLink] | None = None
    creative_direction: VideoProductionCreativeDirection | None = None
    script: VideoProductionScript | None = None
    design_bible: VideoProductionDesignBible | None = None
    audio_plan: VideoProductionAudioPlan | None = None
    edit_plan: VideoProductionEditPlan | None = None
    canvas_state: VideoProductionCanvasState | None = None
    expected_revision: int | None = Field(default=None, ge=1)


class VideoProductionAgentRequest(BaseModel):
    message: str = ""
    shot_ids: list[str] = Field(default_factory=list)


class VideoProductionCopilotRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    asset_ids: list[str] = Field(default_factory=list, max_length=12)
    stage: VideoProductionStage | None = None
    confirm_action_id: str | None = None


class VideoProductionCopilotResponse(BaseModel):
    production: VideoProduction
    needs_confirmation: bool = False
    clarification_questions: list[str] = Field(default_factory=list)


class PromptReviewRequest(BaseModel):
    target_prompt: str = Field(min_length=1, max_length=100_000)
    target_name: str = "Target Prompt"


class PromptReviewResponse(BaseModel):
    target_name: str
    review: str
    model: str


class VideoProductionDesignSheetSelectionRequest(BaseModel):
    panel: int = Field(ge=0, le=3)


class VideoProductionDesignSheetCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    asset_pack_type: Literal["character", "environment", "prop", "ui", "lighting", "transition"] = "environment"
    purpose: str = ""
    prompt: str = ""
    source_asset_ids: list[str] = Field(default_factory=list)
    scene_ids: list[str] = Field(default_factory=list)
    design_mode: Literal["asset", "scene"] = "asset"
    output_aspect_ratio: Literal["project", "16:9", "9:16"] = "project"


class VideoProductionDesignSheetUpdateRequest(BaseModel):
    title: str | None = None
    asset_pack_type: Literal["character", "environment", "prop", "ui", "lighting", "transition"] | None = None
    purpose: str | None = None
    prompt: str | None = None
    source_asset_ids: list[str] | None = None
    scene_ids: list[str] | None = None
    design_mode: Literal["asset", "scene"] | None = None
    output_aspect_ratio: Literal["project", "16:9", "9:16"] | None = None


class VideoProductionSceneReframeRequest(BaseModel):
    """Extend an approved Scene image to a delivery aspect ratio without cropping it."""

    source_asset_id: str = Field(min_length=1)
    output_aspect_ratio: Literal["project", "16:9", "9:16"] = "project"


class VideoProductionShotUpdateRequest(BaseModel):
    scene_id: str | None = None
    title: str | None = None
    start_seconds: float | None = None
    duration_seconds: float | None = None
    generation_duration_seconds: Literal[4, 6, 8] | None = None
    generation_variants: Literal[1, 2] | None = None
    generation_mode: Literal["image_to_video", "first_last_frame", "extend"] | None = None
    extend_source_video_asset_id: str | None = None
    purpose: str | None = None
    visual: str | None = None
    action: str | None = None
    camera: str | None = None
    dialogue_or_copy: str | None = None
    veo_prompt: str | None = None
    continuity: str | None = None
    audio_cue: str | None = None
    transition: str | None = None
    asset_ids: list[str] | None = None
    character_state_asset_id: str | None = None
    additional_character_state_asset_ids: list[str] | None = None
    environment_state_asset_id: str | None = None
    prop_ui_asset_ids: list[str] | None = None
    lighting_rule: str | None = None
    motion_blueprint: str | None = None
    transition_in_asset_id: str | None = None
    transition_out_asset_id: str | None = None
    keyframe_asset_id: str | None = None
    end_keyframe_asset_id: str | None = None
    bridge_source_video_asset_id: str | None = None
    bridge_timestamp_seconds: float | None = Field(default=None, ge=0)
    first_last_frame_status: Literal["not_set", "ready", "needs_intermediate"] | None = None
    first_last_frame_note: str | None = None
    keyframe_job_id: str | None = None
    video_asset_ids: list[str] | None = None
    selected_video_asset_id: str | None = None
    include_in_edit: bool | None = None
    trim_in_seconds: float | None = Field(default=None, ge=0)
    trim_out_seconds: float | None = Field(default=None, gt=0)
    video_job_id: str | None = None
    status: Literal["draft", "approved", "generating", "ready", "failed"] | None = None


class VideoProductionShotCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    purpose: str = ""
    visual: str = ""
    action: str = ""
    duration_seconds: float = Field(default=3.0, gt=0, le=12)


class VideoProductionShotOrderRequest(BaseModel):
    shot_ids: list[str]


class VideoProductionShotRenderRequest(BaseModel):
    """Runs one controlled production step for a storyboard shot."""

    variants: Literal[1, 2] = 2


class VideoProductionBridgeFrameRequest(BaseModel):
    """Promote a usable frame from one Take into the next shot's start frame."""

    source_video_asset_id: str | None = None
    timestamp_seconds: float = Field(ge=0)
    target_shot_id: str | None = None


class VideoProductionRenderRequest(BaseModel):
    """Assembles the approved shot takes into the first delivery cut."""

    include_audio: bool = False


class ThreadMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    asset_ids: list[str] = Field(default_factory=list)
    job_id: str | None = None
    timestamp: datetime = Field(default_factory=utcnow_naive)


class CreativeThread(BaseModel):
    thread_id: str
    workspace_id: str
    title: str
    generation_mode: GenerationMode = GenerationMode.free_create
    created_by: str = ""
    origin_asset_id: str | None = None
    cover_asset_id: str | None = None
    latest_asset_id: str | None = None
    latest_job_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow_naive)
    updated_at: datetime = Field(default_factory=utcnow_naive)
    reference_asset_ids: list[str] = Field(default_factory=list)
    messages: list[ThreadMessage] = Field(default_factory=list)
    preview_url: str | None = None
    asset_count: int = 0
    job_count: int = 0


class User(BaseModel):
    id: str
    name: str
    email: str
    role: Role
    team: str


class ProviderConfig(BaseModel):
    default_image_provider: str
    openai_image_model: str
    vertex_imagen_model: str
    vertex_veo_fast_model: str | None
    vertex_veo_model: str | None
    vertex_ai_enabled: bool
    gcp_project_id: str | None
    gcp_location: str
    asset_bucket: str
    max_image_variants: int
    max_output_sizes: int


class VideoBudgetStatus(BaseModel):
    budget_usd: float
    pricing_enabled: bool
    current_estimated_spend_usd: float
    remaining_estimated_spend_usd: float
    request_estimated_cost_usd: float
    projected_total_usd: float
    would_exceed_budget: bool


class ToolDefinition(BaseModel):
    id: str
    name: str
    category: str
    status: ToolStatus
    provider: str
    owner: str
    description: str


class ToolStatusUpdate(BaseModel):
    status: ToolStatus


class Workspace(BaseModel):
    id: str
    title: str
    description: str
    owner_user_id: str
    team: str
    status: JobStatus
    updated_at: datetime


class Asset(BaseModel):
    id: str
    title: str
    type: Literal["image", "video", "audio", "gif", "report", "playable"]
    gcs_uri: str
    preview_url: str
    provider: str
    model: str
    workspace_id: str
    job_id: str
    prompt_hash: str
    created_by: str
    created_at: datetime
    width: int | None = None
    height: int | None = None
    theme: str | None = None
    asset_role: AssetRole = AssetRole.generated
    analysis: dict[str, Any] | None = None
    thread_id: str | None = None
    parent_asset_id: str | None = None
    root_asset_id: str | None = None


class GenerationRequest(BaseModel):
    workspace_id: str = Field(..., examples=["wsp_q2"])
    prompt: str
    provider: Literal["openai", "gemini"] = "gemini"
    model: str = "imagen-4.0-generate-001"
    variants: int = Field(default=1, ge=1, le=3)
    aspect_ratio: str = "1:1"
    created_by: str = "usr_jane"
    source_asset_ids: list[str] = Field(default_factory=list)
    theme: str = "World Cup"
    output_sizes: list[str] = Field(default_factory=lambda: ["300x250", "320x480", "1200x628"])
    output_format: Literal["image", "gif", "image_and_gif"] = "image"
    reference_asset_ids: list[str] = Field(default_factory=list)
    preserve_layout: bool = False
    use_reference_style: bool = True
    client_asset_ids: list[str] = Field(default_factory=list)
    session_id: str | None = None
    thread_id: str | None = None
    source_asset_id: str | None = None
    generation_mode: GenerationMode = GenerationMode.free_create
    include_gif: bool = False  # generate animated GIF for supported banner sizes
    resize_include_gacha_disclosure: bool = False
    resize_prompt_overrides: dict[str, str] = Field(default_factory=dict)
    resize_negative_prompt_override: str | None = None
    theme_create_mode: ThemeCreateMode | None = None
    theme_create_style_name: str | None = None
    theme_create_style_details: str | None = None
    theme_create_logo_position: str | None = None
    theme_create_element_position: str | None = None
    theme_create_old_text: str | None = None
    theme_create_new_text: str | None = None
    theme_create_font_style: str | None = None
    remediation_analysis: list[RemediationAnalysisResult] = Field(default_factory=list)
    # output_sizes length is validated in the endpoint against settings.max_output_sizes


class VideoGenerationBeat(BaseModel):
    """A time-boxed narrative unit for a generated commercial video."""

    id: str
    title: str
    purpose: str
    start_state: str = ""
    end_state: str = ""
    duration_seconds: int = Field(ge=1)
    veo_brief: str = ""


class VideoGenerationRequest(BaseModel):
    workspace_id: str = Field(..., examples=["wsp_q2"])
    prompt: str = ""
    provider: Literal["gemini"] = "gemini"
    model: str = ""
    created_by: str = "usr_jane"
    thread_id: str | None = None
    source_asset_id: str | None = None
    end_frame_asset_id: str | None = None
    reference_asset_ids: list[str] = Field(default_factory=list)
    video_generation_mode: VideoGenerationMode = VideoGenerationMode.image_to_video
    aspect_ratio: Literal["16:9", "9:16"] = "16:9"
    duration_seconds: Literal[4, 6, 8, 15, 30, 60] = 15
    resolution: Literal["720p", "1080p"] = "720p"
    variants: Literal[1, 2] = 1
    include_audio: bool = False
    camera_preset: str | None = None
    enhance_with_veo_fast: bool = False
    plan_id: str | None = None
    # Populated from the confirmed planning pass; clients do not need to send it.
    sequence_beats: list[VideoGenerationBeat] = Field(default_factory=list)


class VideoPlanConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    created_at: datetime = Field(default_factory=utcnow_naive)


class VideoGenerationPlan(BaseModel):
    plan_id: str
    workspace_id: str
    thread_id: str
    created_by: str
    mode: VideoGenerationMode
    source_asset_id: str
    reference_asset_ids: list[str] = Field(default_factory=list)
    status: Literal["draft", "confirmed", "generated"] = "draft"
    objective: str = ""
    summary: str = ""
    keep: list[str] = Field(default_factory=list)
    change: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    recommended_settings: dict[str, str] = Field(default_factory=dict)
    generation_prompt: str = ""
    beats: list[VideoGenerationBeat] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    interaction_concept: dict[str, Any] = Field(default_factory=dict)
    execution_intent: Literal["chat", "generate"] = "chat"
    conversation: list[VideoPlanConversationMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow_naive)
    updated_at: datetime = Field(default_factory=utcnow_naive)

    @field_validator("conversation", mode="before")
    @classmethod
    def migrate_legacy_conversation(cls, value: Any) -> list[dict[str, Any]]:
        """Read existing string-only plan history while storing new role-aware turns."""
        if not isinstance(value, list):
            return []
        normalized: list[dict[str, Any]] = []
        for entry in value:
            if isinstance(entry, str) and entry.strip():
                normalized.append({"role": "user", "text": entry.strip()})
            elif isinstance(entry, dict) and entry.get("text"):
                normalized.append(entry)
        return normalized


class VideoPlanRequest(BaseModel):
    workspace_id: str
    prompt: str = ""
    created_by: str = ""
    thread_id: str | None = None
    source_asset_id: str
    reference_asset_ids: list[str] = Field(default_factory=list)
    video_generation_mode: VideoGenerationMode
    action: Literal["analyze", "refine", "confirm"] = "analyze"
    plan_id: str | None = None
    generation_prompt_override: str | None = None
    aspect_ratio: Literal["16:9", "9:16"] = "16:9"
    duration_seconds: Literal[4, 6, 8, 15, 30, 60] = 15
    resolution: Literal["720p", "1080p"] = "720p"
    variants: Literal[1, 2] = 1
    include_audio: bool = False


class VideoPlanResponse(BaseModel):
    plan: VideoGenerationPlan
    report_asset_id: str | None = None


class RemediationViolation(BaseModel):
    category: str
    severity: str
    target: str
    reason: str
    fix_instruction: str


class RemediationAnalysisResult(BaseModel):
    asset_id: str
    asset_title: str
    overall_risk: str
    summary: str
    preserve_instructions: list[str] = Field(default_factory=list)
    violations: list[RemediationViolation] = Field(default_factory=list)
    remediation_prompt: str


class RemediationAnalysisRequest(BaseModel):
    workspace_id: str
    source_asset_ids: list[str] = Field(default_factory=list)
    prompt: str = ""
    created_by: str = "usr_jane"


class RemediationAnalysisResponse(BaseModel):
    results: list[RemediationAnalysisResult] = Field(default_factory=list)


class ThemeCreateStyleReport(BaseModel):
    report_id: str
    workspace_id: str
    title: str
    summary: str
    theme_create_mode: ThemeCreateMode
    prompt_template: str
    source_asset_id: str | None = None
    reference_asset_ids: list[str] = Field(default_factory=list)
    source_job_id: str | None = None
    recommended_preset_name: str | None = None
    visual_dna: list[str] = Field(default_factory=list)
    composition_rules: list[str] = Field(default_factory=list)
    do_not_copy: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    taxonomy: dict[str, list[str]] = Field(default_factory=dict)
    created_by: str
    created_at: datetime = Field(default_factory=utcnow_naive)
    updated_at: datetime = Field(default_factory=utcnow_naive)


class ThemeCreateStyleReportCreateRequest(BaseModel):
    workspace_id: str
    title: str
    summary: str
    theme_create_mode: ThemeCreateMode
    prompt_template: str
    source_asset_id: str | None = None
    reference_asset_ids: list[str] = Field(default_factory=list)
    source_job_id: str | None = None
    recommended_preset_name: str | None = None
    visual_dna: list[str] = Field(default_factory=list)
    composition_rules: list[str] = Field(default_factory=list)
    do_not_copy: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    taxonomy: dict[str, list[str]] = Field(default_factory=dict)
    created_by: str = "usr_jane"


class ThemeCreateStyleReportDraftRequest(BaseModel):
    workspace_id: str
    theme_create_mode: ThemeCreateMode
    prompt_template: str
    source_asset_id: str
    reference_asset_ids: list[str] = Field(default_factory=list)
    style_name: str | None = None
    style_details: str | None = None
    logo_position: str | None = None
    element_position: str | None = None
    old_text: str | None = None
    new_text: str | None = None
    font_style: str | None = None


class ThemeCreatePreset(BaseModel):
    preset_id: str
    name: str
    description: str
    theme_create_mode: ThemeCreateMode
    visibility: ThemeCreatePresetVisibility = ThemeCreatePresetVisibility.team
    prompt_template: str
    style_name: str | None = None
    style_details: str | None = None
    workspace_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    taxonomy: dict[str, list[str]] = Field(default_factory=dict)
    source_report_id: str | None = None
    source_job_id: str | None = None
    source_asset_id: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=utcnow_naive)
    updated_at: datetime = Field(default_factory=utcnow_naive)
    usage_count: int = 0
    is_official: bool = False


class ThemeCreatePresetCreateRequest(BaseModel):
    name: str
    description: str
    theme_create_mode: ThemeCreateMode
    visibility: ThemeCreatePresetVisibility = ThemeCreatePresetVisibility.team
    prompt_template: str
    style_name: str | None = None
    style_details: str | None = None
    workspace_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    taxonomy: dict[str, list[str]] = Field(default_factory=dict)
    source_report_id: str | None = None
    source_job_id: str | None = None
    source_asset_id: str | None = None
    created_by: str = "usr_jane"


class ThemeCreatePresetFromReportRequest(BaseModel):
    name: str
    description: str
    visibility: ThemeCreatePresetVisibility = ThemeCreatePresetVisibility.team
    style_name: str | None = None
    style_details: str | None = None


# ── Session / conversation models ─────────────────────────────────────────────

class SessionMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    asset_ids: list[str] = Field(default_factory=list)
    job_id: str | None = None
    timestamp: datetime = Field(default_factory=utcnow_naive)


class Session(BaseModel):
    session_id: str
    workspace_id: str
    reference_asset_ids: list[str] = Field(default_factory=list)
    messages: list[SessionMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow_naive)
    updated_at: datetime = Field(default_factory=utcnow_naive)


# ── Inpainting / image-edit ───────────────────────────────────────────────────

class ImageEditRequest(BaseModel):
    workspace_id: str
    asset_id: str                    # original image asset to edit (the "working image")
    extra_asset_ids: list[str] = Field(default_factory=list)  # logos / reference images
    mask_data: str | None = None     # base64-encoded PNG; transparent pixels = edit area
    prompt: str
    model: str = "gpt-image-2"
    variants: int = Field(default=1, ge=1, le=3)
    created_by: str = "usr_jane"
    theme: str | None = None
    session_id: str | None = None
    thread_id: str | None = None
    output_sizes: list[str] = Field(default_factory=list)


class KakaoCleanRequest(BaseModel):
    workspace_id: str
    asset_id: str
    created_by: str = "usr_jane"
    thread_id: str | None = None


class KakaoBizboardComposeRequest(BaseModel):
    workspace_id: str
    cleaned_asset_id: str
    composed_asset_id: str
    template: str = "APP_DOWNLOAD_ONE_LINE_COPY_THUMBNAIL"
    main_copy: str
    sub_copy: str = ""
    app_download_copy: str = ""
    additional_info: str = ""
    gacha: bool = False
    created_by: str = "usr_jane"
    thread_id: str | None = None


class GenerationJob(BaseModel):
    job_id: str
    workspace_id: str
    status: JobStatus
    progress: int
    lineage_key: str
    message: str
    tool_id: str = "openai-image-2"
    title: str = "Image generation"
    output_asset_ids: list[str] = Field(default_factory=list)
    thread_id: str | None = None
    source_asset_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow_naive)
    updated_at: datetime = Field(default_factory=utcnow_naive)


# ── Outpainting ───────────────────────────────────────────────────────────────

class OutpaintRequest(BaseModel):
    workspace_id: str
    asset_id: str
    direction: Literal["left", "right", "top", "bottom", "all"] = "all"
    ratio: float = Field(default=0.3, ge=0.1, le=0.8)
    prompt: str = ""
    model: str = "gpt-image-2"
    created_by: str = "usr_jane"
    session_id: str | None = None
    thread_id: str | None = None
    output_sizes: list[str] = Field(default_factory=list)
    # Optional exact canvas used by Scene Builder's reframe action. The source
    # pixels stay centered and untouched; only the new border is generated.
    target_size: str | None = None


# ── Background removal ────────────────────────────────────────────────────────

class RemoveBGRequest(BaseModel):
    workspace_id: str
    asset_id: str
    replacement_prompt: str = ""   # if empty → transparent BG; if set → replace with this
    model: str = "gpt-image-2"
    created_by: str = "usr_jane"
    session_id: str | None = None
    thread_id: str | None = None
    output_sizes: list[str] = Field(default_factory=list)


# ── Text overlay ──────────────────────────────────────────────────────────────

class AddTextRequest(BaseModel):
    workspace_id: str
    asset_id: str
    text: str
    position: Literal["top", "center", "bottom"] = "bottom"
    font_size_ratio: float = Field(default=0.06, ge=0.02, le=0.2)
    created_by: str = "usr_jane"
    session_id: str | None = None
    thread_id: str | None = None
    output_sizes: list[str] = Field(default_factory=list)


class GenerateGifRequest(BaseModel):
    workspace_id: str
    asset_id: str
    created_by: str = "usr_jane"
    thread_id: str | None = None


class RoleAssignment(BaseModel):
    user_id: str
    role: Role
    team: str


class UsageEvent(BaseModel):
    id: str
    job_id: str
    workspace_id: str
    user_id: str
    user_email: str
    provider: str
    model: str
    operation: str
    prompt_hash: str
    variants: int
    output_size_count: int
    output_format: str
    estimated_provider_generations: int
    output_asset_count: int
    estimated_cost_usd: float
    actual_cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    created_at: datetime = Field(default_factory=utcnow_naive)


# ── GamingPlayable templates ─────────────────────────────────────────────────

PlayableTemplateVisibility = Literal["private", "workspace", "community"]


class PlayableProjectSaveRequest(BaseModel):
    """Durable editable source for one playable project.

    The schema is intentionally stored as JSON rather than re-modelled on the
    API. The runtime owns the schema version and can evolve without making a
    historical creator project unreadable.
    """

    model_config = ConfigDict(populate_by_name=True)

    workspace_id: str = "wsp_q2"
    project_id: str | None = None
    title: str = Field(min_length=1, max_length=120)
    schema_payload: dict[str, Any] = Field(alias="schema", serialization_alias="schema")
    source_template_id: str | None = None


class PlayableProject(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_id: str
    workspace_id: str
    owner_user_id: str
    title: str
    schema_payload: dict[str, Any] = Field(alias="schema", serialization_alias="schema")
    source_template_id: str | None = None
    created_at: datetime
    updated_at: datetime


class PlayableTemplateCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workspace_id: str = "wsp_q2"
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=600)
    visibility: PlayableTemplateVisibility = "private"
    category: str = Field(default="merge", min_length=1, max_length=64)
    schema_payload: dict[str, Any] = Field(alias="schema", serialization_alias="schema")


class PlayableTemplate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    template_id: str
    workspace_id: str
    owner_user_id: str
    owner_name: str
    title: str
    description: str = ""
    visibility: PlayableTemplateVisibility
    category: str
    version: int
    schema_payload: dict[str, Any] = Field(alias="schema", serialization_alias="schema")
    asset_policy: Literal["slots_only"] = "slots_only"
    favorite_count: int = 0
    fork_count: int = 0
    is_favorited: bool = False
    created_at: datetime
    updated_at: datetime


class PlayableTemplateForkRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)


# ── GamingPlayable Copilot ───────────────────────────────────────────────────

PlayableCopilotModel = Literal["gemini-3.8-flash", "gemini-3.1-pro-preview"]
PlayableCopilotRole = Literal["user", "assistant"]


class PlayableCopilotMessage(BaseModel):
    id: str
    role: PlayableCopilotRole
    text: str = Field(max_length=6_000)
    asset_ids: list[str] = Field(default_factory=list)
    model: PlayableCopilotModel | None = None
    created_at: datetime


class PlayableCopilotSession(BaseModel):
    session_id: str
    workspace_id: str
    owner_user_id: str
    title: str
    messages: list[PlayableCopilotMessage] = Field(default_factory=list)
    proposal: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class PlayableCopilotMessageRequest(BaseModel):
    workspace_id: str = "wsp_q2"
    message: str = Field(min_length=1, max_length=12_000)
    asset_ids: list[str] = Field(default_factory=list, max_length=6)
    model: PlayableCopilotModel = "gemini-3.8-flash"


class PlayableCopilotProjectRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
