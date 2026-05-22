from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

from sciagent.memory_graph import MemoryAtom, MemoryGraph, SUPPORT_LICENSE_ORDER, estimate_token_cost


ALLOWED_FINAL_LICENSES = {"supported", "verified"}
WARNING_LICENSES = {"prohibited", "unsupported", "speculative"}
NORMAL_SECTIONS = {
    "task_contract",
    "problem_kernel",
    "evidence",
    "allowed_claims",
    "derivations",
    "dependent_outputs",
}
PATTERN_VERIFIER_ROLES = {"writer", "formal_deriver", "task_executor", "estimator"}
OBLIGATION_PATTERN_SLOTS = {
    "define": ("term", "definition"),
    "derive": ("premise", "method", "result"),
    "compute": ("inputs", "method", "result"),
    "compare": ("objects", "criterion", "relation"),
    "justify": ("claim", "support"),
}
LAYER_KEYS = (
    "L0_task_contract",
    "L1_problem_kernel",
    "L2_typed_work_memory",
    "L3_structural_state",
    "L4_trajectory",
    "L5_archive",
)


@dataclass(frozen=True)
class RoleProfile:
    required_atom_types: Set[str]
    preferred_atom_types: Set[str]
    allowed_claim_licenses: Set[str]
    include_warning_claims: bool = False
    include_archive_by_default: bool = False
    max_optional_atoms: Dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class StateSignals:
    task_type: str = ""
    domain: str = "unknown"
    pending_obligations: int = 0
    critic_findings: int = 0
    proof_gaps: int = 0
    support_pressure: int = 0
    dependency_pressure: int = 0
    has_draft: bool = False


ROLE_PROFILES = {
    "formal_deriver": RoleProfile(
        required_atom_types={"constraint", "obligation"},
        preferred_atom_types={"problem_fact", "derivation", "claim", "critic_finding"},
        allowed_claim_licenses={"supported", "verified"},
        max_optional_atoms={"minimal": 24, "support_complete": 36, "dependency_complete": 48, "critic_safe": 64},
    ),
    "estimator": RoleProfile(
        required_atom_types={"constraint", "obligation"},
        preferred_atom_types={"problem_fact", "derivation", "claim"},
        allowed_claim_licenses={"supported", "verified"},
        max_optional_atoms={"minimal": 20, "support_complete": 32, "dependency_complete": 44, "critic_safe": 56},
    ),
    "writer": RoleProfile(
        required_atom_types={"constraint", "obligation"},
        preferred_atom_types={"problem_fact", "evidence", "claim", "derivation", "critic_finding"},
        allowed_claim_licenses={"supported", "verified"},
        include_warning_claims=True,
        max_optional_atoms={"minimal": 28, "support_complete": 44, "dependency_complete": 60, "critic_safe": 76},
    ),
    "verification": RoleProfile(
        required_atom_types={"constraint", "obligation"},
        preferred_atom_types={"problem_fact", "evidence", "claim", "derivation", "critic_finding", "task"},
        allowed_claim_licenses={"prohibited", "unsupported", "speculative", "plausible", "supported", "verified"},
        include_warning_claims=True,
        include_archive_by_default=True,
        max_optional_atoms={"minimal": 60, "support_complete": 90, "dependency_complete": 120, "critic_safe": 150},
    ),
    "task_executor": RoleProfile(
        required_atom_types={"constraint", "obligation"},
        preferred_atom_types={"problem_fact", "evidence", "claim", "task", "derivation"},
        allowed_claim_licenses={"plausible", "supported", "verified"},
        max_optional_atoms={"minimal": 22, "support_complete": 34, "dependency_complete": 46, "critic_safe": 58},
    ),
}


@dataclass
class VerifierGap:
    gap_type: str
    atom_id: str = ""
    target_id: str = ""
    message: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "gap_type": self.gap_type,
            "atom_id": self.atom_id,
            "target_id": self.target_id,
            "message": self.message,
        }


@dataclass
class PayloadVerification:
    passed: bool
    gaps: List[VerifierGap] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"passed": self.passed, "gaps": [gap.to_dict() for gap in self.gaps]}


@dataclass
class PayloadView:
    role: str
    task_id: str
    candidate_name: str
    sections: Dict[str, List[Dict[str, Any]]]
    runtime_inputs: Dict[str, Any] = field(default_factory=dict)
    payload_verified: bool = False
    gaps: List[Dict[str, Any]] = field(default_factory=list)
    repair_rounds: int = 0
    rejected_distractors: List[str] = field(default_factory=list)
    verifier_failures: List[Dict[str, Any]] = field(default_factory=list)
    candidate_history: List[Dict[str, Any]] = field(default_factory=list)
    obligation_pattern_report: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def atom_ids(self) -> List[str]:
        ids: List[str] = []
        for atoms in self.sections.values():
            for atom in atoms:
                atom_id = atom.get("id")
                if atom_id and atom_id not in ids:
                    ids.append(atom_id)
        return ids

    @property
    def token_cost(self) -> int:
        atom_cost = sum(int(atom.get("token_cost", 0) or 0) for atoms in self.sections.values() for atom in atoms)
        runtime_cost = estimate_token_cost(_compact_runtime_inputs(self.runtime_inputs, self.role)) if self.runtime_inputs else 0
        return atom_cost + runtime_cost

    @property
    def layer_coverage(self) -> Dict[str, Dict[str, int]]:
        return _layer_coverage_for_sections(self.sections)

    def report(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "task_id": self.task_id,
            "candidate_name": self.candidate_name,
            "payload_verified": self.payload_verified,
            "selected_atoms": self.atom_ids,
            "layer_coverage": self.layer_coverage,
            "obligation_pattern_report": list(self.obligation_pattern_report),
            "token_cost": self.token_cost,
            "gaps": list(self.gaps),
            "repair_rounds": self.repair_rounds,
            "verifier_failures": list(self.verifier_failures),
            "rejected_distractors": list(self.rejected_distractors),
            "candidate_history": list(self.candidate_history),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "task_id": self.task_id,
            "candidate_name": self.candidate_name,
            "sections": self.sections,
            "runtime_inputs": self.runtime_inputs,
            "report": self.report(),
        }


