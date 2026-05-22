from __future__ import annotations

from typing import Dict, List

from smolagents import tool

KEYWORD_TO_PROOF_TYPE = {
    "derive": "general_derivation",
    "derivation": "general_derivation",
    "prove": "proof",
    "show": "proof",
    "maximize": "optimization",
    "maximize over": "optimization",
    "general expression": "general_state_param",
    "general formula": "general_state_param",
    "arbitrary": "general_state_param",
    "for any": "general_state_param",
    "for each outcome": "projection_decomposition",
    "each outcome": "projection_decomposition",
    "orthogonal projection": "projection_decomposition",
    "postselection": "projection_decomposition",
    "fisher": "fisher_info",
    "qfi": "fisher_info",
    "quantum fisher": "fisher_info",
}

TASK_TYPE_TO_PROOF_TYPE = {
    "derive": "general_derivation",
    # "estimate": "optimization",
    # "compare": "optimization",
    # "sanity_check": "projection_decomposition",
}


@tool
def derivation_intent_tool(problem_text: str, task_graph: dict) -> dict:
    """
    Determine whether the task is proof-heavy and list required proof types.

    Args:
        problem_text: Original problem text.
        task_graph: ResearchTaskGraph JSON.

    Returns:
        DerivationIntent JSON.
    """
    lowered = problem_text.lower()
    triggers: List[str] = []
    required: List[str] = []

    for keyword, proof_type in KEYWORD_TO_PROOF_TYPE.items():
        if keyword in lowered:
            triggers.append(keyword)
            required.append(proof_type)

    for task in task_graph.get("tasks", []):
        task_type = str(task.get("task_type", "")).lower()
        if task_type in TASK_TYPE_TO_PROOF_TYPE:
            triggers.append(f"task_type:{task_type}")
            required.append(TASK_TYPE_TO_PROOF_TYPE[task_type])

    required = sorted(set(required))
    proof_heavy = bool(required)
    must_have_artifacts = []
    if proof_heavy:
        must_have_artifacts = [
            "general_formula",
            "intermediate_steps",
            "key_lemmas",
            "final_simplified_result",
        ]
        if "fisher_info" in required or "projection_decomposition" in required:
            must_have_artifacts.append("outcome_decomposition")

    return {
        "proof_heavy": proof_heavy,  # 是否是证明密集型任务
        "required_proof_types": required,  # 所需的证明类型列表
        "must_have_artifacts": must_have_artifacts,  # 必须包含的工件列表
        "triggers": triggers,  # 触发这些判断的关键词列表
    }
