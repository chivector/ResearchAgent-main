from __future__ import annotations

import re
from typing import List

from smolagents import tool


_DEF_PATTERNS = {
    "A_w": re.compile(r"A_w\s*=", re.IGNORECASE),
    "P_s": re.compile(r"P_s\s*=", re.IGNORECASE),
    "Psi_i": re.compile(r"\\Psi_i|\|\s*\\Psi_i", re.IGNORECASE),
    "Psi_f": re.compile(r"\\Psi_f|\|\s*\\Psi_f", re.IGNORECASE),
}


@tool
def proof_contract_check_tool(draft: str, proof_plan: dict) -> dict:
    """
    Check whether proof skeleton artifacts appear in the draft.

    Args:
        draft: Draft text.
        proof_plan: ProofPlan JSON.

    Returns:
        ProofGapReport JSON.
    """
    lowered = draft.lower()
    missing_steps: List[str] = []
    missing_eqs: List[str] = []
    missing_definitions: List[str] = []

    for step in proof_plan.get("steps", []):
        step_id = step.get("id", "")
        expected_eqs = step.get("expected_eqs", []) or []
        found_any = False
        for eq in expected_eqs:
            if eq and eq in draft:
                found_any = True
            elif eq:
                missing_eqs.append(eq)
        if expected_eqs and not found_any:
            if step_id:
                missing_steps.append(step_id)
            else:
                missing_steps.append(step.get("title", "unknown_step"))

    if "A_w" in draft and not _DEF_PATTERNS["A_w"].search(draft):
        missing_definitions.append("A_w definition")
    if "P_s" in draft and not _DEF_PATTERNS["P_s"].search(draft):
        missing_definitions.append("P_s definition")
    if _DEF_PATTERNS["Psi_i"].search(draft) and "pre-selected" not in lowered:
        missing_definitions.append("pre-selected state definition")
    if _DEF_PATTERNS["Psi_f"].search(draft) and "post-selected" not in lowered:
        missing_definitions.append("post-selected state definition")

    return {
        "missing_steps": sorted(set(missing_steps)),
        "missing_eqs": sorted(set(missing_eqs)),
        "missing_definitions": sorted(set(missing_definitions)),
        "generality_issues": [],
        "notes": [],
    }
