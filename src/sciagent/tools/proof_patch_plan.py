from __future__ import annotations

from smolagents import tool


@tool
def proof_patch_plan_tool(proof_gap_report: dict, generality_report: dict | None = None) -> dict:
    """
    Build a patch plan to fix proof gaps and generality issues.

    Args:
        proof_gap_report: ProofGapReport JSON.
        generality_report: GeneralityReport JSON (optional).

    Returns:
        PatchPlan JSON with actions and notes.
    """
    actions = []
    notes = []

    for step_id in proof_gap_report.get("missing_steps", []):
        actions.append(f"Add derivation step: {step_id}")
    for eq in proof_gap_report.get("missing_eqs", []):
        actions.append(f"Include key equation: {eq}")
    for definition in proof_gap_report.get("missing_definitions", []):
        actions.append(f"Define missing symbol: {definition}")
    for issue in proof_gap_report.get("generality_issues", []):
        actions.append(f"Fix generality issue: {issue}")

    if generality_report:
        for issue in generality_report.get("issues", []):
            actions.append(f"Add general-derivation section: {issue}")

    if not actions:
        notes.append("No proof patch required.")
    return {"actions": actions, "notes": notes}
