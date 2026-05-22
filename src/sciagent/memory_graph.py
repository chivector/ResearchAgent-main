from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


SUPPORT_LICENSE_ORDER = {
    "prohibited": 0,
    "unsupported": 1,
    "speculative": 2,
    "plausible": 3,
    "supported": 4,
    "verified": 5,
}


@dataclass
class MemoryAtom:
    id: str
    atom_type: str
    content: str
    source: str
    source_path: str = ""
    domain: str = "unknown"
    support_license: str = "unsupported"
    obligations: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    supports: List[str] = field(default_factory=list)
    supported_by: List[str] = field(default_factory=list)
    prohibits: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    lifecycle: str = "active"
    role_affinity: Dict[str, float] = field(default_factory=dict)
    distractor_risk: float = 0.0
    token_cost: int = 0

    def __post_init__(self) -> None:
        self.support_license = _normalize_support_license(self.support_license)
        self.token_cost = self.token_cost or estimate_token_cost(self.content)
        self.obligations = _dedupe(self.obligations)
        self.depends_on = _dedupe(self.depends_on)
        self.supports = _dedupe(self.supports)
        self.supported_by = _dedupe(self.supported_by)
        self.prohibits = _dedupe(self.prohibits)
        self.conflicts = _dedupe(self.conflicts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "atom_type": self.atom_type,
            "content": self.content,
            "source": self.source,
            "source_path": self.source_path,
            "domain": self.domain,
            "support_license": self.support_license,
            "obligations": list(self.obligations),
            "depends_on": list(self.depends_on),
            "supports": list(self.supports),
            "supported_by": list(self.supported_by),
            "prohibits": list(self.prohibits),
            "conflicts": list(self.conflicts),
            "lifecycle": self.lifecycle,
            "role_affinity": dict(self.role_affinity),
            "distractor_risk": self.distractor_risk,
            "token_cost": self.token_cost,
        }


@dataclass(frozen=True)
class MemoryEdge:
    source: str
    target: str
    edge_type: str

    def to_dict(self) -> Dict[str, str]:
        return {"source": self.source, "target": self.target, "edge_type": self.edge_type}


class MemoryGraph:
    def __init__(self) -> None:
        self.atoms: Dict[str, MemoryAtom] = {}
        self.edges: List[MemoryEdge] = []

    def add_atom(self, atom: MemoryAtom) -> MemoryAtom:
        existing = self.atoms.get(atom.id)
        if existing is None:
            self.atoms[atom.id] = atom
            return atom

        existing.obligations = _dedupe(existing.obligations + atom.obligations)
        existing.depends_on = _dedupe(existing.depends_on + atom.depends_on)
        existing.supports = _dedupe(existing.supports + atom.supports)
        existing.supported_by = _dedupe(existing.supported_by + atom.supported_by)
        existing.prohibits = _dedupe(existing.prohibits + atom.prohibits)
        existing.conflicts = _dedupe(existing.conflicts + atom.conflicts)
        existing.role_affinity.update(atom.role_affinity)
        existing.distractor_risk = max(existing.distractor_risk, atom.distractor_risk)
        if _license_value(atom.support_license) > _license_value(existing.support_license):
            existing.support_license = atom.support_license
        return existing

    def add_edge(self, source: str, target: str, edge_type: str) -> None:
        if source not in self.atoms or target not in self.atoms:
            return
        edge = MemoryEdge(source=source, target=target, edge_type=edge_type)
        if edge in self.edges:
            return
        self.edges.append(edge)
        source_atom = self.atoms[source]
        target_atom = self.atoms[target]
        if edge_type == "depends_on":
            source_atom.depends_on = _dedupe(source_atom.depends_on + [target])
        elif edge_type == "supports":
            source_atom.supports = _dedupe(source_atom.supports + [target])
            target_atom.supported_by = _dedupe(target_atom.supported_by + [source])
        elif edge_type == "prohibits":
            source_atom.prohibits = _dedupe(source_atom.prohibits + [target])
        elif edge_type == "conflicts":
            source_atom.conflicts = _dedupe(source_atom.conflicts + [target])
            target_atom.conflicts = _dedupe(target_atom.conflicts + [source])
        elif edge_type == "serves_obligation":
            source_atom.obligations = _dedupe(source_atom.obligations + [target])

    def get(self, atom_id: str) -> Optional[MemoryAtom]:
        return self.atoms.get(atom_id)

    def active_atoms(self) -> List[MemoryAtom]:
        return [atom for atom in self.atoms.values() if atom.lifecycle == "active"]

    def atoms_by_type(self, *atom_types: str) -> List[MemoryAtom]:
        wanted = set(atom_types)
        return [atom for atom in self.atoms.values() if atom.atom_type in wanted]

    def dependency_closure(self, atom_ids: Iterable[str]) -> List[str]:
        selected = set(atom_ids)
        queue = list(atom_ids)
        while queue:
            atom_id = queue.pop(0)
            atom = self.atoms.get(atom_id)
            if atom is None:
                continue
            for dep_id in atom.depends_on:
                if dep_id in self.atoms and dep_id not in selected:
                    selected.add(dep_id)
                    queue.append(dep_id)
        return sorted(selected)

    def support_closure(self, atom_ids: Iterable[str]) -> List[str]:
        selected = set(atom_ids)
        queue = list(atom_ids)
        while queue:
            atom_id = queue.pop(0)
            atom = self.atoms.get(atom_id)
            if atom is None:
                continue
            for support_id in atom.supported_by:
                if support_id in self.atoms and support_id not in selected:
                    selected.add(support_id)
                    queue.append(support_id)
        return sorted(selected)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "atoms": [atom.to_dict() for atom in self.atoms.values()],
            "edges": [edge.to_dict() for edge in self.edges],
        }


