"""Skill 加载与 Agent 运行：通用基类与提取类/提示词类 agent。"""

from app.ai_video.chains.agents.base import AgentBase, STRUCTURED_OUTPUT_METHOD
from app.ai_video.chains.agents.shot_frame_prompt_agents import (
    ShotFirstFramePromptAgent,
    ShotLastFramePromptAgent,
    ShotKeyFramePromptAgent,
)
from app.ai_video.chains.agents.script_divider_agent import ScriptDividerAgent
from app.ai_video.chains.agents.element_extractor_agent import ElementExtractorAgent
from app.ai_video.chains.agents.entity_merger_agent import EntityMergerAgent
from app.ai_video.chains.agents.variant_analyzer_agent import VariantAnalyzerAgent
from app.ai_video.chains.agents.consistency_checker_agent import ConsistencyCheckerAgent
from app.ai_video.chains.agents.script_optimizer_agent import ScriptOptimizerAgent
from app.ai_video.chains.agents.script_simplifier_agent import ScriptSimplifierAgent
from app.ai_video.chains.agents.character_portrait_analysis_agent import CharacterPortraitAnalysisAgent
from app.ai_video.chains.agents.prop_info_analysis_agent import PropInfoAnalysisAgent
from app.ai_video.chains.agents.scene_info_analysis_agent import SceneInfoAnalysisAgent
from app.ai_video.chains.agents.costume_info_analysis_agent import CostumeInfoAnalysisAgent

__all__ = [
    "AgentBase",
    "STRUCTURED_OUTPUT_METHOD",
    "ShotFirstFramePromptAgent",
    "ShotLastFramePromptAgent",
    "ShotKeyFramePromptAgent",
    "ScriptDividerAgent",
    "ElementExtractorAgent",
    "EntityMergerAgent",
    "VariantAnalyzerAgent",
    "ConsistencyCheckerAgent",
    "ScriptOptimizerAgent",
    "ScriptSimplifierAgent",
    "CharacterPortraitAnalysisAgent",
    "PropInfoAnalysisAgent",
    "SceneInfoAnalysisAgent",
    "CostumeInfoAnalysisAgent",
]
