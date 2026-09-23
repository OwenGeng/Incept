"""Load independently editable system prompts for the AI-video production agents."""
from pathlib import Path


_PROMPT_ROOT = Path(__file__).with_name("prompts")


def _prompt(name: str) -> str:
    return (_PROMPT_ROOT / name).read_text(encoding="utf-8").strip()


CREATIVE_STRATEGIST_PROMPT = _prompt("creative_strategist.md")
REFERENCE_VIDEO_ANALYST_PROMPT = _prompt("reference_video_analyst.md")
PROMPT_REVIEWER_PROMPT = _prompt("prompt_reviewer.md")
SENIOR_SCREENWRITER_PROMPT = _prompt("senior_screenwriter.md")
PRODUCTION_DESIGNER_PROMPT = _prompt("production_designer.md")
STORYBOARD_DIRECTOR_PROMPT = _prompt("storyboard_director.md")
EDIT_REVIEWER_PROMPT = _prompt("edit_reviewer.md")
PRODUCTION_COPILOT_PROMPT = _prompt("production_copilot.md")
STORYBOARD_GENERATE_PROMPT = _prompt("storyboard_generate.md")
SCRIPT_GENERATE_PROMPT = _prompt("script_generate.md")
IMAGE_ASSET_GENERATE_PROMPT = _prompt("image_asset_generate.md")

# Named internal skills are loaded by the Copilot Router. They are deliberately
# separate from its system prompt so a focused generation task does not bloat
# every normal conversation turn.
PRODUCTION_COPILOT_SKILLS = {
    "storyboard generate": STORYBOARD_GENERATE_PROMPT,
    "script-generate": SCRIPT_GENERATE_PROMPT,
    "image-asset-generate": IMAGE_ASSET_GENERATE_PROMPT,
}