def estimate_token_cost(content: Any) -> int:
    text = content if isinstance(content, str) else _stable_json(content)
    return max(1, math.ceil(len(text) / 4))


def build_memory_graph_from_dossier(dossier: Any) -> MemoryGraph:
    data = _as_dict(dossier)
    graph = MemoryGraph()
    domain = _read_domain(data)

    problem_text = str(data.get("problem") or "").strip()
    if problem_text:
        _add_atom(
            graph,
            "archive",
            problem_text,
            source="problem_text",
            source_path="problem",
            domain=domain,
            support_license="verified",
            role_affinity={"verification": 0.9},
        )

    _add_context_atoms(graph, data.get("context") or {}, domain)
    _add_rubric_requirement_atoms(graph, data, domain)
    _add_question_intent_atoms(graph, data.get("question_intent") or {}, domain)
    _add_constraint_ledger_atoms(graph, data.get("constraint_ledger") or {}, domain)
    _add_task_graph_atoms(graph, data.get("task_graph") or {}, domain)
    _add_axiom_atoms(graph, data.get("axiom_ledger") or {}, domain)
    _add_hypothesis_atoms(graph, data.get("hypotheses") or {}, domain)
    _add_derivation_atoms(graph, data.get("derivations") or [], domain)
    _add_task_output_atoms(graph, data.get("task_outputs") or {}, domain)
    _add_critic_atoms(graph, data.get("verification") or {}, "verification", domain)
    _add_proof_gap_atoms(graph, data.get("proof_gaps") or {}, domain)

    return graph


