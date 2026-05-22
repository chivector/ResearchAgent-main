from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciagent.memory_graph import MemoryAtom, MemoryGraph, build_memory_graph_from_dossier, estimate_token_cost
from sciagent.payload_compiler import compile_payload_view, render_payload_view
from sciagent.schemas import ResearchDossier


CaseFactory = Callable[[], Tuple[str, str, Any, Dict[str, Any], Dict[str, Any]]]


def _load_real_problem(dataset_file: Path, problem_id: int) -> str:
    with dataset_file.open(encoding="utf-8") as fp:
        for idx, line in enumerate(fp):
            if idx == problem_id:
                return str(json.loads(line)["problem"])
    raise IndexError(f"Problem id {problem_id} not found in {dataset_file}.")


def _real_problem_writer(dataset_file: Path, problem_id: int) -> CaseFactory:
    def factory() -> Tuple[str, str, Any, Dict[str, Any], Dict[str, Any]]:
        problem = _load_real_problem(dataset_file, problem_id)
        dossier = ResearchDossier(problem=problem, domain_route={"domain": "physics", "confidence": 1.0})
        runtime = {"task_definition": {"id": "writer", "deliverable": "write final answer"}}
        checks = {
            "forbidden_absent": [
                "I'(g) approx eta I(g)",
                "A_w^{(k)}",
                "max_{Psi_f} P_s",
                "P_s^{(n)}",
                "M = <Psi_f|",
                "Phys. Rev.",
                "arXiv:1305",
            ],
            "required_present": ["required answer part", "prompt formula", "derivation completeness"],
            "forbidden_sections": ["archive"],
        }
        return "real_q1_writer", "writer", dossier, runtime, checks

    return factory


def _real_problem_verification(dataset_file: Path, problem_id: int) -> CaseFactory:
    def factory() -> Tuple[str, str, Any, Dict[str, Any], Dict[str, Any]]:
        problem = _load_real_problem(dataset_file, problem_id)
        dossier = ResearchDossier(problem=problem, domain_route={"domain": "physics", "confidence": 1.0})
        runtime = {
            "task_definition": {"id": "verification", "deliverable": "check final answer"},
            "draft": "placeholder draft for payload experiment",
        }
        checks = {
            "required_sections": ["archive"],
            "required_present": ["Question:", "required answer part"],
        }
        return "real_q1_verification", "verification", dossier, runtime, checks

    return factory


def _generic_formula_writer() -> Tuple[str, str, Any, Dict[str, Any], Dict[str, Any]]:
    dossier = ResearchDossier(
        problem=(
            "Question: (a) Define the single particle basis. "
            "(b) Find the exact result for the lattice parameter using "
            "\\(E_0 = 4\\pi^2/(2 M L^2)\\). "
            "(c) Calculate the first excited state and compare degeneracy."
        ),
        domain_route={"domain": "physics", "confidence": 1.0, "evidence_terms": ["lattice"]},
    )
    runtime = {"task_definition": {"id": "writer", "deliverable": "write final answer"}}
    checks = {
        "required_present": [
            "E_0 = 4\\pi^2/(2 M L^2)",
            "required answer part",
            "comparison completeness",
            "derivation completeness",
        ],
        "forbidden_absent": ["weak-value Kraus operator", "A_w^{(k)}"],
    }
    return "generic_formula_writer", "writer", dossier, runtime, checks


def _speculative_filter_writer() -> Tuple[str, str, Any, Dict[str, Any], Dict[str, Any]]:
    dossier = ResearchDossier(
        problem="Question: Compute X and show every required step.",
        domain_route={"domain": "physics", "confidence": 1.0, "evidence_terms": ["X"]},
        context={
            "constraints": ["Use stated units."],
            "deliverables": ["Compute X."],
            "empirical_evidence": ["The prompt states x = 1 m."],
        },
        hypotheses={
            "hypotheses": [{
                "id": "h1",
                "statement": "Speculative external mechanism",
                "inference_level": "speculative",
                "evidence_support": [],
                "answer_relevance": "main",
            }]
        },
    )
    runtime = {"task_definition": {"id": "writer", "deliverable": "write final answer"}}
    checks = {
        "warning_present": ["Speculative external mechanism"],
        "allowed_claim_absent": ["Speculative external mechanism"],
    }
    return "speculative_filter_writer", "writer", dossier, runtime, checks


