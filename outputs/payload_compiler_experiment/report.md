# Payload Compiler Offline Experiment

This experiment does not call any model. It compares the current PayloadView renderer with a full-graph payload baseline and checks generic compiler behavior.

## Summary

- cases: 10
- payload verified: 9/10
- fail-soft views: 1/10
- behavior checks passed: 10/10
- selected minimal views: 9/10
- repaired minimal views: 3/10
- rendered tokens: 4906
- full-graph baseline tokens: 31964
- token savings: 27058 (84.7%)

## Charts

- [01_token_cost_by_case.png](01_token_cost_by_case.png)
- [02_behavior_preservation.png](02_behavior_preservation.png)
- [03_selected_atoms_vs_graph.png](03_selected_atoms_vs_graph.png)
- [04_candidate_repair_outcome.png](04_candidate_repair_outcome.png)
- [05_savings_vs_preservation.png](05_savings_vs_preservation.png)

## Case Metrics

| Case | Role | Candidate | Repairs | Verified | Checks | Rendered | Full Graph | Savings | Atoms | Notes |
| --- | --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | --- |
| real_q1_writer | writer | minimal | 0 | True | True | 901 | 4989 | 81.9% | 24/25 | smallest passing view |
| real_q1_verification | verification | minimal | 0 | True | True | 1895 | 5006 | 62.2% | 25/25 | smallest passing view; verification sees archive |
| generic_formula_writer | writer | minimal | 0 | True | True | 348 | 1968 | 82.3% | 12/13 | smallest passing view |
| speculative_filter_writer | writer | minimal | 0 | True | True | 185 | 1197 | 84.5% | 8/9 | smallest passing view |
| support_repair_writer | writer | minimal | 1 | True | True | 386 | 4860 | 92.1% | 31/43 | verifier repaired graph gaps; smallest repaired view |
| dependency_repair_deriver | formal_deriver | minimal | 1 | True | True | 350 | 4416 | 92.1% | 26/38 | verifier repaired graph gaps; smallest repaired view |
| critic_signal_writer | writer | minimal | 0 | True | True | 361 | 4362 | 91.7% | 29/38 | smallest passing view |
| writer_material_sufficiency | writer | minimal | 1 | True | True | 313 | 4628 | 93.2% | 29/41 | verifier repaired graph gaps; smallest repaired view |
| verification_risk_visibility | verification | minimal | 0 | True | True | 90 | 276 | 67.4% | 2/2 | smallest passing view |
| fail_soft_uncovered_obligation | writer | broad_fallback | 3 | False | True | 77 | 262 | 70.6% | 2/2 | verifier repaired graph gaps; fail-soft fallback with gaps |

## Interpretation

- Token savings are expected: the renderer only emits selected atoms and compact runtime inputs, while the baseline dumps all active graph atoms with metadata.
- `verification` compresses less than `writer` because it is allowed to see the full archive/problem for contamination and omission checks.
- Most selected candidates are `minimal` by design. A selected `minimal` can still be verifier-repaired; support/dependency cases are repaired minimal views, not unvalidated seeds.
- The support/dependency/writer-material repair cases show that the graph verifier can add low-ranked but required support, dependency, or prior-output atoms without jumping to broad fallback.
- The writer-material case targets under-informed minimal views: if writable prior task output exists in the graph, writer must receive at least one such material atom.
- The critic-signal case checks that active critic/proof-gap state changes optional atom ranking enough for writer to receive critic findings.
- The fail-soft case is intentionally not verified. It confirms the pipeline keeps a broad fallback report with a concrete gap instead of silently passing an uncovered obligation.

## Limitations

- This is a payload compiler experiment, not an answer-quality experiment; it does not call an LLM and cannot measure final correctness.
- The full-graph baseline is intentionally conservative and metadata-heavy. For exact historical cost comparison, use an end-to-end run with `legacy_token_cost` in the payload report.
- Current checks are deterministic proxies for expected compiler behavior. They should be paired with at least one API end-to-end run before claiming accuracy impact.

## Behavior Checks

### real_q1_writer
- present::required answer part: True
- present::prompt formula: True
- present::derivation completeness: True
- absent::I'(g) approx eta I(g): True
- absent::A_w^{(k)}: True
- absent::max_{Psi_f} P_s: True
- absent::P_s^{(n)}: True
- absent::M = <Psi_f|: True
- absent::Phys. Rev.: True
- absent::arXiv:1305: True
- no_section::archive: True

### real_q1_verification
- present::Question:: True
- present::required answer part: True
- section::archive: True

### generic_formula_writer
- present::E_0 = 4\pi^2/(2 M L^2): True
- present::required answer part: True
- present::comparison completeness: True
- present::derivation completeness: True
- absent::weak-value Kraus operator: True
- absent::A_w^{(k)}: True

### speculative_filter_writer
- allowed_absent::Speculative external mechanism: True
- warning_present::Speculative external mechanism: True

### support_repair_writer
- atom::evidence:low_rank_support: True
- repair_rounds>=1: True

### dependency_repair_deriver
- atom::problem_fact:unit_dependency: True
- repair_rounds>=1: True

### critic_signal_writer
- section::critic_findings: True
- atom::critic_finding:active_gap: True

### writer_material_sufficiency
- section::dependent_outputs: True
- atom::claim:prior_task_output: True
- repair_rounds>=1: True

### verification_risk_visibility
- present::Unsupported risky claim: True
- warning_present::Prohibited claim: True
- normal_absent::Prohibited claim: True

### fail_soft_uncovered_obligation
- verified_is::False: True
- candidate::broad_fallback: True
- gap::missing_obligation_coverage: True
