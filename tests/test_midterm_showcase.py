from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_midterm_batch import load_midterm_results, normalize_formula_text, rubric_proxy
from scripts.run_midterm_batch import case_paths, is_case_complete, parse_problem_ids


class MidtermShowcaseTests(unittest.TestCase):

    def test_load_midterm_results_keeps_missing_artifacts_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dataset = root / "test.jsonl"
            dataset.write_text(
                "\n".join(
                    [
                        json.dumps({"problem": "Problem 1: compute $E=mc^2$.", "answer": "Use $E=mc^2$."}),
                        json.dumps({"problem": "Problem 2", "answer": "Reference 2"}),
                    ]
                ),
                encoding="utf-8",
            )

            paths = case_paths(root, 1)
            paths.case_dir.mkdir(parents=True)
            paths.answer_file.write_text("The answer uses $E=mc^2$.", encoding="utf-8")
            paths.payload_report.write_text(
                json.dumps(
                    {
                        "summary": {
                            "payload_view_count": 1,
                            "verified_count": 1,
                            "fail_soft_count": 0,
                            "total_rendered_token_cost": 100,
                            "total_legacy_token_cost": 250,
                            "total_token_savings_vs_legacy": 150,
                            "total_token_savings_ratio_vs_legacy": 0.6,
                            "by_role": {
                                "writer": {
                                    "count": 1,
                                    "rendered_token_cost": 100,
                                    "legacy_token_cost": 250,
                                    "verified": 1,
                                    "fail_soft": 0,
                                }
                            },
                        },
                        "payload_views": [
                            {
                                "role": "writer",
                                "candidate_name": "minimal",
                                "payload_verified": True,
                                "repair_rounds": 0,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = load_midterm_results(root, dataset, problem_ids=[1, 2], include_anchor=False)

            self.assertEqual(len(result["rows"]), 2)
            self.assertEqual(result["rows"][0]["status"], "missing_judge")
            self.assertEqual(result["rows"][0]["token_savings_ratio"], 0.6)
            self.assertEqual(result["rows"][0]["candidate_counts"], {"minimal": 1})
            self.assertEqual(result["rows"][1]["status"], "missing_answer_payload_judge")
            self.assertEqual(result["rows"][1]["payload_view_count"], 0)
            self.assertEqual(result["role_rows"][0]["role"], "writer")

    def test_formula_normalization_handles_latex_and_unicode_variants(self) -> None:
        latex = r"I'(g) \approx \eta I(g)"
        unicode = "I'(g) ≈ η I(g)"

        self.assertEqual(normalize_formula_text(latex), normalize_formula_text(unicode))

        proxy = rubric_proxy(
            problem_text="Question: compare the Fisher information.",
            reference_text=r"The expected relation is $I'(g) \approx \eta I(g)$.",
            answer_text="The final relation is I'(g) ≈ η I(g), with eta as the efficiency factor.",
        )

        self.assertEqual(proxy["groups"]["reference_formula_coverage"]["coverage"], 1.0)

    def test_case_completion_and_problem_id_parsing_support_skip_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = case_paths(Path(tmp), 3)
            paths.case_dir.mkdir(parents=True)
            paths.judge_dir.mkdir(parents=True)
            paths.answer_file.write_text("answer", encoding="utf-8")
            paths.payload_report.write_text("{}", encoding="utf-8")

            self.assertTrue(is_case_complete(paths, run_judge=False))
            self.assertFalse(is_case_complete(paths, run_judge=True))

            paths.judge_result.write_text("{}", encoding="utf-8")
            self.assertTrue(is_case_complete(paths, run_judge=True))

        self.assertEqual(parse_problem_ids("1,2,4-6,2"), [1, 2, 4, 5, 6])


if __name__ == "__main__":
    unittest.main()