def _support_repair_writer() -> Tuple[str, str, Any, Dict[str, Any], Dict[str, Any]]:
    graph = MemoryGraph()
    obligation = graph.add_atom(MemoryAtom(
        id="obligation:final_claim",
        atom_type="obligation",
        content="Provide the final supported claim.",
        source="constraint_ledger",
        source_path="constraint_ledger.constraints[0]",
        support_license="verified",
    ))
    support = graph.add_atom(MemoryAtom(
        id="evidence:low_rank_support",
        atom_type="evidence",
        content="Low-ranked but necessary evidence for the final claim.",
        source="context_brief",
        source_path="context.empirical_evidence[0]",
        support_license="verified",
        role_affinity={"writer": -3.0},
    ))
    claim = graph.add_atom(MemoryAtom(
        id="claim:task_support_repair",
        atom_type="claim",
        content="Final supported claim.",
        source="formal_deriver",
        source_path="task_support_repair.result",
        support_license="supported",
        obligations=[obligation.id],
        supported_by=[support.id],
        role_affinity={"writer": 3.0},
    ))
    graph.add_edge(support.id, claim.id, "supports")
    graph.add_edge(claim.id, obligation.id, "serves_obligation")
    for idx in range(40):
        graph.add_atom(MemoryAtom(
            id=f"problem_fact:distractor_{idx}",
            atom_type="problem_fact",
            content=f"High-ranked optional background fact {idx}.",
            source="context_brief",
            source_path=f"context.background[{idx}]",
            support_license="verified",
            role_affinity={"writer": 3.0},
        ))
    runtime = {"task_id": "task_support_repair", "task_definition": {"id": "task_support_repair"}}
    checks = {"required_atom_ids": [support.id], "min_repair_rounds": 1}
    return "support_repair_writer", "writer", graph, runtime, checks


def _dependency_repair_deriver() -> Tuple[str, str, Any, Dict[str, Any], Dict[str, Any]]:
    graph = MemoryGraph()
    dependency = graph.add_atom(MemoryAtom(
        id="problem_fact:unit_dependency",
        atom_type="problem_fact",
        content="x is measured in meters.",
        source="context_brief",
        source_path="context.given_data.x",
        support_license="verified",
        role_affinity={"formal_deriver": -3.0},
    ))
    derivation = graph.add_atom(MemoryAtom(
        id="derivation:task_dependency_repair",
        atom_type="derivation",
        content="X = x, so the unit of X is meters.",
        source="formal_deriver",
        source_path="task_dependency_repair.derivations[0]",
        support_license="supported",
        depends_on=[dependency.id],
        role_affinity={"formal_deriver": 3.0},
    ))
    graph.add_edge(derivation.id, dependency.id, "depends_on")
    for idx in range(36):
        graph.add_atom(MemoryAtom(
            id=f"problem_fact:distractor_{idx}",
            atom_type="problem_fact",
            content=f"High-ranked generic derivation background {idx}.",
            source="context_brief",
            source_path=f"context.background[{idx}]",
            support_license="verified",
            role_affinity={"formal_deriver": 3.0},
        ))
    runtime = {"task_id": "task_dependency_repair", "task_definition": {"id": "task_dependency_repair"}}
    checks = {"required_atom_ids": [dependency.id], "min_repair_rounds": 1}
    return "dependency_repair_deriver", "formal_deriver", graph, runtime, checks


def _critic_signal_writer() -> Tuple[str, str, Any, Dict[str, Any], Dict[str, Any]]:
    graph = MemoryGraph()
    graph.add_atom(MemoryAtom(
        id="obligation:revise_draft",
        atom_type="obligation",
        content="Revise the draft using active critic findings.",
        source="constraint_ledger",
        source_path="constraint_ledger.constraints[0]",
        support_license="verified",
    ))
    critic = graph.add_atom(MemoryAtom(
        id="critic_finding:active_gap",
        atom_type="critic_finding",
        content="Draft omits an important boundary condition.",
        source="proof_auditor",
        source_path="verification.proof_gaps[0]",
        support_license="verified",
        role_affinity={"writer": 0.0},
    ))
    graph.add_atom(MemoryAtom(
        id="constraint:serves_critic",
        atom_type="constraint",
        content="Address the active proof gap before final writing.",
        source="proof_contract",
        source_path="verification.proof_gaps[0].constraint",
        support_license="verified",
        obligations=["obligation:revise_draft"],
        role_affinity={"writer": 0.2},
    ))
    for idx in range(35):
        graph.add_atom(MemoryAtom(
            id=f"problem_fact:critic_distractor_{idx}",
            atom_type="problem_fact",
            content=f"Moderately ranked background detail {idx}.",
            source="context_brief",
            source_path=f"context.background[{idx}]",
            support_license="verified",
            role_affinity={"writer": 0.75},
        ))
    runtime = {"task_definition": {"id": "writer", "deliverable": "revise draft"}, "draft": "short draft"}
    checks = {"required_atom_ids": [critic.id], "required_sections": ["critic_findings"]}
    return "critic_signal_writer", "writer", graph, runtime, checks


