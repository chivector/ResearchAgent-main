from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import VERIFICATION_PROMPT
from sciagent.tools.web_search_tool import WebSearchTool

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_verification_agent(model):
    """构建 VerificationAndSanityAgent with Stage 3 fact-checking."""
    return CodeAgent(
        model=model,
        tools=[WebSearchTool()],
        name="VerificationAndSanityAgent",
        description=("Input: context_brief + draft (+ optional task_graph/task_outputs). "
                     "Output: VerificationReport dict via final_answer."),
        max_steps=8,
        planning_interval=None,
        instructions=VERIFICATION_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS + ["numpy", "sympy"],
        code_block_tags="markdown",
    )
