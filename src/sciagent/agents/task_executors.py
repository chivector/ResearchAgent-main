from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import (
    MECHANISM_INFERER_PROMPT,
    PATHWAY_MAPPING_PROMPT,
    COMPARISON_MATRIX_PROMPT,
    CRITIQUE_AGENT_PROMPT,
    ESTIMATOR_AGENT_PROMPT,
    SYNTHESIZER_AGENT_PROMPT,
)
from sciagent.tools.web_search_tool import WebSearchTool

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_mechanism_inferer_agent(model):
    """构建 MechanismInfererAgent - NO web search, receives ground truth from GroundTruthSearcher."""
    return CodeAgent(
        model=model,
        tools=[],
        name="MechanismInfererAgent",
        description=("Input: context_brief + ground_truth_facts + task_definition + hypotheses. "
                     "Output: MechanismModel dict via final_answer."),
        max_steps=10,
        planning_interval=None,
        instructions=MECHANISM_INFERER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS + ["numpy", "sympy"],
        code_block_tags="markdown",
    )


def build_critique_agent(model):
    """构建 CritiqueAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="CritiqueAgent",
        description=("Input: context_brief + task_definition + hypotheses + dependent_task_outputs. "
                     "Output: CritiqueReport dict via final_answer."),
        max_steps=6,
        planning_interval=None,
        instructions=CRITIQUE_AGENT_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )


def build_estimator_agent(model):
    """构建 EstimatorAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="EstimatorAgent",
        description=("Input: context_brief + task_definition + hypotheses + dependent_task_outputs. "
                     "Output: ParameterEstimate dict via final_answer."),
        max_steps=7,
        planning_interval=None,
        instructions=ESTIMATOR_AGENT_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS + ["numpy", "sympy"],
        code_block_tags="markdown",
    )


def build_synthesizer_agent(model):
    """构建 SynthesizerAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="SynthesizerAgent",
        description=("Input: context_brief + task_definition + all_prior_task_outputs. "
                     "Output: SynthesisReport dict via final_answer."),
        max_steps=6,
        planning_interval=None,
        instructions=SYNTHESIZER_AGENT_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )


def build_pathway_mapping_agent(model):
    """构建 PathwayMappingAgent（生物：通路拓扑/上下游推理）。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="PathwayMappingAgent",
        description=("Input: context_brief + task_definition + hypotheses + dependent_task_outputs. "
                     "Output: PathwayMap dict via final_answer."),
        max_steps=7,
        planning_interval=None,
        instructions=PATHWAY_MAPPING_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS + ["numpy", "sympy"],
        code_block_tags="markdown",
    )


def build_comparison_matrix_agent(model):
    """构建 ComparisonMatrixAgent（试题：对比分析矩阵）。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="ComparisonMatrixAgent",
        description=("Input: context_brief + task_definition + hypotheses + dependent_task_outputs. "
                     "Output: ComparisonMatrix dict via final_answer."),
        max_steps=6,
        planning_interval=None,
        instructions=COMPARISON_MATRIX_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