def compile_payload_view(
    graph: MemoryGraph,
    role: str,
    task: Optional[Dict[str, Any]] = None,
    runtime_inputs: Optional[Dict[str, Any]] = None,
    max_repair_rounds: int = 3,
    budget_tokens: Optional[int] = None,
) -> PayloadView:
    role = _normalize_role(role)
    task = _as_dict(task) if task is not None else {}
    runtime_inputs = runtime_inputs or {}
    task_id = str(task.get("id") or runtime_inputs.get("task_id") or role)

    passed_views: List[PayloadView] = []
    history: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    candidate_names = ["minimal", "support_complete", "dependency_complete", "critic_safe", "broad_fallback"]
    signals = _build_state_signals(graph, task, runtime_inputs)

    for candidate_name in candidate_names:
        selected = _candidate_seed_ids(graph, role, task, candidate_name, runtime_inputs, signals)
        view, verification, rounds, repairs = _repair_until_verified(
            graph=graph,
            role=role,
            task_id=task_id,
            candidate_name=candidate_name,
            selected=selected,
            runtime_inputs=runtime_inputs,
            max_repair_rounds=max_repair_rounds,
        )
        view.candidate_history = history + repairs
        history.append({
            "candidate": candidate_name,
            "passed": verification.passed,
            "token_cost": view.token_cost,
            "repair_rounds": rounds,
        })
        if budget_tokens is not None and view.token_cost > budget_tokens:
            verification.gaps.append(
                VerifierGap(
                    gap_type="budget_exceeded",
                    message=f"Payload cost {view.token_cost} exceeds budget {budget_tokens}.",
                ))
            verification.passed = False
        view.payload_verified = verification.passed
        view.gaps = [gap.to_dict() for gap in verification.gaps]
        view.repair_rounds = rounds
        view.verifier_failures = failures + ([] if verification.passed else [verification.to_dict()])
        if verification.passed:
            passed_views.append(view)
        else:
            failures.append({"candidate": candidate_name, "verification": verification.to_dict()})

    if passed_views:
        chosen = min(passed_views, key=lambda item: (item.token_cost, candidate_names.index(item.candidate_name)))
        chosen.candidate_history = history
        chosen.verifier_failures = failures
        return chosen

    fallback = _build_view(
        graph=graph,
        role=role,
        task_id=task_id,
        candidate_name="broad_fallback",
        selected=_candidate_seed_ids(graph, role, task, "broad_fallback", runtime_inputs, signals),
        runtime_inputs=runtime_inputs,
    )
    verification = verify_payload_view(fallback, role, graph)
    fallback.payload_verified = False
    fallback.gaps = [gap.to_dict() for gap in verification.gaps]
    fallback.repair_rounds = max_repair_rounds
    fallback.verifier_failures = failures + [verification.to_dict()]
    fallback.candidate_history = history
    return fallback


def verify_payload_view(view: PayloadView, role: str, graph: Optional[MemoryGraph] = None) -> PayloadVerification:
    role = _normalize_role(role)
    gaps: List[VerifierGap] = []
    atoms_by_id = {atom["id"]: atom for atoms in view.sections.values() for atom in atoms if atom.get("id")}
    section_by_id: Dict[str, str] = {}
    for section, atoms in view.sections.items():
        for atom in atoms:
            atom_id = atom.get("id")
            if atom_id:
                section_by_id[atom_id] = section

    obligations = [
        atom for atom in atoms_by_id.values()
        if atom.get("atom_type") == "obligation" and atom.get("lifecycle") == "active"
    ]
    covered = set()
    for atom in atoms_by_id.values():
        if atom.get("atom_type") != "obligation":
            covered.update(atom.get("obligations") or [])
        if atom.get("atom_type") == "task":
            covered.update(atom.get("depends_on") or [])
    for obligation in obligations:
        if obligation["id"] in covered:
            continue
        if _runtime_covers_obligation(obligation, view.runtime_inputs):
            continue
        if _selected_atom_serves_obligation(obligation, atoms_by_id):
            continue
        else:
            gaps.append(
                VerifierGap(
                    gap_type="missing_obligation_coverage",
                    atom_id=obligation["id"],
                    message=f"Obligation is present but no atom explicitly serves it: {obligation.get('content', '')[:120]}",
                ))

    for atom_id, atom in atoms_by_id.items():
        if section_by_id.get(atom_id) not in NORMAL_SECTIONS:
            continue
        lifecycle = atom.get("lifecycle")
        if lifecycle in {"stale", "suppressed", "archived"}:
            gaps.append(
                VerifierGap(
                    gap_type="invalid_lifecycle",
                    atom_id=atom_id,
                    message=f"Inactive atom appears in normal section: {lifecycle}.",
                ))
        for dep_id in atom.get("depends_on") or []:
            if dep_id not in atoms_by_id:
                gaps.append(
                    VerifierGap(
                        gap_type="missing_dependency",
                        atom_id=atom_id,
                        target_id=dep_id,
                        message=f"Atom depends on missing atom {dep_id}.",
                    ))

    for atom_id, atom in atoms_by_id.items():
        atom_type = atom.get("atom_type")
        section = section_by_id.get(atom_id)
        support_license = atom.get("support_license")
        if atom_type == "claim" and section in {"allowed_claims", "dependent_outputs"}:
            if role in {"writer", "formal_deriver"} and support_license not in ALLOWED_FINAL_LICENSES:
                gaps.append(
                    VerifierGap(
                        gap_type="role_license_violation",
                        atom_id=atom_id,
                        message=f"{role} cannot use {support_license} claim in {section}.",
                    ))
            if support_license not in {"prohibited", "unsupported", "speculative"} and atom.get("source") != "task_output":
                support_ids = atom.get("supported_by") or []
                has_visible_support = any(support_id in atoms_by_id for support_id in support_ids)
                if role in {"writer", "formal_deriver"} and not has_visible_support:
                    gaps.append(
                        VerifierGap(
                            gap_type="missing_support_for_claim",
                            atom_id=atom_id,
                            target_id=support_ids[0] if support_ids else "",
                            message=f"Claim has no support path: {atom.get('content', '')[:120]}",
                        ))
        if support_license == "prohibited" and section in NORMAL_SECTIONS:
            gaps.append(
                VerifierGap(
                    gap_type="prohibited_claim_in_normal_section",
                    atom_id=atom_id,
                    message="Prohibited atom leaked into a normal payload section.",
                ))

    pattern_report, pattern_gaps = _obligation_pattern_gaps(view, role, atoms_by_id, graph)
    view.obligation_pattern_report = pattern_report
    gaps.extend(pattern_gaps)
    gaps.extend(_quality_sufficiency_gaps(view, role, atoms_by_id, graph))
    return PayloadVerification(passed=not gaps, gaps=gaps)


