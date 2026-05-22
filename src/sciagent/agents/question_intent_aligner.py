from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import QUESTION_INTENT_ALIGNER_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_question_intent_aligner_agent(model):
    """构建 QuestionIntentAlignerAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="QuestionIntentAlignerAgent",
        description=("Input: problem_text + context_brief. "
                     "Output: QuestionIntent dict via final_answer."),
        max_steps=7,
        planning_interval=None,
        instructions=QUESTION_INTENT_ALIGNER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
