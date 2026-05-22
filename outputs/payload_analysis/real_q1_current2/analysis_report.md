# PayloadView Experiment Analysis: real_q1

## Summary

| Metric | Value |
| --- | --- |
| payload_view_count | 13 |
| verified_count | 13 |
| fail_soft_count | 0 |
| total_rendered_token_cost | 166204 |
| total_legacy_token_cost | 369437 |
| total_token_savings_vs_legacy | 203233 |
| total_token_savings_ratio_vs_legacy | 55.0% |
| rubric_proxy_coverage | 5.9% |

## Token Metrics by Role

| Role | Count | Rendered | Legacy | Savings | Savings % | Verified | Fail-soft | Repair rounds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| formal_deriver | 8 | 87153 | 153920 | 66767 | 43.4% | 8 | 0 | 0 |
| verification | 1 | 27961 | 27377 | -584 | -2.1% | 1 | 0 | 0 |
| writer | 4 | 51090 | 188140 | 137050 | 72.8% | 4 | 0 | 5 |

## Rubric-Sensitive Coverage Proxy

This is a deterministic keyword/formula proxy, not a grader. It highlights likely answer-quality risks after payload compression.

| Rubric group | Hits | Coverage | Missing proxy items |
| --- | --- | --- | --- |
| Background protocol | 0/3 | 0.0% | weak coupling Hamiltonian; postselected final state; Kraus operator M |
| Entanglement efficiency | 0/4 | 0.0% | same weak value; max Ps via Var(A); n^2 variance scaling; entangled initial/post state |
| Fixed Ps alternative | 0/3 | 0.0% | fixed postselection probability; sqrt((1-Ps)/Ps) weak value; max weak value formula |
| Fisher information | 0/5 | 0.0% | QFI definition; eta efficiency factor; I prime relation; dn postselections; Cramer-Rao bound |
| Conclusion | 1/2 | 50.0% | n-fold efficiency statement |

## Interpretation

- Expected: PayloadView reduces repeated context substantially, especially for writer calls.
- Expected: Most calls choose `minimal`; repair rounds appear only where dependency/support closure is needed.
- Expected: Verification is compressed less than writer/task calls because it is allowed to see broader context.
- Risk: `payload_verified=true` is a payload sufficiency signal, not an answer correctness signal.
- Risk: The final answer still misses several formula-level rubric proxies, so the next iteration should add rubric-sensitive obligation atoms.
- Risk: Current minimal-view selection optimizes token cost after graph verifier pass; if verifier does not encode formula obligations, it can choose a view that is too small for scoring quality.

## Charts

- [01_token_cost_by_role.png](01_token_cost_by_role.png)
- [02_per_view_token_cost.png](02_per_view_token_cost.png)
- [03_candidate_repair_profile.png](03_candidate_repair_profile.png)
- [04_payload_health_summary.png](04_payload_health_summary.png)
- [05_rubric_proxy_coverage.png](05_rubric_proxy_coverage.png)
