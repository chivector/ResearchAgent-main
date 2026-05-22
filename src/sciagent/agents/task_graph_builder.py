from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import TASK_GRAPH_BUILDER_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_task_graph_builder_agent(model):
    """构建 TaskGraphBuilderAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="TaskGraphBuilderAgent",
        description=("Input: problem_text + context_brief. "
                     "Output: ResearchTaskGraph dict via final_answer."),
        max_steps=6,
        planning_interval=2,
        instructions=TASK_GRAPH_BUILDER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