def _add_context_atoms(graph: MemoryGraph, context: Any, domain: str) -> None:
    context = _as_dict(context)
    if not isinstance(context, dict):
        return

    for idx, text in enumerate(_listify(context.get("subquestions"))):
        _add_atom(
            graph,
            "obligation",
            text,
            source="context_brief",
            source_path=f"context.subquestions[{idx}]",
            domain=domain,
            support_license="verified",
            role_affinity={"writer": 1.0, "verification": 1.0},
        )

    for field_name in (
        "deliverables",
        "must_have_terms",
    ):
        for idx, text in enumerate(_listify(context.get(field_name))):
            _add_atom(
                graph,
                "obligation",
                text,
                source="context_brief",
                source_path=f"context.{field_name}[{idx}]",
                domain=domain,
                support_license="verified",
                role_affinity={"writer": 1.0, "verification": 1.0},
            )

    for field_name in (
        "constraints",
        "negative_constraints",
        "unchanged_features",
        "core_conflicts",
        "temporal_context",
        "spatial_context",
        "equations_and_formulas",
    ):
        for idx, text in enumerate(_listify(context.get(field_name))):
            _add_atom(
                graph,
                "constraint",
                text,
                source="context_brief",
                source_path=f"context.{field_name}[{idx}]",
                domain=domain,
                support_license="verified",
                role_affinity={"formal_deriver": 1.0, "writer": 1.0, "verification": 1.0},
            )

    for field_name in ("empirical_evidence", "reaction_tuples"):
        for idx, text in enumerate(_listify(context.get(field_name))):
            _add_atom(
                graph,
                "evidence",
                _stable_json(text) if isinstance(text, (dict, list)) else str(text),
                source="context_brief",
                source_path=f"context.{field_name}[{idx}]",
                domain=domain,
                support_license="verified",
                role_affinity={"writer": 0.9, "verification": 1.0},
            )

    evidence_mapping = context.get("evidence_mapping") or {}
    if isinstance(evidence_mapping, dict):
        for key, value in evidence_mapping.items():
            if value:
                _add_atom(
                    graph,
                    "evidence",
                    f"{key}: {value}",
                    source="context_brief",
                    source_path=f"context.evidence_mapping.{key}",
                    domain=domain,
                    support_license="verified",
                    role_affinity={"writer": 1.0, "verification": 1.0},
                )

    for field_name in ("given_data", "reaction_conditions", "phenotype_summary", "entity_map"):
        value = context.get(field_name)
        if value:
            _add_atom(
                graph,
                "problem_fact",
                f"{field_name}: {_stable_json(value)}",
                source="context_brief",
                source_path=f"context.{field_name}",
                domain=domain,
                support_license="verified",
                role_affinity={"formal_deriver": 0.9, "writer": 0.8, "verification": 0.9},
            )


def _add_rubric_requirement_atoms(graph: MemoryGraph, data: Dict[str, Any], domain: str) -> None:
    text = _rubric_text_blob(data)
    if not text:
        return

    requirements: List[tuple[str, str, float]] = _generic_rubric_requirements(data)

    seen = set()
    deduped: List[tuple[str, str, float]] = []
    for title, content, distractor_risk in requirements:
        key = (title.strip().lower(), content.strip().lower())
        if not title.strip() or not content.strip() or key in seen:
            continue
        seen.add(key)
        deduped.append((title, content, distractor_risk))

    for idx, (title, content, distractor_risk) in enumerate(deduped[:36]):
        _add_requirement_pair(graph, idx, title, content, domain, distractor_risk)


def _generic_rubric_requirements(data: Dict[str, Any]) -> List[tuple[str, str, float]]:
    problem_text = str(data.get("problem") or "")
    requirements: List[tuple[str, str, float]] = []

    for idx, formula in enumerate(_extract_formula_fragments(data)[:10]):
        requirements.append((
            f"prompt formula {idx + 1}",
            f"Preserve and use the prompt formula `{formula}` in the relevant derivation or answer section; define the symbols and explain its role.",
            0.05,
        ))

    for idx, item in enumerate(_extract_enumerated_requirements(problem_text)[:8]):
        requirements.append((
            f"required answer part {idx + 1}",
            f"Answer this requested part explicitly and separately: {item}",
            0.0,
        ))

    for idx, item in enumerate(_extract_declared_grading_focus(data)[:8]):
        requirements.append((
            f"declared grading focus {idx + 1}",
            f"Cover this declared grading focus with concrete evidence, equations, or claims: {item}",
            0.05,
        ))

    if _has_any(problem_text.lower(), ("derive", "show that", "prove", "calculate", "compute", "find the exact", "write down explicitly")):
        requirements.append((
            "derivation completeness",
            "For derivation/calculation tasks, include the intermediate equations, variable definitions, substitutions, and final result instead of only the conclusion.",
            0.0,
        ))
    if _has_any(problem_text.lower(), ("compare", "contrast", "versus", "vs.", "tradeoff", "alternative")):
        requirements.append((
            "comparison completeness",
            "For comparison tasks, state both sides, the comparison criterion, and the resulting conclusion.",
            0.0,
        ))

    return requirements


