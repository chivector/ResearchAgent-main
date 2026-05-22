from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import AXIOM_BUILDER_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_axiom_builder_agent(model):
    """构建 AxiomBuilderAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="AxiomBuilderAgent",
        description=("Input: problem_text + context_brief + domain_route. "
                     "Output: AxiomLedger dict via final_answer."),
        max_steps=7,
        planning_interval=None,
        instructions=AXIOM_BUILDER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
