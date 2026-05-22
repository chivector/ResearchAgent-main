from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import RESEARCH_DIRECTOR_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_director_agent(model):
    """构建 ResearchDirectorAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="ResearchDirectorAgent",
        description=("Input: problem_text + context_brief + task_graph + domain_route. "
                     "Output: DirectorDecision dict via final_answer. "
                     "Decide roles, routing, and synthesis strategy."),
        max_steps=6,
        planning_interval=None,
        instructions=RESEARCH_DIRECTOR_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
