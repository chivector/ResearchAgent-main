from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import META_REVIEWER_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_meta_reviewer_agent(model, tools):
    """构建 MetaReviewerAgent。"""
    return CodeAgent(
        model=model,
        tools=tools,
        name="MetaReviewerAgent",
        description=("Input: draft + task_graph. Output: issue list via final_answer. "
                     "Focus on scientific-method checks."),
        max_steps=4,
        planning_interval=None,
        instructions=META_REVIEWER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
