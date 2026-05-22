# Midterm Research Pack

## Research Positioning

The defensible research contribution is an auditable context-control mechanism for multi-agent scientific reasoning. The current evidence supports a sharper story than simply adding more agents: PayloadView reduces repeated context while preserving verifier and judge quality signals.

## Evidence Summary

| Signal | Current value | Interpretation |
| --- | --- | --- |
| Average token savings | 55.0% | Compression is already measurable against legacy full-dossier prompts. |
| Average judge score | 9.20 | Answer quality remains high on available complete cases. |
| Verifier pass rate | 100.0% | Payload sufficiency is explicitly checked before model calls. |
| Reference formula coverage | 18.8% | Main quality risk: key equations are not yet first-class obligations. |
| Complete cases | 1 | Batch completion is the fastest way to strengthen generalization claims. |

## Recommended Improvement Direction

| Rank | Improvement | Impact | Effort | Confidence | Concrete deliverable |
| --- | --- | --- | --- | --- | --- |
| 1 | Multi-question generalization study | 8.8 | 3.0 | 86% | Run the 7-case default batch and report savings/quality by problem type. |
| 2 | Traceable demo narrative | 6.5 | 2.6 | 84% | Create one slide showing problem -> memory graph -> payload view -> judge result. |
| 3 | Formula-level obligation compiler | 9.3 | 4.2 | 90% | Extract key equations into obligation atoms and make the verifier check explicit formula coverage. |
| 4 | Verification payload split | 7.6 | 4.8 | 80% | Separate answer-contract, evidence-audit, and risk-audit views with role-specific budgets. |
| 5 | Repair and candidate calibration | 7.4 | 5.0 | 76% | Use candidate history to tune role profiles and reduce avoidable repair/fallback calls. |
| 6 | Ablation study for research claims | 8.1 | 6.2 | 70% | Run full, PayloadView, no-repair, and no-license-gate variants on the same cases. |

## Charts

- [01_research_dashboard.png](01_research_dashboard.png)
- [02_improvement_priority_matrix.png](02_improvement_priority_matrix.png)
- [03_evidence_chain.png](03_evidence_chain.png)
- [04_research_roadmap.png](04_research_roadmap.png)
- [05_gap_signals.png](05_gap_signals.png)

## Narrative for Defense

1. Start with the dashboard: show savings, judge quality, verifier pass rate, and role-level compression.
2. Use the evidence-chain figure to explain why this is a research mechanism, not only an engineering wrapper.
3. Use the priority matrix to justify the next iteration: formula-level obligations first, batch generalization second.
4. Use the gap chart to acknowledge limitations clearly and turn them into a concrete research roadmap.
