from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import FORMAL_DERIVER_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_formal_deriver_agent(model):
    """构建 FormalDeriverAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="FormalDeriverAgent",
        description=(
            "Input: context_brief + task_graph + proof_plan. "
            "Output: DerivationBlocks list via final_answer."
        ),
        max_steps=8,
        planning_interval=2,
        instructions=FORMAL_DERIVER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS + ["numpy", "sympy"],
        code_block_tags="markdown",
    )