def render_payload_view(view: PayloadView) -> str:
    lines = [
        "COMPILED_PAYLOAD_VIEW:",
        f"role={view.role}; task_id={view.task_id}; verified={str(view.payload_verified).lower()}",
    ]
    for section_name in (
        "task_contract",
        "problem_kernel",
        "evidence",
        "allowed_claims",
        "derivations",
        "warnings",
        "critic_findings",
        "dependent_outputs",
        "archive",
    ):
        if section_name == "archive" and view.role != "verification" and view.candidate_name != "broad_fallback":
            continue
        atoms = view.sections.get(section_name) or []
        if not atoms:
            continue
        lines.append(f"\n{section_name.upper()}:")
        for atom in atoms:
            prefix = _compact_atom_prefix(section_name, atom)
            lines.append(f"- {prefix}{_compact_atom_content(atom, section_name, view.role, view.candidate_name)}")
    compact_runtime = _compact_runtime_inputs(view.runtime_inputs, view.role)
    if compact_runtime:
        lines.append("\nRUNTIME_INPUTS:")
        lines.append(json.dumps(compact_runtime, ensure_ascii=False, default=str))
    return "\n".join(lines)


def _repair_until_verified(
    graph: MemoryGraph,
    role: str,
    task_id: str,
    candidate_name: str,
    selected: Set[str],
    runtime_inputs: Dict[str, Any],
    max_repair_rounds: int,
) -> tuple[PayloadView, PayloadVerification, int, List[Dict[str, Any]]]:
    repairs: List[Dict[str, Any]] = []
    rounds = 0
    last_view = _build_view(graph, role, task_id, candidate_name, selected, runtime_inputs)
    last_verification = verify_payload_view(last_view, role, graph)
    while not last_verification.passed and rounds < max_repair_rounds:
        additions = _repair_for_gaps(graph, selected, last_verification.gaps)
        if not additions:
            break
        rounds += 1
        selected.update(additions)
        repairs.append({
            "candidate": candidate_name,
            "round": rounds,
            "added_atoms": sorted(additions),
            "gaps": [gap.to_dict() for gap in last_verification.gaps],
        })
        last_view = _build_view(graph, role, task_id, candidate_name, selected, runtime_inputs)
        last_verification = verify_payload_view(last_view, role, graph)
    return last_view, last_verification, rounds, repairs


def _repair_for_gaps(graph: MemoryGraph, selected: Set[str], gaps: List[VerifierGap]) -> Set[str]:
    additions: Set[str] = set()
    for gap in gaps:
        if gap.gap_type == "missing_dependency" and gap.target_id in graph.atoms:
            additions.add(gap.target_id)
        elif gap.gap_type == "missing_support_for_claim":
            atom = graph.get(gap.atom_id)
            if atom:
                additions.update(atom.supported_by)
        elif gap.gap_type == "missing_obligation_coverage":
            if gap.atom_id in graph.atoms:
                additions.add(gap.atom_id)
            additions.update(_atoms_for_obligation(graph, gap.atom_id))
        elif gap.gap_type in {"missing_required_obligation", "missing_obligation_slot", "missing_pattern_material"}:
            if gap.atom_id in graph.atoms:
                additions.add(gap.atom_id)
            if gap.target_id in graph.atoms:
                additions.add(gap.target_id)
                target = graph.get(gap.target_id)
                if target:
                    additions.update(target.supported_by)
                    additions.update(target.depends_on)
            additions.update(_atoms_for_obligation(graph, gap.atom_id))
        elif gap.gap_type in {"missing_writer_material", "missing_derivation_material"}:
            if gap.target_id in graph.atoms:
                additions.add(gap.target_id)
                target = graph.get(gap.target_id)
                if target:
                    additions.update(target.supported_by)
                    additions.update(target.depends_on)
    additions.difference_update(selected)
    return additions


def _candidate_seed_ids(
    graph: MemoryGraph,
    role: str,
    task: Dict[str, Any],
    candidate_name: str,
    runtime_inputs: Optional[Dict[str, Any]] = None,
    signals: Optional[StateSignals] = None,
) -> Set[str]:
    selected: Set[str] = set()
    role = _normalize_role(role)
    profile = _role_profile(role)
    signals = signals or _build_state_signals(graph, task, runtime_inputs or {})
    runtime_inputs = runtime_inputs or {}
    runtime_task_definition = _as_dict(runtime_inputs.get("task_definition") or {})
    task_id = str(task.get("id") or runtime_inputs.get("task_id") or runtime_task_definition.get("id") or "")

    candidates: List[MemoryAtom] = []
    for atom in graph.atoms.values():
        if not _passes_hard_gate(atom, role, profile, candidate_name):
            continue
        if _is_required_atom(atom, task_id, profile, candidate_name, role, runtime_inputs or {}):
            selected.add(atom.id)
        else:
            candidates.append(atom)

    cap = profile.max_optional_atoms.get(candidate_name, profile.max_optional_atoms.get("minimal", 24))
    if candidate_name == "broad_fallback":
        cap = max(cap, len(candidates))
    ranked = sorted(
        candidates,
        key=lambda atom: _score_atom(atom, role, task, candidate_name, profile, signals),
        reverse=True,
    )
    for atom in ranked[:cap]:
        if _score_atom(atom, role, task, candidate_name, profile, signals) > -2.0 or candidate_name == "broad_fallback":
            selected.add(atom.id)

    if candidate_name in {"support_complete", "dependency_complete", "critic_safe", "broad_fallback"}:
        selected.update(graph.support_closure(selected))
    if candidate_name in {"dependency_complete", "critic_safe", "broad_fallback"}:
        selected.update(graph.dependency_closure(selected))
    if candidate_name in {"critic_safe", "broad_fallback"}:
        selected.update(atom.id for atom in graph.atoms.values() if atom.atom_type == "critic_finding")
    if candidate_name == "broad_fallback":
        selected.update(atom.id for atom in graph.atoms.values() if atom.lifecycle != "archived")

    return selected


