"""
Dual-Track Epistemic Routing Patch for runner.py

Replace lines 1110-1135 with this implementation to enable domain-aware routing.
"""

# =============================================================================
# DUAL-TRACK EPISTEMIC ROUTING (Domain-Aware Architecture)
# =============================================================================
# Track A: Deductive (Physics/Math) - uses AxiomLedger, skips HypothesisModeler
# Track B: Empirical (Biology/Chemistry) - uses HypothesisModeler, minimal axioms
# =============================================================================

domain = dossier.domain_route.get("domain", "")
is_deductive_track = (
    domain == "physics" or
    dossier.derivation_intent.get("proof_heavy", False)
)

if is_deductive_track:
    # -------------------------------------------------------------------------
    # TRACK A: DEDUCTIVE REASONING (Physics/Math)
    # -------------------------------------------------------------------------
    # Build rigorous axiomatic framework
    axiom_output = axiom_builder.run(
        f"problem_text: {problem_text}\n"
        f"context_brief: {json.dumps(dossier.context, ensure_ascii=False)}\n"
        f"domain_route: {json.dumps(dossier.domain_route, ensure_ascii=False)}\n"
        f"subject_profile: {json.dumps(dossier.subject_profile, ensure_ascii=False)}"
    )
    dossier.axiom_ledger = _safe_agent_json(axiom_output, fallback={
        "space_type": "", "particle_type": "", "state_hierarchy": [],
        "formalism": "", "symmetries": [], "boundary_conditions": [],
        "violation_checks": [], "notes": []
    })
    tools["archive"].forward("axiom_ledger", json.dumps(dossier.axiom_ledger, ensure_ascii=False))

    # Skip hypothesis modeling - not applicable to deductive reasoning
    dossier.hypotheses = None

else:
    # -------------------------------------------------------------------------
    # TRACK B: EMPIRICAL REASONING (Biology/Chemistry)
    # -------------------------------------------------------------------------
    # Build causal hypothesis framework
    hypothesis_output = hypothesis_modeler.run(
        f"problem_text: {problem_text}\n"
        f"context_brief: {json.dumps(dossier.context, ensure_ascii=False)}\n"
        f"domain_route: {json.dumps(dossier.domain_route, ensure_ascii=False)}\n"
        f"subject_profile: {json.dumps(dossier.subject_profile, ensure_ascii=False)}\n"
        f"task_graph: {json.dumps(dossier.task_graph, ensure_ascii=False)}"
    )
    dossier.hypotheses = _safe_agent_json(hypothesis_output, fallback={"hypotheses": [], "notes": []})
    tools["archive"].forward("hypotheses", json.dumps(dossier.hypotheses, ensure_ascii=False))

    # Minimal axiom ledger for empirical sciences
    dossier.axiom_ledger = {
        "biological_axioms": dossier.context.get("assumptions_in_text", []),
        "notes": ["Empirical track: axioms derived from experimental context"]
    }