def _writer_material_sufficiency() -> Tuple[str, str, Any, Dict[str, Any], Dict[str, Any]]:
    graph = MemoryGraph()
    material = graph.add_atom(MemoryAtom(
        id="claim:prior_task_output",
        atom_type="claim",
        content="Prior task derived the final usable result.",
        source="task_output",
        source_path="task_outputs.task_1",
        support_license="supported",
        role_affinity={"writer": -5.0},
    ))
    for idx in range(40):
        graph.add_atom(MemoryAtom(
            id=f"problem_fact:material_distractor_{idx}",
            atom_type="problem_fact",
            content=f"High-ranked background detail {idx}.",
            source="context_brief",
            source_path=f"context.background[{idx}]",
            support_license="verified",
            role_affinity={"writer": 3.0},
        ))
    runtime = {"task_definition": {"id": "writer", "deliverable": "write from prior task outputs"}}
    checks = {"required_atom_ids": [material.id], "required_sections": ["dependent_outputs"], "min_repair_rounds": 1}
    return "writer_material_sufficiency", "writer", graph, runtime, checks


def _verification_risk_visibility() -> Tuple[str, str, Any, Dict[str, Any], Dict[str, Any]]:
    graph = MemoryGraph()
    graph.add_atom(MemoryAtom(
        id="claim:unsupported_risk",
        atom_type="claim",
        content="Unsupported risky claim should be visible to verification.",
        source="task_output",
        source_path="task_outputs.writer.claims[0]",
        support_license="unsupported",
        role_affinity={"verification": 1.0},
    ))
    graph.add_atom(MemoryAtom(
        id="claim:prohibited_risk",
        atom_type="claim",
        content="Prohibited claim should be visible only as a warning.",
        source="verification",
        source_path="verification.rejected_claims[0]",
        support_license="prohibited",
        role_affinity={"verification": 1.0},
    ))
    runtime = {"task_definition": {"id": "verification", "deliverable": "check risky claims"}, "draft": "short draft"}
    checks = {
        "required_present": ["Unsupported risky claim"],
        "warning_present": ["Prohibited claim"],
        "forbidden_normal_present": ["Prohibited claim"],
    }
    return "verification_risk_visibility", "verification", graph, runtime, checks


def _fail_soft_uncovered_obligation() -> Tuple[str, str, Any, Dict[str, Any], Dict[str, Any]]:
    graph = MemoryGraph()
    graph.add_atom(MemoryAtom(
        id="obligation:uncovered",
        atom_type="obligation",
        content="Explain an obligation that has no serving atom.",
        source="constraint_ledger",
        source_path="constraint_ledger.constraints[0]",
        support_license="verified",
    ))
    graph.add_atom(MemoryAtom(
        id="problem_fact:irrelevant",
        atom_type="problem_fact",
        content="Irrelevant background fact that does not cover the obligation.",
        source="context_brief",
        source_path="context.background[0]",
        support_license="verified",
        role_affinity={"writer": 2.0},
    ))
    runtime = {"task_definition": {"id": "writer", "deliverable": "write final answer"}}
    checks = {
        "expected_verified": False,
        "expected_candidate": "broad_fallback",
        "expected_gap_types": ["missing_obligation_coverage"],
    }
    return "fail_soft_uncovered_obligation", "writer", graph, runtime, checks


def _graph_from_source(source: Any) -> MemoryGraph:
    if isinstance(source, MemoryGraph):
        return source
    return build_memory_graph_from_dossier(source)


