"""脚本处理 Agents（兼容聚合模块）。

该模块历史上承载所有 Agent 实现；当前实现已拆分到各自独立文件中。
此文件保留原 import 路径，便于旧代码/路由/测试继续工作。
"""

from __future__ import annotations

from app.ai_video.chains.agents.consistency_checker_agent import ConsistencyCheckerAgent
from app.ai_video.chains.agents.element_extractor_agent import ElementExtractorAgent
from app.ai_video.chains.agents.entity_merger_agent import EntityMergerAgent
from app.ai_video.chains.agents.script_divider_agent import ScriptDividerAgent
from app.ai_video.chains.agents.script_optimizer_agent import ScriptOptimizerAgent
from app.ai_video.chains.agents.script_simplifier_agent import ScriptSimplifierAgent
from app.ai_video.chains.agents.variant_analyzer_agent import VariantAnalyzerAgent

from app.ai_video.schemas.skills.script_processing import (
    EntityMergeResult,
    ScriptConsistencyCheckResult,
    ScriptDivisionResult,
    ScriptOptimizationResult,
    ScriptSimplificationResult,
    ShotDivision,
    StudioScriptExtractionDraft,
    VariantAnalysisResult,
)

__all__ = [
    "ScriptDividerAgent",
    "ElementExtractorAgent",
    "EntityMergerAgent",
    "VariantAnalyzerAgent",
    "ConsistencyCheckerAgent",
    "ScriptOptimizerAgent",
    "ScriptSimplifierAgent",
    # schema re-export
    "ScriptConsistencyCheckResult",
    "ScriptDivisionResult",
    "ScriptSimplificationResult",
    "ScriptOptimizationResult",
    "StudioScriptExtractionDraft",
    "EntityMergeResult",
    "VariantAnalysisResult",
    "ShotDivision",
]