def _extract_formula_fragments(data: Dict[str, Any]) -> List[str]:
    import re

    context = _as_dict(data.get("context") or {})
    if not isinstance(context, dict):
        context = {}
    text_parts = [
        str(data.get("problem") or ""),
        _stable_json(context.get("equations_and_formulas") or []),
        _stable_json(_as_dict(data.get("axiom_ledger") or {})),
        _stable_json(_as_dict(data.get("proof_plan") or {})),
        _stable_json(_as_dict(data.get("derivations") or [])),
        _stable_json(_as_dict(data.get("task_outputs") or {})),
        _stable_json(_as_dict(data.get("task_graph") or {})),
    ]
    text = "\n".join(text_parts)
    patterns = [
        r"\\\\\[(.+?)\\\\\]",
        r"\\\((.+?)\\\)",
        r"\$\$(.+?)\$\$",
        r"\$(.+?)\$",
    ]
    formulas: List[str] = []
    seen = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.DOTALL):
            formula = " ".join(match.group(1).split())
            while formula.endswith("\\"):
                formula = formula[:-1].rstrip()
            if not _looks_like_formula(formula):
                continue
            key = formula.lower()
            if key not in seen:
                seen.add(key)
                formulas.append(formula[:360])
    return formulas


def _looks_like_formula(value: str) -> bool:
    import re

    if len(value) < 3:
        return False
    if re.search(r"[A-Za-z]'?\([A-Za-z0-9_+\-]+\)", value):
        return True
    math_markers = ("=", "\\", "^", "_", "{", "}", "sum", "frac", "otimes", "langle", "rangle", "sigma", "lambda")
    return any(marker in value for marker in math_markers)


