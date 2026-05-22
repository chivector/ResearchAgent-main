# Midterm PayloadView Showcase Report

## Main Finding

This showcase contains 8 analyzed cases, 1 complete case, average token savings 55.0%, and average LLM-as-judge score 9.20.
Payload verifier pass rate is 13/13 views (100.0%).

## Charts

- [01_token_savings_by_case.png](01_token_savings_by_case.png)
- [02_judge_score_vs_savings.png](02_judge_score_vs_savings.png)
- [03_role_level_savings.png](03_role_level_savings.png)
- [04_payload_verifier_health.png](04_payload_verifier_health.png)
- [05_candidate_repair_distribution.png](05_candidate_repair_distribution.png)
- [06_formula_rubric_coverage.png](06_formula_rubric_coverage.png)

## Case Metrics

| Case | Status | Views | Verified | Fail-soft | Rendered | Legacy | Savings % | Judge | Repairs | Coverage proxy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| anchor_real_q1_hq | complete | 13 | 13 | 0 | 166204 | 369437 | 55.0% | 9.20 | 5 | 65.8% |
| batch_p001 | missing_answer_payload_judge | 0 | 0 | 0 | 0 | 0 |  |  | 0 | 0.0% |
| batch_p002 | missing_answer_payload_judge | 0 | 0 | 0 | 0 | 0 |  |  | 0 | 0.0% |
| batch_p006 | missing_answer_payload_judge | 0 | 0 | 0 | 0 | 0 |  |  | 0 | 0.0% |
| batch_p008 | missing_answer_payload_judge | 0 | 0 | 0 | 0 | 0 |  |  | 0 | 0.0% |
| batch_p010 | missing_answer_payload_judge | 0 | 0 | 0 | 0 | 0 |  |  | 0 | 0.0% |
| batch_p013 | missing_answer_payload_judge | 0 | 0 | 0 | 0 | 0 |  |  | 0 | 0.0% |
| batch_p016 | missing_answer_payload_judge | 0 | 0 | 0 | 0 | 0 |  |  | 0 | 0.0% |

## Role-Level Savings

| Role | Calls | Rendered | Legacy | Savings % |
| --- | --- | --- | --- | --- |
| formal_deriver | 8 | 87153 | 153920 | 43.4% |
| verification | 1 | 27961 | 27377 | -2.1% |
| writer | 4 | 51090 | 188140 | 72.8% |

## Interpretation

- Compression value is shown by comparing compiled PayloadView tokens against legacy full-dossier-style payloads.
- Quality is tracked separately with LLM-as-judge scores and deterministic formula/rubric coverage proxies.
- Verifier health and repair rounds show whether minimal payloads required graph-based repair before being sent to agents.
- Missing judge or payload artifacts are kept in the table instead of being hidden, so the report can be used while a batch is still running.

## Limitations and Next Step

- LLM-as-judge is an external quality signal, not a formal proof of correctness.
- Formula/rubric coverage is a deterministic proxy and should be read as a risk detector.
- The next implementation target is formula-level obligation extraction so key equations become explicit payload verifier requirements.
