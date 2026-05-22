from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sciagent.memory_graph import MemoryAtom, MemoryGraph, build_memory_graph_from_dossier
from sciagent.payload_compiler import (
    PayloadView,
    _repair_until_verified,
    compile_payload_view,
    render_payload_view,
    verify_payload_view,
)
from sciagent.schemas import ResearchDossier


class PayloadCompilerTests(unittest.TestCase):

    def _formula_rich_dossier(self) -> ResearchDossier:
        return ResearchDossier(
            problem=(
                "Question: Large weak values can enhance sensitivity but require low postselection "
                "probabilities. Define the visible weak value formula "
                "\\(A_w = \\langle \\Psi_f|A|\\Psi_i\\rangle / \\langle \\Psi_f|\\Psi_i\\rangle\\). "
                "Then compare the explicitly provided Fisher information symbols \\(I(g)\\) and \\(I'(g)\\)."
            ),
            domain_route={"domain": "physics", "confidence": 1.0, "evidence_terms": ["weak value"]},
        )

    def _dummy_dossier(self) -> ResearchDossier:
        return ResearchDossier(
            problem="Compute X and show every required step.",
            domain_route={"domain": "physics", "confidence": 1.0, "evidence_terms": ["X"]},
            context={
                "key_terms": ["X"],
                "entities": ["X"],
                "given_data": {"x": "1 m"},
                "assumptions_in_text": [],
                "constraints": ["Use stated units."],
                "deliverables": ["Compute X."],
                "subquestions": ["What is X?"],
                "negative_constraints": [],
                "core_conflicts": [],
                "empirical_evidence": ["The prompt states x = 1 m."],
                "evidence_mapping": {"main": "The prompt states x = 1 m."},
                "must_have_terms": ["X"],
                "unchanged_features": [],
                "phenotype_summary": {"viability": "unknown", "morphology": [], "notes": []},
            },
            constraint_ledger={
                "constraints": [{
                    "id": "c_1",
                    "constraint_type": "format",
                    "text": "show all steps",
                    "source": "problem_text",
                    "keywords": ["step"],
                    "verification_strategy": "section_presence",
                    "satisfied_by": [],
                    "status": "pending",
                }],
                "last_validated_at": "extraction",
            },
            task_graph={
                "tasks": [{
                    "id": "task_1",
                    "title": "derive X",
                    "task_type": "derive",
                    "inputs": [],
                    "deliverable": "Derive X.",
                    "micro_checklists": ["Define x", "Show arithmetic"],
                    "depends_on": [],
                    "roles": ["formal_deriver"],
                }],
                "notes": [],
            },
            hypotheses={
                "hypotheses": [{
                    "id": "h1",
                    "statement": "Speculative external mechanism",
                    "inference_level": "speculative",
                    "evidence_support": [],
                    "answer_relevance": "main",
                }],
                "notes": [],
            },
        )

    def test_constraints_and_micro_checklists_generate_obligation_atoms(self) -> None:
        graph = build_memory_graph_from_dossier(self._dummy_dossier())
        obligation_text = [atom.content for atom in graph.atoms.values() if atom.atom_type == "obligation"]

        self.assertTrue(any("show all steps" in text for text in obligation_text))
        self.assertIn("Define x", obligation_text)
        self.assertIn("Show arithmetic", obligation_text)

    def test_visible_prompt_formulas_generate_rubric_atoms_without_answer_leakage(self) -> None:
        graph = build_memory_graph_from_dossier(self._formula_rich_dossier())
        rubric_atoms = [atom for atom in graph.atoms.values() if atom.source == "rubric_requirements"]
        rubric_text = "\n".join(atom.content for atom in rubric_atoms)

        self.assertGreaterEqual(len(rubric_atoms), 4)
        self.assertIn("A_w = \\langle \\Psi_f|A|\\Psi_i\\rangle", rubric_text)
        self.assertIn("I(g)", rubric_text)
        self.assertIn("I'(g)", rubric_text)
        self.assertNotIn("max_{Psi_f} P_s approx Var(A)", rubric_text)
        self.assertNotIn("A_w^{(k)}", rubric_text)
        self.assertNotIn("I'(g) approx eta I(g)", rubric_text)

    def test_writer_payload_includes_visible_formula_constraints(self) -> None:
        graph = build_memory_graph_from_dossier(self._formula_rich_dossier())
        view = compile_payload_view(graph, role="writer", runtime_inputs={"task_definition": {"id": "writer"}})
        rendered = render_payload_view(view)

        self.assertTrue(view.payload_verified)
        self.assertTrue(any(atom_id.startswith("constraint:") for atom_id in view.atom_ids))
        self.assertIn("Rubric formula requirement", rendered)
        self.assertIn("A_w = \\langle \\Psi_f|A|\\Psi_i\\rangle", rendered)
        self.assertIn("I'(g)", rendered)
        self.assertNotIn("I'(g) approx eta I(g)", rendered)
        self.assertNotIn("A_w^{(k)}", rendered)

    def test_generated_derivation_formulas_can_become_rubric_atoms(self) -> None:
        dossier = ResearchDossier(
            problem="Question: Use the derived relation to compute the result.",
            domain_route={"domain": "physics", "confidence": 1.0, "evidence_terms": ["energy"]},
            derivations=[{
                "id": "d1",
                "title": "Mass energy relation",
                "latex": "\\(E = mc^2\\)",
                "result": "Energy is proportional to mass.",
            }],
        )
        graph = build_memory_graph_from_dossier(dossier)
        rubric_text = "\n".join(atom.content for atom in graph.atoms.values() if atom.source == "rubric_requirements")

        self.assertIn("E = mc^2", rubric_text)

    def test_generic_formula_requirements_are_not_weak_value_specific(self) -> None:
        dossier = ResearchDossier(
            problem=(
                "Question: (a) Define the single particle basis. "
                "(b) Find the exact result for the lattice parameter using "
                "\\(E_0 = 4\\pi^2/(2 M L^2)\\). "
                "(c) Calculate the first excited state and compare degeneracy."
            ),
            domain_route={"domain": "physics", "confidence": 1.0, "evidence_terms": ["lattice"]},
        )
        graph = build_memory_graph_from_dossier(dossier)
        rubric_atoms = [atom for atom in graph.atoms.values() if atom.source == "rubric_requirements"]
        rubric_text = "\n".join(atom.content for atom in rubric_atoms)
        view = compile_payload_view(graph, role="writer", runtime_inputs={"task_definition": {"id": "writer"}})
        rendered = render_payload_view(view)

        self.assertIn("prompt formula", rubric_text)
        self.assertIn("required answer part", rubric_text)
        self.assertIn("derivation completeness", rubric_text)
        self.assertIn("comparison completeness", rubric_text)
        self.assertNotIn("weak-value Kraus operator", rubric_text)
        self.assertTrue(view.payload_verified)
        self.assertIn("E_0 = 4\\pi^2/(2 M L^2)", rendered)

    def test_writer_keeps_speculative_claim_out_of_allowed_claims(self) -> None:
        graph = build_memory_graph_from_dossier(self._dummy_dossier())
        view = compile_payload_view(graph, role="writer", runtime_inputs={"draft_goal": "write"})
        allowed = view.sections.get("allowed_claims", [])
        warnings = view.sections.get("warnings", [])

        self.assertFalse(any("Speculative external mechanism" in atom["content"] for atom in allowed))
        self.assertTrue(any("Speculative external mechanism" in atom["content"] for atom in warnings))

    def test_compact_renderer_omits_debug_report_and_atom_metadata(self) -> None:
        graph = build_memory_graph_from_dossier(self._dummy_dossier())
        view = compile_payload_view(
            graph,
            role="writer",
            runtime_inputs={
                "task_definition": {"id": "writer", "deliverable": "Compute X and show every required step."},
                "mandatory_checklist": ["Define x", "Show arithmetic"],
                "problem": "This full prompt should not be repeated in compact runtime inputs.",
                "constraint_ledger": {"debug": "metadata-heavy input"},
            },
        )
        rendered = render_payload_view(view)

        self.assertIn("COMPILED_PAYLOAD_VIEW:", rendered)
        self.assertNotIn("PAYLOAD_VIEW_REPORT", rendered)
        self.assertNotIn('"source":', rendered)
        self.assertNotIn("support_license", rendered)
        self.assertNotIn("source_path", rendered)
        self.assertNotIn("This full prompt should not be repeated", rendered)

    def test_derive_view_includes_dependency_closure(self) -> None:
        graph = MemoryGraph()
        dep = MemoryAtom(
            id="evidence:unit",
            atom_type="evidence",
            content="x is measured in meters.",
            source="problem_text",
            source_path="context.empirical_evidence[0]",
            support_license="verified",
        )
        derivation = MemoryAtom(
            id="derivation:x",
            atom_type="derivation",
            content="X = x",
            source="formal_deriver",
            source_path="derivations[0]",
            support_license="supported",
            depends_on=[dep.id],
        )
        graph.add_atom(dep)
        graph.add_atom(derivation)

        view = compile_payload_view(graph, role="formal_deriver", task={"id": "task_1"}, runtime_inputs={})

        self.assertTrue(view.payload_verified)
        self.assertIn(dep.id, view.atom_ids)

    def test_writer_view_includes_support_closure(self) -> None:
        graph = MemoryGraph()
        support = MemoryAtom(
            id="evidence:support",
            atom_type="evidence",
            content="Observed evidence.",
            source="problem_text",
            source_path="context.empirical_evidence[0]",
            support_license="verified",
        )
        claim = MemoryAtom(
            id="claim:supported",
            atom_type="claim",
            content="Final supported claim.",
            source="formal_deriver",
            source_path="derivations[0].result",
            support_license="supported",
            supported_by=[support.id],
        )
        graph.add_atom(support)
        graph.add_atom(claim)

        view = compile_payload_view(graph, role="writer", runtime_inputs={})

        self.assertTrue(view.payload_verified)
        self.assertIn(support.id, view.atom_ids)

    def test_dependency_and_support_gaps_trigger_repair_loop(self) -> None:
        graph = MemoryGraph()
        support = MemoryAtom(
            id="evidence:support",
            atom_type="evidence",
            content="Observed evidence.",
            source="problem_text",
            source_path="context.empirical_evidence[0]",
            support_license="verified",
        )
        claim = MemoryAtom(
            id="claim:supported",
            atom_type="claim",
            content="Final supported claim.",
            source="formal_deriver",
            source_path="derivations[0].result",
            support_license="supported",
            supported_by=[support.id],
        )
        dep = MemoryAtom(
            id="constraint:unit",
            atom_type="constraint",
            content="Use SI units.",
            source="axiom_ledger",
            source_path="axiom_ledger.boundary_conditions[0]",
            support_license="verified",
        )
        derivation = MemoryAtom(
            id="derivation:x",
            atom_type="derivation",
            content="X = x",
            source="formal_deriver",
            source_path="derivations[0]",
            support_license="supported",
            depends_on=[dep.id],
        )
        for atom in (support, claim, dep, derivation):
            graph.add_atom(atom)

        view, verification, rounds, repairs = _repair_until_verified(
            graph=graph,
            role="writer",
            task_id="writer",
            candidate_name="minimal",
            selected={claim.id, derivation.id},
            runtime_inputs={},
            max_repair_rounds=3,
        )

        self.assertTrue(verification.passed)
        self.assertGreaterEqual(rounds, 1)
        self.assertIn(support.id, view.atom_ids)
        self.assertIn(dep.id, view.atom_ids)
        self.assertTrue(repairs)

    def test_proof_gap_state_boost_selects_relevant_critic_finding(self) -> None:
        graph = MemoryGraph()
        graph.add_atom(MemoryAtom(
            id="fact:x",
            atom_type="problem_fact",
            content="x is the target variable.",
            source="context_brief",
            source_path="context.given_data",
            support_license="verified",
            role_affinity={"formal_deriver": 0.2},
        ))
        graph.add_atom(MemoryAtom(
            id="critic:proof-gap",
            atom_type="critic_finding",
            content="missing_definitions: define x before deriving X.",
            source="proof_auditor",
            source_path="proof_gaps.missing_definitions[0]",
            support_license="verified",
            role_affinity={"formal_deriver": 0.1},
        ))

        view = compile_payload_view(
            graph,
            role="formal_deriver",
            task={"id": "task_1", "task_type": "derive", "deliverable": "derive X"},
            runtime_inputs={},
        )

        critic_contents = [atom["content"] for atom in view.sections.get("critic_findings", [])]
        self.assertTrue(any("define x" in content for content in critic_contents))

    def test_writer_material_sufficiency_repairs_under_informed_minimal(self) -> None:
        graph = MemoryGraph()
        material = MemoryAtom(
            id="claim:prior_task_output",
            atom_type="claim",
            content="Prior task derived the final usable result.",
            source="task_output",
            source_path="task_outputs.task_1",
            support_license="supported",
            role_affinity={"writer": -5.0},
        )
        graph.add_atom(material)
        for idx in range(40):
            graph.add_atom(MemoryAtom(
                id=f"problem_fact:background_{idx}",
                atom_type="problem_fact",
                content=f"High ranked background detail {idx}.",
                source="context_brief",
                source_path=f"context.background[{idx}]",
                support_license="verified",
                role_affinity={"writer": 3.0},
            ))

        view = compile_payload_view(graph, role="writer", runtime_inputs={"task_definition": {"id": "writer"}})

        self.assertTrue(view.payload_verified)
        self.assertGreaterEqual(view.repair_rounds, 1)
        self.assertIn(material.id, view.atom_ids)
        self.assertTrue(view.sections.get("dependent_outputs"))

    def test_obligation_self_coverage_does_not_pass_verifier(self) -> None:
        obligation = {
            "id": "obligation:orphan",
            "atom_type": "obligation",
            "content": "Compute X.",
            "source": "constraint_ledger",
            "source_path": "constraint_ledger.constraints[0]",
            "domain": "physics",
            "support_license": "verified",
            "obligations": [],
            "depends_on": [],
            "supports": [],
            "supported_by": [],
            "prohibits": [],
            "conflicts": [],
            "lifecycle": "active",
            "role_affinity": {},
            "distractor_risk": 0.0,
            "token_cost": 3,
        }
        view = PayloadView(
            role="writer",
            task_id="writer",
            candidate_name="minimal",
            sections={"task_contract": [obligation]},
            runtime_inputs={},
        )

        verification = verify_payload_view(view, role="writer")

        self.assertFalse(verification.passed)
        self.assertTrue(any(gap.gap_type == "missing_obligation_coverage" for gap in verification.gaps))

    def test_payload_report_includes_layer_coverage(self) -> None:
        obligation = MemoryAtom(
            id="obligation:one",
            atom_type="obligation",
            content="Compute X.",
            source="task_graph",
            support_license="verified",
            token_cost=3,
        )
        fact = MemoryAtom(
            id="fact:one",
            atom_type="problem_fact",
            content="X is given.",
            source="context_brief",
            support_license="verified",
            token_cost=4,
        )
        derivation = MemoryAtom(
            id="derivation:one",
            atom_type="derivation",
            content="X = 1.",
            source="formal_deriver",
            support_license="verified",
            obligations=[obligation.id],
            depends_on=[fact.id],
            supported_by=[fact.id],
            token_cost=5,
        )
        task = MemoryAtom(
            id="task:one",
            atom_type="task",
            content='{"id": "T1", "deliverable": "Compute X."}',
            source="task_graph",
            support_license="verified",
            depends_on=[obligation.id],
            token_cost=6,
        )
        critic = MemoryAtom(
            id="critic:one",
            atom_type="critic_finding",
            content="Missing formula.",
            source="verification",
            support_license="verified",
            token_cost=7,
        )
        archive = MemoryAtom(
            id="archive:one",
            atom_type="archive",
            content="Full problem text.",
            source="problem_text",
            support_license="verified",
            token_cost=8,
        )
        view = PayloadView(
            role="writer",
            task_id="writer",
            candidate_name="minimal",
            sections={
                "task_contract": [obligation.to_dict(), task.to_dict()],
                "problem_kernel": [fact.to_dict()],
                "derivations": [derivation.to_dict()],
                "critic_findings": [critic.to_dict()],
                "archive": [archive.to_dict()],
            },
        )

        coverage = view.report()["layer_coverage"]

        self.assertEqual(coverage["L0_task_contract"]["atom_count"], 1)
        self.assertEqual(coverage["L1_problem_kernel"]["atom_count"], 1)
        self.assertEqual(coverage["L2_typed_work_memory"]["atom_count"], 1)
        self.assertEqual(coverage["L3_structural_state"]["atom_count"], 1)
        self.assertEqual(coverage["L4_trajectory"]["atom_count"], 1)
        self.assertEqual(coverage["L5_archive"]["atom_count"], 1)
        self.assertGreaterEqual(coverage["L3_structural_state"]["edge_count"], 4)
        self.assertEqual(coverage["L2_typed_work_memory"]["token_cost"], 5)

    def test_pattern_verifier_checks_unselected_required_obligation(self) -> None:
        graph = MemoryGraph()
        obligation = MemoryAtom(
            id="obligation:derive-x",
            atom_type="obligation",
            content="Derive X from the stated premise.",
            source="task_graph",
            source_path="task_graph.tasks[T1].deliverable",
            support_license="verified",
        )
        derivation = MemoryAtom(
            id="derivation:x",
            atom_type="derivation",
            content="Using the stated premise, derive X = 1 as the result.",
            source="formal_deriver",
            source_path="derivations[0]",
            support_license="verified",
            obligations=[obligation.id],
        )
        graph.add_atom(obligation)
        graph.add_atom(derivation)

        view, verification, rounds, _ = _repair_until_verified(
            graph=graph,
            role="writer",
            task_id="T1",
            candidate_name="minimal",
            selected={derivation.id},
            runtime_inputs={},
            max_repair_rounds=2,
        )

        self.assertTrue(verification.passed)
        self.assertGreaterEqual(rounds, 1)
        self.assertIn(obligation.id, view.atom_ids)
        self.assertTrue(any(item["obligation_id"] == obligation.id for item in view.report()["obligation_pattern_report"]))

    def test_compare_obligation_slot_gap_triggers_repair(self) -> None:
        graph = MemoryGraph()
        obligation = MemoryAtom(
            id="obligation:compare",
            atom_type="obligation",
            content="Compare option A and option B using the stated criterion.",
            source="task_graph",
            source_path="task_graph.tasks[T2].deliverable",
            support_license="verified",
        )
        comparison = MemoryAtom(
            id="claim:comparison",
            atom_type="claim",
            content="Option A is greater than option B under the stated criterion.",
            source="task_output",
            source_path="task_outputs.T2",
            support_license="supported",
            obligations=[obligation.id],
            role_affinity={"writer": -5.0},
        )
        graph.add_atom(obligation)
        graph.add_atom(comparison)

        view, verification, rounds, _ = _repair_until_verified(
            graph=graph,
            role="writer",
            task_id="T2",
            candidate_name="minimal",
            selected={obligation.id},
            runtime_inputs={},
            max_repair_rounds=2,
        )

        self.assertTrue(verification.passed)
        self.assertGreaterEqual(rounds, 1)
        self.assertIn(comparison.id, view.atom_ids)
        report = [item for item in view.report()["obligation_pattern_report"] if item["obligation_id"] == obligation.id][0]
        self.assertEqual(report["obligation_type"], "compare")
        self.assertFalse(report["missing_slots"])

    def test_derive_obligation_requires_working_material_when_available(self) -> None:
        graph = MemoryGraph()
        obligation = MemoryAtom(
            id="obligation:derive",
            atom_type="obligation",
            content="Derive the symbolic result from the premise.",
            source="task_graph",
            source_path="task_graph.tasks[T3].deliverable",
            support_license="verified",
        )
        material = MemoryAtom(
            id="derivation:available",
            atom_type="derivation",
            content="From the premise, using the relation y = x, the final result is y = 1.",
            source="formal_deriver",
            source_path="derivations[0]",
            support_license="verified",
            obligations=[obligation.id],
        )
        graph.add_atom(obligation)
        graph.add_atom(material)
        view = PayloadView(
            role="formal_deriver",
            task_id="T3",
            candidate_name="minimal",
            sections={"task_contract": [obligation.to_dict()]},
            runtime_inputs={},
        )

        verification = verify_payload_view(view, role="formal_deriver", graph=graph)

        self.assertFalse(verification.passed)
        self.assertTrue(any(gap.gap_type == "missing_obligation_slot" for gap in verification.gaps))

    def test_justify_obligation_rejects_unsupported_claim_material(self) -> None:
        graph = MemoryGraph()
        obligation = MemoryAtom(
            id="obligation:justify",
            atom_type="obligation",
            content="Justify the final claim with evidence.",
            source="task_graph",
            source_path="task_graph.tasks[T4].deliverable",
            support_license="verified",
        )
        unsupported = MemoryAtom(
            id="claim:unsupported",
            atom_type="claim",
            content="Final claim without support.",
            source="hypothesis_modeler",
            source_path="hypotheses[0]",
            support_license="unsupported",
            obligations=[obligation.id],
        )
        graph.add_atom(obligation)
        graph.add_atom(unsupported)
        view = PayloadView(
            role="writer",
            task_id="T4",
            candidate_name="minimal",
            sections={"task_contract": [obligation.to_dict()], "warnings": [unsupported.to_dict()]},
            runtime_inputs={},
        )

        verification = verify_payload_view(view, role="writer", graph=graph)

        self.assertFalse(verification.passed)
        self.assertTrue(any(gap.gap_type == "missing_pattern_material" for gap in verification.gaps))
        report = view.report()["obligation_pattern_report"][0]
        self.assertEqual(report["obligation_type"], "justify")
        self.assertIn("claim", report["missing_slots"])

    def test_unrepairable_payload_falls_back_with_report(self) -> None:
        graph = MemoryGraph()
        claim = MemoryAtom(
            id="claim:orphan",
            atom_type="claim",
            content="Unsupported final claim.",
            source="formal_deriver",
            source_path="derivations[0].result",
            support_license="supported",
        )
        graph.add_atom(claim)

        view = compile_payload_view(graph, role="writer", runtime_inputs={})

        self.assertFalse(view.payload_verified)
        self.assertEqual(view.candidate_name, "broad_fallback")
        self.assertTrue(view.report()["verifier_failures"])


if __name__ == "__main__":
    unittest.main()