def _extract_enumerated_requirements(problem_text: str) -> List[str]:
    import re

    normalized = _requirement_region(problem_text.replace("\r\n", "\n"))
    matches = []
    patterns = [
        r"(?:^|\n)\s*(\d+)\.\s+(.+?)(?=(?:\n\s*\d+\.\s+)|(?:\n\s*\n)|\Z)",
        r"(?:^|\n)\s*\(([a-zA-Z])\)\s+(.+?)(?=(?:\n\s*\([a-zA-Z]\)\s+)|(?:\n\s*\n)|\Z)",
        r"(?<!\w)\(([a-fA-F])\)\s+(.+?)(?=(?:\s+\([a-fA-F]\)\s+)|\Z)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, normalized, flags=re.DOTALL):
            item = " ".join(match.group(2).split())
            if len(item) >= 20 and not _looks_like_reference_item(item):
                matches.append(item[:420])
    return matches


def _requirement_region(problem_text: str) -> str:
    import re

    lower = problem_text.lower()
    start_markers = (
        "your solution should follow",
        "answer the following",
        "following questions",
        "subquestions:",
        "requirements:",
        "tasks:",
        "question:",
        "problem:",
    )
    candidate_starts = []
    for marker in start_markers:
        start = 0
        while True:
            idx = lower.find(marker, start)
            if idx < 0:
                break
            if re.search(r"(?:^|\n)\s*(?:\d+\.|\([a-zA-Z]\))\s+", problem_text[idx:], flags=re.DOTALL):
                candidate_starts.append(idx)
            start = idx + len(marker)

    region = problem_text[max(candidate_starts):] if candidate_starts else problem_text
    region_lower = region.lower()
    stop_markers = (
        "\nthink step by step",
        "\nplease think",
        "\nbe as detailed as possible",
    )
    stop_positions = [region_lower.find(marker) for marker in stop_markers if region_lower.find(marker) >= 0]
    if stop_positions:
        region = region[: min(stop_positions)]
    return region


def _looks_like_reference_item(item: str) -> bool:
    import re

    lower = item.lower()
    if "\\end{itemize}" in lower:
        return True
    bibliography_markers = (
        "phys. rev.",
        "phys. rep.",
        "arxiv:",
        "doi:",
        "journal",
        "proceedings",
        "conference",
    )
    if any(marker in lower for marker in bibliography_markers):
        return True
    return bool(re.match(r"^[A-Z](?:\.\s*[A-Z])*\.?\s+[^.]+,\s+.*\b(?:19|20)\d{2}\b", item))


def _extract_declared_grading_focus(data: Dict[str, Any]) -> List[str]:
    items: List[str] = []
    context = _as_dict(data.get("context") or {})
    if isinstance(context, dict):
        for key in ("deliverables", "subquestions", "must_have_terms"):
            for value in _listify(context.get(key)):
                text = str(value).strip()
                if text:
                    items.append(text)
    question_intent = _as_dict(data.get("question_intent") or {})
    if isinstance(question_intent, dict):
        for value in _listify(question_intent.get("grading_focus")):
            text = str(value).strip()
            if text:
                items.append(text)
        for sub in _listify(question_intent.get("subquestion_intents")):
            sub = _as_dict(sub)
            if not isinstance(sub, dict):
                continue
            for key in ("question_goal", "required_answer_shape", "answer_scope"):
                text = str(sub.get(key) or "").strip()
                if text:
                    items.append(text)
    task_graph = _as_dict(data.get("task_graph") or {})
    if isinstance(task_graph, dict):
        for task in _listify(task_graph.get("tasks")):
            task = _as_dict(task)
            if not isinstance(task, dict):
                continue
            for key in ("title", "deliverable"):
                text = str(task.get(key) or "").strip()
                if text:
                    items.append(text)
            for value in _listify(task.get("dense_requirements")) + _listify(task.get("micro_checklists")):
                text = str(value).strip()
                if text:
                    items.append(text)
    deduped: List[str] = []
    seen = set()
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(item[:360])
    return deduped


def _add_requirement_pair(
    graph: MemoryGraph,
    idx: int,
    title: str,
    content: str,
    domain: str,
    distractor_risk: float = 0.0,
) -> None:
    obligation = _add_atom(
        graph,
        "obligation",
        f"Rubric formula requirement: {title}",
        source="rubric_requirements",
        source_path=f"rubric_requirements[{idx}].obligation",
        domain=domain,
        support_license="verified",
        role_affinity={"writer": 1.4, "verification": 1.4, "formal_deriver": 1.0, "task_executor": 0.7},
        distractor_risk=distractor_risk,
    )
    constraint = _add_atom(
        graph,
        "constraint",
        f"{title}: {content}",
        source="rubric_requirements",
        source_path=f"rubric_requirements[{idx}].constraint",
        domain=domain,
        support_license="verified",
        obligations=[obligation.id],
        role_affinity={"writer": 1.5, "verification": 1.5, "formal_deriver": 1.2, "task_executor": 0.8},
        distractor_risk=distractor_risk,
    )
    graph.add_edge(constraint.id, obligation.id, "serves_obligation")


def _rubric_text_blob(data: Dict[str, Any]) -> str:
    parts = [
        str(data.get("problem") or ""),
        _stable_json(data.get("context") or {}),
        _stable_json(data.get("question_intent") or {}),
        _stable_json(data.get("task_graph") or {}),
        _stable_json(data.get("axiom_ledger") or {}),
    ]
    return " ".join(parts).lower()


def _has_any(text: str, needles: Iterable[str]) -> bool:
    return any(str(needle).lower() in text for needle in needles)


def _add_question_intent_atoms(graph: MemoryGraph, question_intent: Any, domain: str) -> None:
    question_intent = _as_dict(question_intent)
    if not isinstance(question_intent, dict):
        return

    for field_name in ("global_goal", "scope_limits"):
        value = str(question_intent.get(field_name) or "").strip()
        if value:
            _add_atom(
                graph,
                "obligation" if field_name == "global_goal" else "constraint",
                value,
                source="question_intent",
                source_path=f"question_intent.{field_name}",
                domain=domain,
                support_license="verified",
                role_affinity={"writer": 1.0, "verification": 1.0},
            )

    for idx, text in enumerate(_listify(question_intent.get("forbidden_expansions"))):
        _add_atom(
            graph,
            "constraint",
            f"Forbidden expansion: {text}",
            source="question_intent",
            source_path=f"question_intent.forbidden_expansions[{idx}]",
            domain=domain,
            support_license="verified",
            role_affinity={"writer": 1.0, "verification": 1.0},
            distractor_risk=0.9,
        )

    for sidx, sub in enumerate(_listify(question_intent.get("subquestion_intents"))):
        sub = _as_dict(sub)
        if not isinstance(sub, dict):
            continue
        subquestion = sub.get("subquestion") or sub.get("question_goal") or f"subquestion_{sidx + 1}"
        obligation = _add_atom(
            graph,
            "obligation",
            str(subquestion),
            source="question_intent",
            source_path=f"question_intent.subquestion_intents[{sidx}]",
            domain=domain,
            support_license="verified",
            role_affinity={"writer": 1.0, "verification": 1.0},
        )
        for field_name in ("required_answer_shape", "answer_scope", "question_goal"):
            value = str(sub.get(field_name) or "").strip()
            if not value:
                continue
            atom = _add_atom(
                graph,
                "constraint",
                value,
                source="question_intent",
                source_path=f"question_intent.subquestion_intents[{sidx}].{field_name}",
                domain=domain,
                support_license="verified",
                obligations=[obligation.id],
                role_affinity={"writer": 1.0, "verification": 1.0},
            )
            graph.add_edge(atom.id, obligation.id, "serves_obligation")
        for idx, text in enumerate(_listify(sub.get("do_not_assume"))):
            atom = _add_atom(
                graph,
                "constraint",
                f"Do not assume: {text}",
                source="question_intent",
                source_path=f"question_intent.subquestion_intents[{sidx}].do_not_assume[{idx}]",
                domain=domain,
                support_license="verified",
                obligations=[obligation.id],
                role_affinity={"writer": 1.0, "verification": 1.0},
                distractor_risk=0.9,
            )
            graph.add_edge(atom.id, obligation.id, "serves_obligation")


def _add_constraint_ledger_atoms(graph: MemoryGraph, constraint_ledger: Any, domain: str) -> None:
    ledger = _as_dict(constraint_ledger)
    if not isinstance(ledger, dict):
        return
    for idx, entry in enumerate(_listify(ledger.get("constraints"))):
        entry = _as_dict(entry)
        if not isinstance(entry, dict):
            continue
        text = str(entry.get("text") or "").strip()
        if not text:
            continue
        ctype = str(entry.get("constraint_type") or "deliverable")
        status = str(entry.get("status") or "pending")
        atom_type = "constraint" if ctype == "scope" else "obligation"
        lifecycle = "active" if status in ("pending", "violated", "deferred") else "stale"
        _add_atom(
            graph,
            atom_type,
            text,
            source="constraint_ledger",
            source_path=f"constraint_ledger.constraints[{idx}]",
            domain=domain,
            support_license="verified",
            lifecycle=lifecycle,
            role_affinity={"writer": 1.0, "verification": 1.0, "formal_deriver": 0.8},
        )


def _add_task_graph_atoms(graph: MemoryGraph, task_graph: Any, domain: str) -> None:
    task_graph = _as_dict(task_graph)
    if not isinstance(task_graph, dict):
        return
    for tidx, task in enumerate(_listify(task_graph.get("tasks"))):
        task = _as_dict(task)
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or f"task_{tidx + 1}")
        task_atom = _add_atom(
            graph,
            "task",
            _stable_json(task),
            source="task_graph",
            source_path=f"task_graph.tasks[{task_id}]",
            domain=domain,
            support_license="verified",
            role_affinity={"task_executor": 1.0, "writer": 0.9, "verification": 0.9},
        )
        deliverable = str(task.get("deliverable") or task.get("title") or "").strip()
        if deliverable:
            obligation = _add_atom(
                graph,
                "obligation",
                deliverable,
                source="task_graph",
                source_path=f"task_graph.tasks[{task_id}].deliverable",
                domain=domain,
                support_license="verified",
                role_affinity={"task_executor": 1.0, "writer": 1.0, "verification": 1.0},
            )
            graph.add_edge(task_atom.id, obligation.id, "depends_on")
        for midx, item in enumerate(_listify(task.get("micro_checklists"))):
            obligation = _add_atom(
                graph,
                "obligation",
                str(item),
                source="task_graph",
                source_path=f"task_graph.tasks[{task_id}].micro_checklists[{midx}]",
                domain=domain,
                support_license="verified",
                role_affinity={"task_executor": 1.0, "writer": 1.0, "verification": 1.0},
            )
            graph.add_edge(task_atom.id, obligation.id, "depends_on")


