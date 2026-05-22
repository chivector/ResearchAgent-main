from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import (
    WETLAB_DESIGNER_PROMPT,
    INSILICO_DESIGNER_PROMPT,
    DATA_ANALYSIS_DESIGNER_PROMPT,
)

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_wetlab_designer_agent(model):
    """构建 WetLabDesignerAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="WetLabDesignerAgent",
        description=("Input: context_brief + task + hypotheses. "
                     "Output: MethodPlan dict via final_answer."),
        max_steps=6,
        planning_interval=None,
        instructions=WETLAB_DESIGNER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )


def build_insilico_designer_agent(model):
    """构建 InSilicoDesignerAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="InSilicoDesignerAgent",
        description=("Input: context_brief + task + hypotheses. "
                     "Output: MethodPlan dict via final_answer."),
        max_steps=6,
        planning_interval=None,
        instructions=INSILICO_DESIGNER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS + ["numpy", "sympy"],
        code_block_tags="markdown",
    )


def build_data_analysis_designer_agent(model):
    """构建 DataAnalysisDesignerAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="DataAnalysisDesignerAgent",
        description=("Input: context_brief + task + hypotheses. "
                     "Output: MethodPlan dict via final_answer."),
        max_steps=6,
        planning_interval=None,
        instructions=DATA_ANALYSIS_DESIGNER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