def _role_profile(role: str) -> RoleProfile:
    return ROLE_PROFILES.get(role, ROLE_PROFILES["task_executor"])


def _build_state_signals(graph: MemoryGraph, task: Dict[str, Any], runtime_inputs: Dict[str, Any]) -> StateSignals:
    active_obligations = [
        atom for atom in graph.atoms.values()
        if atom.atom_type in {"obligation", "constraint"} and atom.lifecycle == "active"
    ]
    critics = [atom for atom in graph.atoms.values() if atom.atom_type == "critic_finding" and atom.lifecycle == "active"]
    proof_gaps = [atom for atom in critics if atom.source in {"proof_auditor", "proof_contract"} or "proof_gaps" in atom.source_path]
    support_pressure = sum(
        1 for atom in graph.atoms.values()
        if atom.atom_type == "claim" and atom.support_license in {"supported", "verified"} and atom.supported_by
    )
    dependency_pressure = sum(1 for atom in graph.atoms.values() if atom.depends_on)
    domain = "unknown"
    for atom in graph.atoms.values():
        if atom.domain and atom.domain != "unknown":
            domain = atom.domain
            break
    return StateSignals(
        task_type=str(task.get("task_type") or runtime_inputs.get("task_type") or ""),
        domain=domain,
        pending_obligations=len(active_obligations),
        critic_findings=len(critics),
        proof_gaps=len(proof_gaps),
        support_pressure=support_pressure,
        dependency_pressure=dependency_pressure,
        has_draft=bool(runtime_inputs.get("draft")),
    )


def _passes_hard_gate(atom: MemoryAtom, role: str, profile: RoleProfile, candidate_name: str) -> bool:
    if atom.lifecycle != "active" and candidate_name != "broad_fallback":
        return False
    if atom.atom_type == "archive":
        return profile.include_archive_by_default or candidate_name == "broad_fallback"
    if atom.atom_type == "claim":
        if atom.support_license in profile.allowed_claim_licenses:
            return True
        return profile.include_warning_claims and atom.support_license in WARNING_LICENSES
    if atom.support_license == "prohibited":
        return role == "verification" or profile.include_warning_claims
    return True


def _is_required_atom(
    atom: MemoryAtom,
    task_id: str,
    profile: RoleProfile,
    candidate_name: str,
    role: str,
    runtime_inputs: Dict[str, Any],
) -> bool:
    if task_id and task_id in atom.source_path:
        return True
    if atom.source == "rubric_requirements" and role in {"writer", "verification"}:
        return True
    if atom.atom_type in profile.required_atom_types and atom.source in {"constraint_ledger", "question_intent"}:
        return True
    if atom.atom_type == "constraint" and atom.source in {"context_brief", "axiom_ledger"}:
        return True
    if atom.atom_type == "archive":
        return role == "verification" or candidate_name == "broad_fallback" or bool(runtime_inputs.get("include_full_problem"))
    return False


def _score_atom(
    atom: MemoryAtom,
    role: str,
    task: Dict[str, Any],
    candidate_name: str,
    profile: RoleProfile,
    signals: StateSignals,
) -> float:
    score = atom.role_affinity.get(role, 0.0)
    if atom.atom_type in profile.preferred_atom_types:
        score += 1.5
    if atom.atom_type in profile.required_atom_types:
        score += 1.0
    score += SUPPORT_LICENSE_ORDER.get(atom.support_license, 1) * 0.25
    if atom.domain == signals.domain and signals.domain != "unknown":
        score += 0.3
    if task.get("id") and str(task.get("id")) in atom.source_path:
        score += 2.0
    if atom.source == "rubric_requirements":
        score += 1.6 if role in {"writer", "verification"} else 0.8
    if _content_matches_task(atom.content, task):
        score += 0.8
    if signals.pending_obligations and atom.atom_type in {"obligation", "constraint"}:
        score += min(1.0, signals.pending_obligations / 10)
    if signals.support_pressure and atom.atom_type == "evidence":
        score += 0.7
    if signals.dependency_pressure and atom.atom_type in {"constraint", "problem_fact", "derivation"}:
        score += 0.5
    if signals.critic_findings and atom.atom_type == "critic_finding":
        score += 1.2
    if signals.proof_gaps and role in {"formal_deriver", "writer"} and atom.atom_type in {"critic_finding", "derivation", "constraint"}:
        score += 1.0
    if candidate_name == "critic_safe" and atom.atom_type == "critic_finding":
        score += 1.0
    if candidate_name in {"support_complete", "dependency_complete"} and atom.atom_type in {"evidence", "derivation"}:
        score += 0.4
    score -= atom.distractor_risk * 1.2
    score -= min(2.0, atom.token_cost / 2500)
    return score


def _content_matches_task(content: str, task: Dict[str, Any]) -> bool:
    task_text = " ".join(str(task.get(key, "")) for key in ("title", "deliverable", "task_type"))
    return _has_meaningful_overlap(content, task_text)


