from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import PROMPT_PROXIMITY_SELECTOR_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_prompt_proximity_selector_agent(model):
    """构建 PromptProximitySelector Agent。

    选择"最贴题、最少外推"的解释，而非"最专业、最复杂"的解释。
    这是无 rubric 场景下重要的一步。
    """
    return CodeAgent(
        model=model,
        tools=[],
        name="PromptProximitySelector",
        description=("Input: subquestion + extracted evidence + candidate hypotheses. "
                     "Output: RationalSelection dict via final_answer. "
                     "Selects the explanation closest to prompt logic, not the most sophisticated one."),
        max_steps=7,
        planning_interval=None,
        instructions=PROMPT_PROXIMITY_SELECTOR_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
