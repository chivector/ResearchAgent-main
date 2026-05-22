from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import PATCHER_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_patcher_agent(model):
    """构建 PatcherAgent，用于执行增量修补操作。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="PatcherAgent",
        description=(
            "Input: current draft text + patch_plan with structured patch_actions. "
            "Output: patched draft text with minimal changes."
        ),
        max_steps=6,
        planning_interval=None,
        instructions=PATCHER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