def _build_view(
    graph: MemoryGraph,
    role: str,
    task_id: str,
    candidate_name: str,
    selected: Iterable[str],
    runtime_inputs: Dict[str, Any],
) -> PayloadView:
    selected_atoms = [graph.atoms[atom_id] for atom_id in selected if atom_id in graph.atoms]
    selected_atoms.sort(key=_atom_sort_key)
    sections: Dict[str, List[Dict[str, Any]]] = {
        "task_contract": [],
        "problem_kernel": [],
        "evidence": [],
        "allowed_claims": [],
        "derivations": [],
        "warnings": [],
        "critic_findings": [],
        "dependent_outputs": [],
        "archive": [],
    }
    rejected: List[str] = []
    for atom in selected_atoms:
        section = _section_for_atom(atom, role)
        sections[section].append(atom.to_dict())
        if section == "warnings":
            rejected.append(atom.id)
    view = PayloadView(
        role=role,
        task_id=task_id,
        candidate_name=candidate_name,
        sections={key: value for key, value in sections.items() if value},
        runtime_inputs=runtime_inputs,
        rejected_distractors=rejected,
    )
    return view


def _section_for_atom(atom: MemoryAtom, role: str) -> str:
    if atom.lifecycle != "active":
        return "archive"
    if atom.atom_type == "archive":
        return "archive"
    if atom.atom_type in {"obligation", "task"}:
        return "task_contract"
    if atom.atom_type in {"problem_fact", "constraint"}:
        return "problem_kernel"
    if atom.atom_type == "evidence":
        return "evidence"
    if atom.atom_type == "derivation":
        return "derivations"
    if atom.atom_type == "critic_finding":
        return "critic_findings"
    if atom.source == "task_output":
        return "dependent_outputs"
    if atom.atom_type == "claim":
        if role == "verification":
            return "allowed_claims" if atom.support_license not in WARNING_LICENSES else "warnings"
        if atom.support_license in ALLOWED_FINAL_LICENSES:
            return "allowed_claims"
        return "warnings"
    return "problem_kernel"


def _layer_coverage_for_sections(sections: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Dict[str, int]]:
    coverage = {
        layer: {"atom_count": 0, "token_cost": 0, "edge_count": 0}
        for layer in LAYER_KEYS
    }
    for atoms in sections.values():
        for atom in atoms:
            layer = _layer_for_atom(atom)
            coverage[layer]["atom_count"] += 1
            coverage[layer]["token_cost"] += int(atom.get("token_cost", 0) or 0)
            coverage["L3_structural_state"]["edge_count"] += _structural_relation_count(atom)
    return coverage


def _layer_for_atom(atom: Dict[str, Any]) -> str:
    atom_type = str(atom.get("atom_type") or "")
    source = str(atom.get("source") or "")
    lifecycle = str(atom.get("lifecycle") or "active")
    if lifecycle != "active" or atom_type == "archive":
        return "L5_archive"
    if atom_type == "critic_finding":
        return "L4_trajectory"
    if atom_type == "task":
        return "L3_structural_state"
    if atom_type == "obligation":
        return "L0_task_contract"
    if atom_type in {"problem_fact", "constraint"}:
        return "L1_problem_kernel"
    if atom_type in {"evidence", "claim", "derivation"} or source == "task_output":
        return "L2_typed_work_memory"
    return "L1_problem_kernel"


def _structural_relation_count(atom: Dict[str, Any]) -> int:
    relation_fields = ("obligations", "depends_on", "supports", "supported_by", "prohibits", "conflicts")
    return sum(len(atom.get(field) or []) for field in relation_fields)


def _obligation_pattern_gaps(
    view: PayloadView,
    role: str,
    atoms_by_id: Dict[str, Dict[str, Any]],
    graph: Optional[MemoryGraph],
) -> tuple[List[Dict[str, Any]], List[VerifierGap]]:
    role = _normalize_role(role)
    if role not in PATTERN_VERIFIER_ROLES:
        return [], []

    required_obligations = _required_obligations_for_call(graph, view, role, atoms_by_id)
    if not required_obligations:
        return [], []

    reports: List[Dict[str, Any]] = []
    gaps: List[VerifierGap] = []
    selected_ids = set(atoms_by_id)
    for obligation in required_obligations:
        obligation_id = str(obligation.get("id") or "")
        pattern_type = _infer_obligation_type(obligation, view.runtime_inputs)
        required_slots = set(OBLIGATION_PATTERN_SLOTS.get(pattern_type, OBLIGATION_PATTERN_SLOTS["justify"]))
        serving_atoms = _serving_atoms_for_obligation(obligation, atoms_by_id)
        covered_slots = _covered_obligation_slots(pattern_type, obligation, serving_atoms, atoms_by_id, role)
        missing_slots = sorted(required_slots - covered_slots)
        repair_candidates = _pattern_repair_candidates(
            graph=graph,
            obligation=obligation,
            pattern_type=pattern_type,
            missing_slots=missing_slots,
            role=role,
            selected_ids=selected_ids,
        )
        repair_ids = [atom.id for atom in repair_candidates]
        reports.append({
            "obligation_id": obligation_id,
            "obligation_type": pattern_type,
            "required_slots": sorted(required_slots),
            "covered_slots": sorted(covered_slots),
            "missing_slots": missing_slots,
            "serving_atom_ids": [str(atom.get("id")) for atom in serving_atoms if atom.get("id")],
            "repair_candidate_ids": repair_ids[:5],
        })

        if obligation_id and obligation_id not in atoms_by_id:
            gaps.append(VerifierGap(
                gap_type="missing_required_obligation",
                atom_id=obligation_id,
                target_id=repair_candidates[0].id if repair_candidates else "",
                message=f"Required obligation is absent from payload; pattern={pattern_type}.",
            ))
            continue
        if missing_slots and repair_candidates:
            gaps.append(VerifierGap(
                gap_type="missing_obligation_slot",
                atom_id=obligation_id,
                target_id=repair_candidates[0].id,
                message=(
                    f"Obligation pattern `{pattern_type}` missing slots: {', '.join(missing_slots)}."
                ),
            ))
        elif missing_slots and _has_invalid_selected_pattern_material(serving_atoms, role):
            gaps.append(VerifierGap(
                gap_type="missing_pattern_material",
                atom_id=obligation_id,
                message=(
                    f"Selected material for `{pattern_type}` obligation is not role-licensed enough; "
                    f"missing slots: {', '.join(missing_slots)}."
                ),
            ))
    return reports, gaps


