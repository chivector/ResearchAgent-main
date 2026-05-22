from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import HYPOTHESIS_MODELER_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_hypothesis_modeler_agent(model):
    """构建 HypothesisModelerAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="HypothesisModelerAgent",
        description=("Input: context_brief + task_graph. "
                     "Output: HypothesisPack dict via final_answer."),
        max_steps=7,
        planning_interval=None,
        instructions=HYPOTHESIS_MODELER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS + ["numpy", "sympy"],
        code_block_tags="markdown",
    )
