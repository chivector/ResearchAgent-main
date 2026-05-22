"""
Task Execution Payload Builder - Dual-Track Aware

This module provides domain-aware payload construction for task execution.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sciagent.memory_graph import MemoryGraph, build_memory_graph_from_dossier
from sciagent.payload_compiler import PayloadView, compile_payload_view, render_payload_view as _render_payload_view


def compile_agent_payload(
    dossier: Any,
    agent_role: str,
    task: Optional[Dict[str, Any]] = None,
    runtime_inputs: Optional[Dict[str, Any]] = None,
    graph: Optional[MemoryGraph] = None,
    max_repair_rounds: int = 3,
    budget_tokens: Optional[int] = None,
) -> PayloadView:
    """Compile a role/task-specific PayloadView from the typed memory graph."""
    memory_graph = graph or build_memory_graph_from_dossier(dossier)
    return compile_payload_view(
        memory_graph,
        role=agent_role,
        task=task,
        runtime_inputs=runtime_inputs,
        max_repair_rounds=max_repair_rounds,
        budget_tokens=budget_tokens,
    )


def render_payload_view(payload_view: PayloadView) -> str:
    """Render a PayloadView into the text form consumed by smolagents."""
    return _render_payload_view(payload_view)

def build_task_payload(
    problem_text: str,
    dossier,
    task: dict,
    dependent_outputs: dict,
    is_deductive_track: bool
) -> str:
    """
    Build task execution payload based on epistemic track.

    Args:
        problem_text: Original problem statement
        dossier: ResearchDossier with all context
        task: Current task definition
        dependent_outputs: Outputs from dependency tasks
        is_deductive_track: True for physics/math, False for biology/chemistry

    Returns:
        Formatted payload string for agent execution
    """
    import json

    # Base payload (always included)
    base = (
        f"problem_text: {problem_text}\n"
        f"context_brief: {json.dumps(dossier.context, ensure_ascii=False)}\n"
        f"domain_route: {json.dumps(dossier.domain_route, ensure_ascii=False)}\n"
        f"subject_profile: {json.dumps(dossier.subject_profile, ensure_ascii=False)}\n"
        f"task_definition: {json.dumps(task, ensure_ascii=False)}\n"
    )

    # Micro-checklists (always included if present)
    checklist = ""
    if task.get("micro_checklists"):
        checklist = f"MANDATORY_CHECKLIST: {json.dumps(task.get('micro_checklists'), ensure_ascii=False)}\n"

    # Constraint ledger (mandatory constraint validation network)
    constraint_info = ""
    if dossier.constraint_ledger:
        ledger = dossier.constraint_ledger if isinstance(dossier.constraint_ledger, dict) else {}
        pending = [c for c in ledger.get("constraints", []) if c.get("status") == "pending"]
        if pending:
            constraint_info = f"CONSTRAINT_LEDGER (MANDATORY - your output MUST address these):\n{json.dumps(pending, ensure_ascii=False)}\n"

    # Track-specific payload
    if is_deductive_track:
        # Deductive track: inject axioms and derivations
        track_specific = ""
        if dossier.axiom_ledger:
            track_specific += (
                f"AXIOM_LEDGER (IMMUTABLE CONSTRAINTS): "
                f"{json.dumps(dossier.axiom_ledger, ensure_ascii=False)}\n"
            )
        if dossier.derivations:
            track_specific += f"global_derivations: {json.dumps(dossier.derivations, ensure_ascii=False)}\n"
    else:
        # Empirical track: inject hypotheses
        track_specific = ""
        if dossier.hypotheses:
            track_specific += f"hypotheses: {json.dumps(dossier.hypotheses, ensure_ascii=False)}\n"

    # Dependent outputs (always included)
    deps = f"dependent_task_outputs: {json.dumps(dependent_outputs, ensure_ascii=False)}"

    return base + checklist + constraint_info + track_specific + deps
