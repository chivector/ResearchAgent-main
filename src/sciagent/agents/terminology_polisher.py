from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import TERMINOLOGY_POLISHER_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_terminology_polisher_agent(model):
    """构建 TerminologyPolisherAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="TerminologyPolisherAgent",
        description="Input: draft text. Output: polished text via final_answer.",
        max_steps=4,
        planning_interval=None,
        instructions=TERMINOLOGY_POLISHER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
