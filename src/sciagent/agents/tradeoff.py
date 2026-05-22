from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import TRADEOFF_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_tradeoff_agent(model):
    """构建 TradeoffAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="TradeoffAgent",
        description=("Input: context_brief + task_graph + methods + hypotheses. "
                     "Output: DecisionRecord dict via final_answer."),
        max_steps=5,
        planning_interval=None,
        instructions=TRADEOFF_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
