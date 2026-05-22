from __future__ import annotations

from smolagents import CodeAgent

from sciagent.prompts import PROOF_AUDITOR_PROMPT

COMMON_IMPORTS = ["typing", "json", "re", "math"]


def build_proof_auditor_agent(model):
    """构建 ProofAuditorAgent。"""
    return CodeAgent(
        model=model,
        tools=[],
        name="ProofAuditorAgent",
        description=("Input: proof_plan + derivation_blocks + draft. "
                     "Output: ProofGapReport dict via final_answer."),
        max_steps=6,
        planning_interval=None,
        instructions=PROOF_AUDITOR_PROMPT,
        additional_authorized_imports=COMMON_IMPORTS,
        code_block_tags="markdown",
    )
