from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import SCIENTIFIC_WRITER_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_scientific_writer_agent(model):
    """构建 ScientificWriterAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="ScientificWriterAgent",
        description=(
            "Input: research_dossier dict. Output: draft text only. "
            "Ensure all tasks map to sections."
        ),
        max_steps=6,
        planning_interval=2,
        instructions=SCIENTIFIC_WRITER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