def _full_graph_baseline(graph: MemoryGraph, role: str, runtime_inputs: Dict[str, Any]) -> str:
    atoms = [
        atom.to_dict()
        for atom in graph.atoms.values()
        if atom.lifecycle == "active" or role == "verification"
    ]
    return json.dumps(
        {"role": role, "all_graph_atoms": atoms, "runtime_inputs": runtime_inputs},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _evaluate_checks(view: Any, rendered: str, checks: Dict[str, Any]) -> Tuple[bool, Dict[str, bool]]:
    outcomes: Dict[str, bool] = {}
    for text in checks.get("required_present", []):
        outcomes[f"present::{text[:40]}"] = text in rendered
    for text in checks.get("forbidden_absent", []):
        outcomes[f"absent::{text[:40]}"] = text not in rendered
    for section in checks.get("required_sections", []):
        outcomes[f"section::{section}"] = bool(view.sections.get(section))
    for section in checks.get("forbidden_sections", []):
        outcomes[f"no_section::{section}"] = not bool(view.sections.get(section))
    for atom_id in checks.get("required_atom_ids", []):
        outcomes[f"atom::{atom_id}"] = atom_id in view.atom_ids
    expected_verified = checks.get("expected_verified")
    if expected_verified is not None:
        outcomes[f"verified_is::{expected_verified}"] = bool(view.payload_verified) is bool(expected_verified)
    expected_candidate = checks.get("expected_candidate")
    if expected_candidate:
        outcomes[f"candidate::{expected_candidate}"] = view.candidate_name == expected_candidate
    for gap_type in checks.get("expected_gap_types", []):
        outcomes[f"gap::{gap_type}"] = any(gap.get("gap_type") == gap_type for gap in view.gaps)
    min_repairs = checks.get("min_repair_rounds")
    if min_repairs is not None:
        outcomes[f"repair_rounds>={min_repairs}"] = int(view.repair_rounds or 0) >= int(min_repairs)
    allowed_claim_absent = checks.get("allowed_claim_absent", [])
    if allowed_claim_absent:
        allowed_text = "\n".join(atom.get("content", "") for atom in view.sections.get("allowed_claims", []))
        for text in allowed_claim_absent:
            outcomes[f"allowed_absent::{text[:40]}"] = text not in allowed_text
    warning_present = checks.get("warning_present", [])
    if warning_present:
        warning_text = "\n".join(atom.get("content", "") for atom in view.sections.get("warnings", []))
        for text in warning_present:
            outcomes[f"warning_present::{text[:40]}"] = text in warning_text
    normal_absent = checks.get("forbidden_normal_present", [])
    if normal_absent:
        normal_sections = ("task_contract", "problem_kernel", "evidence", "allowed_claims", "derivations", "dependent_outputs")
        normal_text = "\n".join(
            atom.get("content", "")
            for section in normal_sections
            for atom in view.sections.get(section, [])
        )
        for text in normal_absent:
            outcomes[f"normal_absent::{text[:40]}"] = text not in normal_text
    return all(outcomes.values()) if outcomes else True, outcomes


def _run_case(name: str, role: str, source: Any, runtime_inputs: Dict[str, Any], checks: Dict[str, Any]) -> Dict[str, Any]:
    graph = _graph_from_source(source)
    view = compile_payload_view(graph, role=role, runtime_inputs=runtime_inputs)
    rendered = render_payload_view(view)
    baseline = _full_graph_baseline(graph, role, runtime_inputs)
    rendered_tokens = estimate_token_cost(rendered)
    baseline_tokens = estimate_token_cost(baseline)
    checks_passed, check_details = _evaluate_checks(view, rendered, checks)
    rubric_atoms = [atom for atom in graph.atoms.values() if atom.source == "rubric_requirements"]
    return {
        "case": name,
        "role": role,
        "candidate": view.candidate_name,
        "payload_verified": view.payload_verified,
        "repair_rounds": view.repair_rounds,
        "selected_atom_count": len(view.atom_ids),
        "graph_atom_count": len(graph.atoms),
        "rubric_atom_count": len(rubric_atoms),
        "rendered_token_cost": rendered_tokens,
        "full_graph_token_cost": baseline_tokens,
        "token_savings": baseline_tokens - rendered_tokens,
        "token_savings_ratio": round((baseline_tokens - rendered_tokens) / baseline_tokens, 4) if baseline_tokens else 0.0,
        "gap_count": len(view.gaps),
        "gaps": view.gaps,
        "checks_passed": checks_passed,
        "check_details": check_details,
        "sections": sorted(view.sections.keys()),
        "candidate_history": view.candidate_history,
        "selected_view_kind": "repaired_minimal" if view.candidate_name == "minimal" and view.repair_rounds else view.candidate_name,
    }


def _write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fieldnames = [
        "case",
        "role",
        "candidate",
        "payload_verified",
        "repair_rounds",
        "selected_atom_count",
        "graph_atom_count",
        "rubric_atom_count",
        "rendered_token_cost",
        "full_graph_token_cost",
        "token_savings",
        "token_savings_ratio",
        "gap_count",
        "checks_passed",
        "selected_view_kind",
        "sections",
    ]
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            csv_row = dict(row)
            csv_row["sections"] = ",".join(row["sections"])
            writer.writerow({key: csv_row.get(key, "") for key in fieldnames})


def _case_label(case_name: str) -> str:
    aliases = {
        "real_q1_writer": "Real Q1\nwriter",
        "real_q1_verification": "Real Q1\nverify",
        "generic_formula_writer": "Generic\nformula",
        "speculative_filter_writer": "Speculative\nfilter",
        "support_repair_writer": "Support\nrepair",
        "dependency_repair_deriver": "Dependency\nrepair",
        "critic_signal_writer": "Critic\nsignal",
        "writer_material_sufficiency": "Writer\nmaterial",
        "verification_risk_visibility": "Risk\nvisibility",
        "fail_soft_uncovered_obligation": "Fail-soft\nobligation",
    }
    return aliases.get(case_name, case_name.replace("_", "\n"))


def _check_pass_rate(row: Dict[str, Any]) -> float:
    details = row.get("check_details") or {}
    if not details:
        return 1.0
    return sum(1 for value in details.values() if value) / len(details)


def _save_token_cost_chart(path: Path, rows: List[Dict[str, Any]]) -> None:
    labels = [_case_label(row["case"]) for row in rows]
    full = [row["full_graph_token_cost"] for row in rows]
    rendered = [row["rendered_token_cost"] for row in rows]
    x = list(range(len(rows)))
    width = 0.38

    fig, ax = plt.subplots(figsize=(12, 5.8))
    ax.bar([idx - width / 2 for idx in x], full, width, label="Full-graph baseline", color="#9aa6b2")
    ax.bar([idx + width / 2 for idx in x], rendered, width, label="PayloadView", color="#2f6f9f")
    for idx, row in enumerate(rows):
        ymax = max(full[idx], rendered[idx])
        ax.text(idx, ymax * 1.03, f"-{row['token_savings_ratio']:.0%}", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x, labels, fontsize=8)
    ax.set_ylabel("Estimated tokens")
    ax.set_title("PayloadView Reduces Tokens Per Case")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_preservation_chart(path: Path, rows: List[Dict[str, Any]]) -> None:
    labels = [_case_label(row["case"]) for row in rows]
    rates = [_check_pass_rate(row) * 100 for row in rows]
    colors = ["#3f8f70" if row["checks_passed"] else "#d35f5f" for row in rows]

    fig, ax = plt.subplots(figsize=(12, 4.8))
    bars = ax.bar(labels, rates, color=colors)
    ax.axhline(100, color="#333333", linewidth=0.8, alpha=0.35)
    ax.set_ylim(0, 108)
    ax.set_ylabel("Behavior checks passed (%)")
    ax.set_title("Required Payload Behaviors Preserved After Compression")
    ax.grid(axis="y", alpha=0.25)
    for bar, row in zip(bars, rows):
        details = row.get("check_details") or {}
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            min(bar.get_height() + 2, 105),
            f"{sum(1 for value in details.values() if value)}/{len(details) or 1}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_atom_selection_chart(path: Path, rows: List[Dict[str, Any]]) -> None:
    labels = [_case_label(row["case"]) for row in rows]
    selected = [row["selected_atom_count"] for row in rows]
    graph = [row["graph_atom_count"] for row in rows]
    x = list(range(len(rows)))
    width = 0.38

    fig, ax = plt.subplots(figsize=(12, 5.5))
    ax.bar([idx - width / 2 for idx in x], graph, width, label="Graph atoms", color="#b8b2a7")
    ax.bar([idx + width / 2 for idx in x], selected, width, label="Selected atoms", color="#3f8f70")
    for idx, row in enumerate(rows):
        ratio = row["selected_atom_count"] / row["graph_atom_count"] if row["graph_atom_count"] else 0
        ax.text(idx, max(graph[idx], selected[idx]) + 1, f"{ratio:.0%}", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x, labels, fontsize=8)
    ax.set_ylabel("Atom count")
    ax.set_title("PayloadView Keeps a Targeted Subset of the Memory Graph")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_candidate_outcome_chart(path: Path, rows: List[Dict[str, Any]]) -> None:
    kind_counts = Counter(row["selected_view_kind"] for row in rows)
    verified = sum(1 for row in rows if row["payload_verified"])
    fail_soft = len(rows) - verified
    repair_rounds = [row["repair_rounds"] for row in rows]
    labels = [_case_label(row["case"]) for row in rows]

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    kinds = list(kind_counts)
    axes[0].bar(kinds, [kind_counts[kind] for kind in kinds], color=["#2f6f9f", "#6d70b8", "#ba7a2f"][:len(kinds)])
    axes[0].set_title("Selected View Types")
    axes[0].set_ylabel("Count")
    axes[0].grid(axis="y", alpha=0.25)

    axes[1].pie(
        [verified, fail_soft],
        labels=["Verified", "Fail-soft"],
        autopct="%1.0f%%",
        startangle=90,
        colors=["#3f8f70", "#d35f5f"],
    )
    axes[1].set_title("Verifier Outcome")

    axes[2].bar(labels, repair_rounds, color="#8d4d9d")
    axes[2].set_title("Repair Rounds")
    axes[2].set_ylabel("Rounds")
    axes[2].tick_params(axis="x", labelsize=8)
    axes[2].grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_savings_preservation_scatter(path: Path, rows: List[Dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    for row in rows:
        x = row["token_savings_ratio"] * 100
        y = _check_pass_rate(row) * 100
        size = 45 + row["selected_atom_count"] * 4
        color = "#d35f5f" if not row["payload_verified"] else "#2f6f9f"
        ax.scatter(x, y, s=size, color=color, alpha=0.78, edgecolor="white", linewidth=0.8)
        ax.text(x + 0.5, y - 0.8, row["case"].replace("_", " "), fontsize=8)
    ax.set_xlim(55, 96)
    ax.set_ylim(92, 102)
    ax.set_xlabel("Token savings vs full-graph baseline (%)")
    ax.set_ylabel("Behavior checks preserved (%)")
    ax.set_title("Compression Preserves Required Payload Behaviors")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _write_charts(output_dir: Path, rows: List[Dict[str, Any]]) -> List[Path]:
    charts = [
        output_dir / "01_token_cost_by_case.png",
        output_dir / "02_behavior_preservation.png",
        output_dir / "03_selected_atoms_vs_graph.png",
        output_dir / "04_candidate_repair_outcome.png",
        output_dir / "05_savings_vs_preservation.png",
    ]
    _save_token_cost_chart(charts[0], rows)
    _save_preservation_chart(charts[1], rows)
    _save_atom_selection_chart(charts[2], rows)
    _save_candidate_outcome_chart(charts[3], rows)
    _save_savings_preservation_scatter(charts[4], rows)
    return charts


def _write_markdown(path: Path, rows: List[Dict[str, Any]], charts: List[Path]) -> None:
    total_rendered = sum(row["rendered_token_cost"] for row in rows)
    total_full = sum(row["full_graph_token_cost"] for row in rows)
    verified = sum(1 for row in rows if row["payload_verified"])
    checks = sum(1 for row in rows if row["checks_passed"])
    minimal_count = sum(1 for row in rows if row["candidate"] == "minimal")
    repaired_minimal_count = sum(1 for row in rows if row["selected_view_kind"] == "repaired_minimal")
    fail_soft_count = sum(1 for row in rows if not row["payload_verified"])
    lines = [
        "# Payload Compiler Offline Experiment",
        "",
        "This experiment does not call any model. It compares the current PayloadView renderer with a full-graph payload baseline and checks generic compiler behavior.",
        "",
        "## Summary",
        "",
        f"- cases: {len(rows)}",
        f"- payload verified: {verified}/{len(rows)}",
        f"- fail-soft views: {fail_soft_count}/{len(rows)}",
        f"- behavior checks passed: {checks}/{len(rows)}",
        f"- selected minimal views: {minimal_count}/{len(rows)}",
        f"- repaired minimal views: {repaired_minimal_count}/{len(rows)}",
        f"- rendered tokens: {total_rendered}",
        f"- full-graph baseline tokens: {total_full}",
        f"- token savings: {total_full - total_rendered} ({((total_full - total_rendered) / total_full):.1%})" if total_full else "- token savings: n/a",
        "",
        "## Charts",
        "",
    ]
    for chart in charts:
        lines.append(f"- [{chart.name}]({chart.name})")
    lines.extend([
        "",
        "## Case Metrics",
        "",
        "| Case | Role | Candidate | Repairs | Verified | Checks | Rendered | Full Graph | Savings | Atoms | Notes |",
        "| --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ])
    for row in rows:
        savings_pct = f"{row['token_savings_ratio']:.1%}"
        notes = []
        if row["repair_rounds"]:
            notes.append("verifier repaired graph gaps")
        if row["candidate"] == "minimal":
            notes.append("smallest passing view" if not row["repair_rounds"] else "smallest repaired view")
        if row["role"] == "verification" and "archive" in row["sections"]:
            notes.append("verification sees archive")
        if not row["payload_verified"]:
            notes.append("fail-soft fallback with gaps")
        lines.append(
            f"| {row['case']} | {row['role']} | {row['candidate']} | {row['repair_rounds']} | "
            f"{row['payload_verified']} | {row['checks_passed']} | {row['rendered_token_cost']} | "
            f"{row['full_graph_token_cost']} | {savings_pct} | "
            f"{row['selected_atom_count']}/{row['graph_atom_count']} | {'; '.join(notes)} |"
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- Token savings are expected: the renderer only emits selected atoms and compact runtime inputs, while the baseline dumps all active graph atoms with metadata.",
        "- `verification` compresses less than `writer` because it is allowed to see the full archive/problem for contamination and omission checks.",
        "- Most selected candidates are `minimal` by design. A selected `minimal` can still be verifier-repaired; support/dependency cases are repaired minimal views, not unvalidated seeds.",
        "- The support/dependency/writer-material repair cases show that the graph verifier can add low-ranked but required support, dependency, or prior-output atoms without jumping to broad fallback.",
        "- The writer-material case targets under-informed minimal views: if writable prior task output exists in the graph, writer must receive at least one such material atom.",
        "- The critic-signal case checks that active critic/proof-gap state changes optional atom ranking enough for writer to receive critic findings.",
        "- The fail-soft case is intentionally not verified. It confirms the pipeline keeps a broad fallback report with a concrete gap instead of silently passing an uncovered obligation.",
        "",
        "## Limitations",
        "",
        "- This is a payload compiler experiment, not an answer-quality experiment; it does not call an LLM and cannot measure final correctness.",
        "- The full-graph baseline is intentionally conservative and metadata-heavy. For exact historical cost comparison, use an end-to-end run with `legacy_token_cost` in the payload report.",
        "- Current checks are deterministic proxies for expected compiler behavior. They should be paired with at least one API end-to-end run before claiming accuracy impact.",
        "",
        "## Behavior Checks",
        "",
    ])
    for row in rows:
        lines.append(f"### {row['case']}")
        for key, value in row["check_details"].items():
            lines.append(f"- {key}: {value}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline PayloadView compiler experiments.")
    parser.add_argument("--dataset-file", default="test.jsonl")
    parser.add_argument("--problem-id", type=int, default=0)
    parser.add_argument("--output-dir", default="outputs/payload_compiler_experiment")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_file = Path(args.dataset_file)
    factories: List[CaseFactory] = [
        _real_problem_writer(dataset_file, args.problem_id),
        _real_problem_verification(dataset_file, args.problem_id),
        _generic_formula_writer,
        _speculative_filter_writer,
        _support_repair_writer,
        _dependency_repair_deriver,
        _critic_signal_writer,
        _writer_material_sufficiency,
        _verification_risk_visibility,
        _fail_soft_uncovered_obligation,
    ]
    rows = [_run_case(*factory()) for factory in factories]

    metrics_path = output_dir / "metrics.csv"
    report_path = output_dir / "report.md"
    json_path = output_dir / "results.json"
    charts = _write_charts(output_dir, rows)
    _write_csv(metrics_path, rows)
    _write_markdown(report_path, rows, charts)
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "output_dir": str(output_dir),
        "report": str(report_path),
        "metrics": str(metrics_path),
        "results": str(json_path),
        "charts": [str(chart) for chart in charts],
        "verified": f"{sum(1 for row in rows if row['payload_verified'])}/{len(rows)}",
        "checks_passed": f"{sum(1 for row in rows if row['checks_passed'])}/{len(rows)}",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