def _required_obligations_for_call(
    graph: Optional[MemoryGraph],
    view: PayloadView,
    role: str,
    atoms_by_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    required: Dict[str, Dict[str, Any]] = {
        atom["id"]: atom
        for atom in atoms_by_id.values()
        if atom.get("id") and atom.get("atom_type") == "obligation" and atom.get("lifecycle") == "active"
    }
    if graph is None:
        return list(required.values())

    referenced = set()
    for atom in atoms_by_id.values():
        referenced.update(atom.get("obligations") or [])
        if atom.get("atom_type") == "task":
            referenced.update(atom.get("depends_on") or [])

    runtime_text = _runtime_obligation_text(view.runtime_inputs, role)
    task_id = str(view.task_id or "")
    for atom in graph.atoms.values():
        if atom.atom_type != "obligation" or atom.lifecycle != "active":
            continue
        if atom.id in required:
            continue
        if atom.id in referenced:
            required[atom.id] = atom.to_dict()
            continue
        if task_id and task_id not in {"writer", role} and task_id in atom.source_path:
            required[atom.id] = atom.to_dict()
            continue
        if atom.source == "rubric_requirements" and role in {"writer", "formal_deriver", "task_executor"}:
            required[atom.id] = atom.to_dict()
            continue
        if atom.source in {"constraint_ledger", "question_intent"} and _has_meaningful_overlap(atom.content, runtime_text):
            required[atom.id] = atom.to_dict()
            continue
        if atom.source == "task_graph" and _has_meaningful_overlap(atom.content, runtime_text):
            required[atom.id] = atom.to_dict()
    return list(required.values())


def _infer_obligation_type(obligation: Dict[str, Any], runtime_inputs: Dict[str, Any]) -> str:
    content = str(obligation.get("content") or "")
    text = f"{content} {_runtime_obligation_text(runtime_inputs, '')}".lower()
    if _has_any(text, ("compare", "contrast", "versus", " vs", "alternative", "tradeoff", "relation between")):
        return "compare"
    if _has_any(text, ("compute", "calculate", "find the exact", "evaluate", "estimate", "numerical", "value")):
        return "compute"
    if _has_any(text, ("derive", "derivation", "prove", "show that", "equation", "formula", "expression", "intermediate")):
        return "derive"
    if _has_any(text, ("define", "definition", "symbol", "variable", "term", "meaning")):
        return "define"
    return "justify"


def _serving_atoms_for_obligation(
    obligation: Dict[str, Any],
    atoms_by_id: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    serving: List[Dict[str, Any]] = []
    for atom in atoms_by_id.values():
        if atom.get("atom_type") == "obligation" or atom.get("id") == obligation.get("id"):
            continue
        if _atom_relevant_to_obligation(atom, obligation):
            serving.append(atom)
    return serving


def _covered_obligation_slots(
    pattern_type: str,
    obligation: Dict[str, Any],
    serving_atoms: List[Dict[str, Any]],
    atoms_by_id: Dict[str, Dict[str, Any]],
    role: str,
) -> Set[str]:
    covered: Set[str] = set()
    for atom in serving_atoms:
        for slot in OBLIGATION_PATTERN_SLOTS.get(pattern_type, OBLIGATION_PATTERN_SLOTS["justify"]):
            if _atom_covers_pattern_slot(atom, slot, pattern_type, role, atoms_by_id):
                covered.add(slot)
    return covered


def _pattern_repair_candidates(
    graph: Optional[MemoryGraph],
    obligation: Dict[str, Any],
    pattern_type: str,
    missing_slots: List[str],
    role: str,
    selected_ids: Set[str],
) -> List[MemoryAtom]:
    if graph is None or not missing_slots:
        return []
    candidates: List[MemoryAtom] = []
    for atom in graph.atoms.values():
        if atom.id in selected_ids or atom.lifecycle != "active" or atom.atom_type == "obligation":
            continue
        if atom.atom_type not in {"problem_fact", "constraint", "evidence", "claim", "derivation", "task"} and atom.source != "task_output":
            continue
        if not _atom_allowed_for_pattern(atom, role):
            continue
        if not _atom_relevant_to_obligation(atom.to_dict(), obligation):
            continue
        if not any(_atom_covers_pattern_slot(atom.to_dict(), slot, pattern_type, role, {}) for slot in missing_slots):
            continue
        candidates.append(atom)

    def score(atom: MemoryAtom) -> float:
        value = SUPPORT_LICENSE_ORDER.get(atom.support_license, 1) * 0.25
        value += atom.role_affinity.get(role, 0.0)
        if atom.atom_type in {"derivation", "claim"} or atom.source == "task_output":
            value += 1.2
        if atom.atom_type in {"problem_fact", "constraint", "evidence"}:
            value += 0.7
        value -= min(1.5, atom.token_cost / 2000)
        return value

    return sorted(candidates, key=score, reverse=True)


def _atom_relevant_to_obligation(atom: Dict[str, Any], obligation: Dict[str, Any]) -> bool:
    obligation_id = obligation.get("id")
    if obligation_id and (
        obligation_id in (atom.get("obligations") or [])
        or obligation_id in (atom.get("depends_on") or [])
    ):
        return True
    return _has_meaningful_overlap(str(obligation.get("content") or ""), str(atom.get("content") or ""))


def _atom_allowed_for_pattern(atom: MemoryAtom, role: str) -> bool:
    if atom.support_license == "prohibited":
        return False
    if atom.atom_type == "claim" and role in {"writer", "formal_deriver"}:
        return atom.support_license in ALLOWED_FINAL_LICENSES
    return atom.support_license not in {"prohibited", "unsupported", "speculative"} or role == "task_executor"


def _atom_covers_pattern_slot(
    atom: Dict[str, Any],
    slot: str,
    pattern_type: str,
    role: str,
    atoms_by_id: Dict[str, Dict[str, Any]],
) -> bool:
    atom_type = str(atom.get("atom_type") or "")
    source = str(atom.get("source") or "")
    license_value = str(atom.get("support_license") or "unsupported")
    content = str(atom.get("content") or "")
    lower = content.lower()
    if license_value == "prohibited":
        return False
    if atom_type == "claim" and role in {"writer", "formal_deriver"} and license_value not in ALLOWED_FINAL_LICENSES:
        return False
    is_task_output = source == "task_output"
    is_result_material = atom_type in {"derivation", "claim"} or is_task_output
    is_grounding_material = atom_type in {"problem_fact", "constraint", "evidence"} or is_task_output
    has_formula_or_method = _looks_like_symbolic_or_method_content(content)
    if slot in {"term", "definition", "objects", "criterion"}:
        return is_grounding_material or is_result_material
    if slot in {"premise", "inputs"}:
        return is_grounding_material or _has_any(lower, ("given", "input", "assumption", "condition", "unit", "boundary"))
    if slot == "method":
        return atom_type == "derivation" or is_task_output or has_formula_or_method or _has_any(lower, ("method", "using", "by ", "from ", "therefore"))
    if slot == "result":
        return is_result_material
    if slot == "relation":
        return is_result_material or _has_any(lower, ("less", "greater", "same", "increase", "decrease", "equal", "tradeoff", "<", ">", "≤", ">="))
    if slot == "claim":
        return is_result_material and (atom_type != "claim" or license_value in ALLOWED_FINAL_LICENSES or role == "task_executor")
    if slot == "support":
        if atom_type in {"evidence", "derivation"} or is_task_output:
            return True
        support_ids = atom.get("supported_by") or []
        return bool(support_ids and any(support_id in atoms_by_id for support_id in support_ids))
    return False


def _has_invalid_selected_pattern_material(serving_atoms: List[Dict[str, Any]], role: str) -> bool:
    if role not in {"writer", "formal_deriver"}:
        return False
    for atom in serving_atoms:
        if atom.get("atom_type") == "claim" and atom.get("support_license") not in ALLOWED_FINAL_LICENSES:
            return True
    return False


def _runtime_obligation_text(runtime_inputs: Dict[str, Any], role: str) -> str:
    compact = _compact_runtime_inputs(runtime_inputs or {}, role)
    return json.dumps(compact, ensure_ascii=False, default=str)


def _looks_like_symbolic_or_method_content(content: str) -> bool:
    lower = str(content or "").lower()
    if _has_any(lower, ("formula", "equation", "derive", "derivation", "calculate", "compute", "using", "substitute")):
        return True
    return any(marker in str(content) for marker in ("=", "\\", "^", "_", "∑", "≤", ">=", "<=", "≈", "->"))


def _atoms_for_obligation(graph: MemoryGraph, obligation_id: str) -> Set[str]:
    matches = set()
    for atom in graph.atoms.values():
        if obligation_id in atom.obligations or obligation_id in atom.depends_on:
            matches.add(atom.id)
    return matches


def _selected_atom_serves_obligation(obligation: Dict[str, Any], atoms_by_id: Dict[str, Dict[str, Any]]) -> bool:
    obligation_id = obligation.get("id")
    obligation_text = str(obligation.get("content") or "")
    for atom in atoms_by_id.values():
        if atom.get("id") == obligation_id or atom.get("atom_type") == "obligation":
            continue
        if obligation_id in (atom.get("obligations") or []) or obligation_id in (atom.get("depends_on") or []):
            return True
        if atom.get("atom_type") in {"task", "constraint", "evidence", "claim", "derivation", "problem_fact"}:
            if _has_meaningful_overlap(obligation_text, str(atom.get("content") or "")):
                return True
    return False


def _quality_sufficiency_gaps(
    view: PayloadView,
    role: str,
    atoms_by_id: Dict[str, Dict[str, Any]],
    graph: Optional[MemoryGraph],
) -> List[VerifierGap]:
    if graph is None:
        return []
    role = _normalize_role(role)
    if role != "writer":
        return []

    available_materials = _available_writer_materials(graph)
    if not available_materials:
        return []
    if any(_is_writer_material_atom(atom) for atom in atoms_by_id.values()):
        return []

    target = _best_material_repair_target(available_materials, view.runtime_inputs, role)
    if target is None:
        return []
    return [
        VerifierGap(
            gap_type="missing_writer_material",
            target_id=target.id,
            message=(
                "Writer payload has supported derivation/task-output material available in the memory graph, "
                "but no writable material atom is selected."
            ),
        )
    ]


def _available_writer_materials(graph: MemoryGraph) -> List[MemoryAtom]:
    materials: List[MemoryAtom] = []
    for atom in graph.atoms.values():
        if atom.lifecycle != "active":
            continue
        if atom.atom_type == "derivation" and atom.support_license in ALLOWED_FINAL_LICENSES:
            materials.append(atom)
            continue
        if atom.atom_type == "claim" and atom.support_license in ALLOWED_FINAL_LICENSES:
            if atom.source in {"task_output", "formal_deriver", "estimator", "synthesizer"}:
                materials.append(atom)
    return materials


def _is_writer_material_atom(atom: Dict[str, Any]) -> bool:
    if atom.get("atom_type") == "derivation" and atom.get("support_license") in ALLOWED_FINAL_LICENSES:
        return True
    if atom.get("atom_type") == "claim" and atom.get("support_license") in ALLOWED_FINAL_LICENSES:
        return atom.get("source") in {"task_output", "formal_deriver", "estimator", "synthesizer"}
    return False


def _best_material_repair_target(
    materials: List[MemoryAtom],
    runtime_inputs: Dict[str, Any],
    role: str,
) -> Optional[MemoryAtom]:
    runtime_text = json.dumps(_compact_runtime_inputs(runtime_inputs, role), ensure_ascii=False, default=str)

    def score(atom: MemoryAtom) -> float:
        value = atom.role_affinity.get(role, 0.0)
        value += SUPPORT_LICENSE_ORDER.get(atom.support_license, 1) * 0.25
        if atom.source == "task_output":
            value += 0.8
        if _has_meaningful_overlap(atom.content, runtime_text):
            value += 0.6
        value -= min(1.5, atom.token_cost / 2000)
        return value

    return max(materials, key=score) if materials else None


def _runtime_covers_obligation(obligation: Dict[str, Any], runtime_inputs: Dict[str, Any]) -> bool:
    content = str(obligation.get("content") or "")
    if not content:
        return False
    if obligation.get("source") == "rubric_requirements":
        return False
    runtime_text = json.dumps(_compact_runtime_inputs(runtime_inputs, ""), ensure_ascii=False, default=str)
    if _has_meaningful_overlap(content, runtime_text):
        return True
    lower = content.lower()
    if any(marker in lower for marker in (
        "show all",
        "step",
        "step by step",
        "derive",
        "derivation",
        "format",
        "include all",
        "intermediate",
        "justification",
        "detailed reasoning",
        "compare",
        "summarize",
        "summarise",
        "conclusion",
    )):
        return any(key in runtime_inputs for key in (
            "task_definition",
            "mandatory_checklist",
            "proof_plan",
            "task_outputs",
            "dependent_task_outputs",
            "all_prior_task_outputs",
            "derivations",
            "selected_rationales",
            "draft",
        ))
    return False


def _has_meaningful_overlap(left: str, right: str) -> bool:
    left_terms = _content_terms(left)
    right_terms = _content_terms(right)
    if not left_terms or not right_terms:
        return False
    shared = left_terms & right_terms
    return len(shared) >= min(2, len(left_terms))


def _has_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def _content_terms(text: str) -> Set[str]:
    import re

    normalized = str(text).replace("-", " ")
    stop = {
        "the", "and", "for", "with", "from", "that", "this", "should", "must", "into", "your", "about", "using",
        "give", "show", "all", "each", "what", "which", "when", "where", "how", "why", "are", "was", "were",
        "problem", "requires", "required", "include", "includes", "including", "term", "terms",
    }
    return {
        term.lower()
        for term in re.findall(r"[A-Za-z][A-Za-z0-9_\\^]{1,}", normalized)
        if term.lower() not in stop
    }


def _compact_atom_prefix(section_name: str, atom: Dict[str, Any]) -> str:
    if section_name == "warnings":
        return "[warning] "
    if section_name == "critic_findings":
        return "[critic] "
    if atom.get("support_license") in {"supported", "verified"} and section_name in {"evidence", "allowed_claims"}:
        return "[supported] "
    return ""


def _compact_atom_content(
    atom: Dict[str, Any],
    section_name: str = "",
    role: str = "",
    candidate_name: str = "",
) -> str:
    content = atom.get("content", "")
    if section_name == "archive" and (role == "verification" or candidate_name == "broad_fallback"):
        return " ".join(str(content or "").split())
    parsed: Any = None
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except (TypeError, ValueError):
            parsed = None
    if isinstance(parsed, dict):
        atom_type = atom.get("atom_type")
        if atom_type == "task":
            return _compact_text(_stable_json_subset(
                parsed,
                ("title", "deliverable", "task_type", "micro_checklists", "depends_on"),
            ))
        if atom_type == "derivation":
            return _compact_text(_stable_json_subset(
                parsed,
                ("title", "result", "latex", "assumptions", "scope", "confidence"),
            ))
        if atom_type == "critic_finding":
            return _compact_text(_stable_json_subset(
                parsed,
                ("severity", "message", "suggestion", "constraint_id", "target"),
            ))
    return _compact_text(content)


def _stable_json_subset(value: Dict[str, Any], keys: Iterable[str]) -> str:
    compact = {key: value[key] for key in keys if key in value and value[key]}
    return json.dumps(compact or value, ensure_ascii=False, sort_keys=True, default=str)


def _compact_text(text: Any, max_chars: int = 1200) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= max_chars:
        return value
    return value[:max_chars].rstrip() + " ..."


def _compact_runtime_inputs(runtime_inputs: Dict[str, Any], role: str) -> Dict[str, Any]:
    if not runtime_inputs:
        return {}
    allowed = {
        "task_definition",
        "mandatory_checklist",
        "derivation_methodology",
        "dependent_task_outputs",
        "all_prior_task_outputs",
        "proof_plan",
        "derivation_intent",
        "patch_plan",
        "validated_hypotheses",
        "demoted_hypotheses_for_alternatives_only",
        "reasoning_alignment_warnings",
        "selected_rationales",
        "unsatisfied_constraints",
        "subject_profile",
    }
    if role == "verification":
        allowed.update({"draft", "task_outputs"})
    compact: Dict[str, Any] = {}
    for key in allowed:
        value = runtime_inputs.get(key)
        if value:
            compact[key] = _compact_value(value, key)
    return compact


def _compact_value(value: Any, key: str) -> Any:
    if isinstance(value, str):
        limit = 6000 if key == "draft" else 1600
        return _compact_text(value, limit)
    if isinstance(value, list):
        return [_compact_value(item, key) for item in value[:12]]
    if isinstance(value, dict):
        compact: Dict[str, Any] = {}
        for idx, (child_key, child_value) in enumerate(value.items()):
            if idx >= 20:
                compact["..."] = f"{len(value) - idx} more entries omitted"
                break
            if child_key in {"problem", "essential_context", "optional_context", "context_brief", "constraint_ledger", "question_intent", "domain_route", "task_graph"}:
                continue
            compact[str(child_key)] = _compact_value(child_value, str(child_key))
        return compact
    return value


def _atom_sort_key(atom: MemoryAtom) -> tuple[int, int, str]:
    type_rank = {
        "archive": 0,
        "obligation": 1,
        "constraint": 2,
        "problem_fact": 3,
        "evidence": 4,
        "derivation": 5,
        "claim": 6,
        "critic_finding": 7,
        "task": 8,
    }.get(atom.atom_type, 99)
    license_rank = -SUPPORT_LICENSE_ORDER.get(atom.support_license, 1)
    return (type_rank, license_rank, atom.id)


def _normalize_role(role: str) -> str:
    role = str(role or "").strip().lower()
    aliases = {
        "scientific_writer": "writer",
        "writer_agent": "writer",
        "verification_agent": "verification",
        "formal_deriver_agent": "formal_deriver",
        "derive": "formal_deriver",
        "parameter_estimation": "estimator",
    }
    return aliases.get(role, role or "task_executor")


def _as_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value
