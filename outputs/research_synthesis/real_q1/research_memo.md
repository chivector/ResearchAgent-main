# Real Q1 PayloadView Research Synthesis

## Main Finding

The current run keeps the LLM-as-judge score at 9.2/10 while increasing token savings from 43.9% to 55.0%.

## Charts

- [01_savings_vs_judge_score.png](01_savings_vs_judge_score.png)
- [02_role_savings.png](02_role_savings.png)
- [03_candidate_distribution.png](03_candidate_distribution.png)

## Run-Level Metrics

| Run | Views | Verified | Fail-soft | Rendered | Legacy | Savings | Savings % | Judge | Repairs | Answer est. tokens |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| previous | 11 | 11 | 0 | 121909 | 217199 | 95290 | 43.9% | 9.2 | 0 | 2410 |
| current | 13 | 13 | 0 | 166204 | 369437 | 203233 | 55.0% | 9.2 | 5 | 3125 |

## Role-Level Savings

| Run | Role | Count | Rendered | Legacy | Savings % | Verified | Fail-soft |
| --- | --- | --- | --- | --- | --- | --- | --- |
| previous | formal_deriver | 4 | 46320 | 51914 | 10.8% | 4 | 0 |
| previous | task_executor | 2 | 21380 | 35587 | 39.9% | 2 | 0 |
| previous | verification | 1 | 16852 | 18018 | 6.5% | 1 | 0 |
| previous | writer | 4 | 37357 | 111680 | 66.5% | 4 | 0 |
| current | formal_deriver | 8 | 87153 | 153920 | 43.4% | 8 | 0 |
| current | verification | 1 | 27961 | 27377 | -2.1% | 1 | 0 |
| current | writer | 4 | 51090 | 188140 | 72.8% | 4 | 0 |

## Interpretation

- Token savings improved by 11.1% absolute, with judge score change +0.0.
- The current run has more PayloadView calls and more formal-deriver calls, but still achieves stronger overall savings.
- Writer remains the main compression win; verification can be neutral or slightly larger because it carries broader checking context.
- The added writer-material sufficiency repair is consistent with the result: writer calls show repair rounds while maintaining high judged answer quality.
- Candidate selection is still dominated by `minimal`, but repaired minimal views indicate that the verifier is adding necessary atoms instead of jumping to broad fallback.

## Research Implications

- The stronger claim is not just that tokens are reduced; it is that tokens are reduced while answer quality remains high under an independent LLM judge.
- The next useful experiment is a small multi-question batch, because one high-scoring question is evidence of feasibility but not enough for generalization.
- The next compiler improvement should target explicit formula obligations for Fisher-information style formulas, because both judge and rubric proxy identify missing or dispersed formulas.
