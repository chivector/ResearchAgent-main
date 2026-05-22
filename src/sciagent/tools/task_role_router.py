from __future__ import annotations

from smolagents import tool

ROLE_MAP = {
    # Backward-compatible / legacy
    "interpret_context": ["ContextMinerAgent"],
    "retrieval_task": ["ContextMinerAgent"],
    "mechanism": ["MechanismInfererAgent", "VerificationAndSanityAgent"],
    "critique": ["CritiqueAgent", "MetaReviewerAgent"],
    "compare": ["ComparisonMatrixAgent", "MetaReviewerAgent"],
    "estimate": ["EstimatorAgent", "VerificationAndSanityAgent"],
    "downstream": ["ScientificWriterAgent"],
    # Current task types
    "derive": ["FormalDeriverAgent", "VerificationAndSanityAgent"],
    "mechanism_inference": ["MechanismInfererAgent"],
    "pathway_mapping": ["PathwayMappingAgent"],
    "comparison_table": ["ComparisonMatrixAgent"],
    "design_wetlab": ["WetLabDesigner"],
    "design_insilico": ["InSilicoDesigner"],
    "design_data_analysis": ["DataAnalysisDesigner"],
    "critique_and_tradeoff": ["CritiqueAgent", "MetaReviewerAgent"],
    "parameter_estimation": ["EstimatorAgent", "VerificationAndSanityAgent"],
    "sanity_check": ["VerificationAndSanityAgent"],
    "synthesis": ["SynthesizerAgent", "ScientificWriterAgent"],
}


@tool
def task_role_router_tool(task_graph: dict) -> dict:
    """
    Route tasks to role labels based on task_type.

    Args:
        task_graph: ResearchTaskGraph JSON.

    Returns:
        Updated ResearchTaskGraph JSON with roles assigned.
    """
    tasks = []
    for task in task_graph.get("tasks", []):
        task_type = task.get("task_type", "interpret_context")
        roles = ROLE_MAP.get(task_type, ["ContextMiner"])
        updated = dict(task)
        updated["roles"] = roles
        tasks.append(updated)
    return {"tasks": tasks, "notes": task_graph.get("notes", [])}
