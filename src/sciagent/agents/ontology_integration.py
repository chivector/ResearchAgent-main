"""
Ontological Expansion Layer Integration Example

This module demonstrates how to integrate the OntologicalExpander
before TaskGraphBuilder to capture hidden scoring points.
"""

from sciagent.agents.ontological_expander import build_ontological_expander_agent
from sciagent.agents.task_graph_builder import build_task_graph_builder_agent


def expand_and_build_tasks(model, problem_text: str, context_brief: dict) -> dict:
    """
    Two-stage pipeline: Ontological Expansion → Task Graph Building

    Args:
        model: LLM model instance
        problem_text: Original problem statement
        context_brief: Output from ContextMiner

    Returns:
        Enhanced task graph with prerequisite steps injected
    """
    # Stage 1: Expand implicit prerequisites
    expander = build_ontological_expander_agent(model)
    expansion_result = expander.run(
        f"Problem: {problem_text}\n\nContext: {context_brief}"
    )

    # Stage 2: Build task graph with expanded prerequisites
    builder = build_task_graph_builder_agent(model)
    task_graph = builder.run(
        f"Problem: {problem_text}\n\n"
        f"Context: {context_brief}\n\n"
        f"Mandatory Prerequisites: {expansion_result}"
    )

    return {
        "ontological_expansion": expansion_result,
        "task_graph": task_graph
    }
