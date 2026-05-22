from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import PROOF_PLANNER_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_proof_planner_agent(model):
    """构建 ProofPlannerAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="ProofPlannerAgent",
        description=(
            "Input: problem_text + context_brief + task_graph + derivation_intent. "
            "Output: ProofPlan dict via final_answer."
        ),
        max_steps=7,
        planning_interval=2,
        instructions=PROOF_PLANNER_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