def _add_axiom_atoms(graph: MemoryGraph, axiom_ledger: Any, domain: str) -> None:
    axiom_ledger = _as_dict(axiom_ledger)
    if not isinstance(axiom_ledger, dict):
        return
    hard_fields = (
        "space_type",
        "particle_type",
        "state_hierarchy",
        "formalism",
        "symmetries",
        "boundary_conditions",
        "explicit_protocol_facts",
        "biological_axioms",
        "chemical_axioms",
        "violation_checks",
    )
    for field_name in hard_fields:
        for idx, text in enumerate(_listify(axiom_ledger.get(field_name))):
            if not text:
                continue
            atom_type = "constraint" if field_name in ("violation_checks", "boundary_conditions") else "problem_fact"
            _add_atom(
                graph,
                atom_type,
                str(text),
                source="axiom_ledger",
                source_path=f"axiom_ledger.{field_name}[{idx}]",
                domain=domain,
                support_license="verified",
                role_affinity={"formal_deriver": 1.0, "writer": 0.9, "verification": 1.0},
            )
    for idx, text in enumerate(_listify(axiom_ledger.get("soft_interpretations"))):
        _add_atom(
            graph,
            "claim",
            str(text),
            source="axiom_ledger",
            source_path=f"axiom_ledger.soft_interpretations[{idx}]",
            domain=domain,
            support_license="speculative",
            role_affinity={"hypothesis": 0.9, "verification": 0.8},
            distractor_risk=0.4,
        )


