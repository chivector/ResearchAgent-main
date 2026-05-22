from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import CONTEXT_MINER_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_context_miner_agent(model):
    """构建 ContextMinerAgent (no web search - delegates to GroundTruthSearcher)."""
    return CodeAgent(
        model=model,
        tools=[],
        name="ContextMinerAgent",
        description=("Input: problem_text. Output: ContextBrief dict via final_answer. "
                     "Extract terms, constraints, deliverables."),
        max_steps=5,
        planning_interval=None,
        instructions=CONTEXT_MINER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
