from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import ONTOLOGICAL_EXPANSION_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_ontological_expander_agent(model):
    """构建 OntologicalExpanderAgent - 展开隐含的物理推导步骤。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="OntologicalExpanderAgent",
        description=(
            "Input: problem_text + context_brief. "
            "Output: OntologicalExpansion dict with mandatory prerequisite steps."
        ),
        max_steps=6,
        planning_interval=None,
        instructions=ONTOLOGICAL_EXPANSION_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