def _add_hypothesis_atoms(graph: MemoryGraph, hypotheses: Any, domain: str) -> None:
    hypotheses = _as_dict(hypotheses)
    if not isinstance(hypotheses, dict):
        return
    for idx, item in enumerate(_listify(hypotheses.get("hypotheses"))):
        item = _as_dict(item)
        if not isinstance(item, dict):
            continue
        statement = str(item.get("statement") or "").strip()
        if not statement:
            continue
        inference_level = str(item.get("inference_level") or "inference").lower()
        support_license = {
            "explicit": "verified",
            "inference": "plausible",
            "speculative": "speculative",
        }.get(inference_level, "plausible")
        claim = _add_atom(
            graph,
            "claim",
            statement,
            source="hypothesis_modeler",
            source_path=f"hypotheses.hypotheses[{idx}]",
            domain=domain,
            support_license=support_license,
            role_affinity={"hypothesis": 1.0, "writer": 0.6, "verification": 0.9},
            distractor_risk=0.5 if support_license == "speculative" else 0.15,
        )
        for eidx, evidence in enumerate(_listify(item.get("evidence_support"))):
            ev = _add_atom(
                graph,
                "evidence",
                str(evidence),
                source="hypothesis_modeler",
                source_path=f"hypotheses.hypotheses[{idx}].evidence_support[{eidx}]",
                domain=domain,
                support_license="verified",
                role_affinity={"writer": 0.9, "verification": 1.0},
            )
            graph.add_edge(ev.id, claim.id, "supports")
        for ridx, rejected in enumerate(_listify(item.get("eliminated_alternatives"))):
            _add_atom(
                graph,
                "claim",
                str(rejected),
                source="hypothesis_modeler",
                source_path=f"hypotheses.hypotheses[{idx}].eliminated_alternatives[{ridx}]",
                domain=domain,
                support_license="prohibited",
                role_affinity={"writer": 0.2, "verification": 1.0},
                distractor_risk=1.0,
            )


def _add_derivation_atoms(graph: MemoryGraph, derivations: Any, domain: str) -> None:
    for idx, item in enumerate(_listify(derivations)):
        item = _as_dict(item)
        if not isinstance(item, dict):
            continue
        body = str(item.get("latex") or item.get("title") or item.get("result") or "").strip()
        if not body:
            continue
        derivation = _add_atom(
            graph,
            "derivation",
            _stable_json(item),
            source="formal_deriver",
            source_path=f"derivations[{idx}]",
            domain=domain,
            support_license="supported",
            role_affinity={"formal_deriver": 1.0, "writer": 1.0, "verification": 1.0},
        )
        result = str(item.get("result") or "").strip()
        if result:
            claim = _add_atom(
                graph,
                "claim",
                result,
                source="formal_deriver",
                source_path=f"derivations[{idx}].result",
                domain=domain,
                support_license="supported",
                supported_by=[derivation.id],
                role_affinity={"writer": 1.0, "verification": 1.0},
            )
            graph.add_edge(derivation.id, claim.id, "supports")
        for aidx, assumption in enumerate(_listify(item.get("assumptions"))):
            dep = _add_atom(
                graph,
                "constraint",
                str(assumption),
                source="formal_deriver",
                source_path=f"derivations[{idx}].assumptions[{aidx}]",
                domain=domain,
                support_license="supported",
                role_affinity={"formal_deriver": 1.0, "writer": 0.8, "verification": 1.0},
            )
            graph.add_edge(derivation.id, dep.id, "depends_on")


def _add_task_output_atoms(graph: MemoryGraph, task_outputs: Any, domain: str) -> None:
    if not isinstance(task_outputs, dict):
        return
    for task_id, output in task_outputs.items():
        if output is None:
            continue
        _add_atom(
            graph,
            "claim",
            _stable_json(output),
            source="task_output",
            source_path=f"task_outputs.{task_id}",
            domain=domain,
            support_license="supported",
            role_affinity={"task_executor": 0.8, "writer": 0.9, "verification": 0.9},
        )


def _add_critic_atoms(graph: MemoryGraph, report: Any, source: str, domain: str) -> None:
    report = _as_dict(report)
    if not isinstance(report, dict):
        return
    for idx, issue in enumerate(_listify(report.get("issues"))):
        issue = _as_dict(issue)
        if not isinstance(issue, dict):
            continue
        message = str(issue.get("message") or issue.get("suggestion") or "").strip()
        if not message:
            continue
        _add_atom(
            graph,
            "critic_finding",
            _stable_json(issue),
            source=source,
            source_path=f"{source}.issues[{idx}]",
            domain=domain,
            support_license="verified",
            role_affinity={"writer": 0.8, "verification": 1.0, "patcher": 1.0},
            distractor_risk=0.2,
        )


def _add_proof_gap_atoms(graph: MemoryGraph, proof_gaps: Any, domain: str) -> None:
    proof_gaps = _as_dict(proof_gaps)
    if not isinstance(proof_gaps, dict):
        return
    for field_name in ("missing_steps", "missing_eqs", "missing_definitions", "generality_issues", "notes"):
        for idx, item in enumerate(_listify(proof_gaps.get(field_name))):
            _add_atom(
                graph,
                "critic_finding",
                f"{field_name}: {item}",
                source="proof_auditor",
                source_path=f"proof_gaps.{field_name}[{idx}]",
                domain=domain,
                support_license="verified",
                role_affinity={"formal_deriver": 1.0, "writer": 0.8, "verification": 1.0},
            )


def _add_atom(
    graph: MemoryGraph,
    atom_type: str,
    content: str,
    source: str,
    source_path: str,
    domain: str,
    support_license: str,
    obligations: Optional[List[str]] = None,
    supported_by: Optional[List[str]] = None,
    lifecycle: str = "active",
    role_affinity: Optional[Dict[str, float]] = None,
    distractor_risk: float = 0.0,
) -> MemoryAtom:
    atom = MemoryAtom(
        id=_make_atom_id(atom_type, source_path, content),
        atom_type=atom_type,
        content=str(content),
        source=source,
        source_path=source_path,
        domain=domain,
        support_license=support_license,
        obligations=obligations or [],
        supported_by=supported_by or [],
        lifecycle=lifecycle,
        role_affinity=role_affinity or {},
        distractor_risk=distractor_risk,
    )
    return graph.add_atom(atom)


def _make_atom_id(atom_type: str, source_path: str, content: Any) -> str:
    payload = f"{atom_type}|{source_path}|{_stable_json(content)}"
    digest = hashlib.sha1(payload.encode("utf-8", errors="ignore")).hexdigest()[:12]
    safe_type = atom_type.replace(" ", "_")
    return f"{safe_type}:{digest}"


def _read_domain(data: Dict[str, Any]) -> str:
    route = _as_dict(data.get("domain_route") or {})
    if isinstance(route, dict):
        return str(route.get("domain") or "unknown")
    return "unknown"


def _as_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _listify(value: Any) -> List[Any]:
    value = _as_dict(value)
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [value]


def _stable_json(value: Any) -> str:
    value = _as_dict(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _normalize_support_license(value: str) -> str:
    value = str(value or "").strip().lower()
    return value if value in SUPPORT_LICENSE_ORDER else "unsupported"


def _license_value(value: str) -> int:
    return SUPPORT_LICENSE_ORDER.get(_normalize_support_license(value), 1)


def _dedupe(items: Iterable[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if item is None:
            continue
        key = str(item)
        if key and key not in seen:
            seen.add(key)
            result.append(key)
    return result
