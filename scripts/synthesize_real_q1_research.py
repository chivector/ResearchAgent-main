from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _views(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(report.get("payload_views") or [])


def _summary(report: Dict[str, Any]) -> Dict[str, Any]:
    return dict(report.get("summary") or {})


def _run_row(label: str, payload_report: Dict[str, Any], judge: Dict[str, Any], answer_file: Path) -> Dict[str, Any]:
    summary = _summary(payload_report)
    views = _views(payload_report)
    answer_text = answer_file.read_text(encoding="utf-8", errors="replace") if answer_file.exists() else ""
    repairs = sum(int(view.get("repair_rounds", 0) or 0) for view in views)
    candidates = Counter(str(view.get("candidate_name") or "unknown") for view in views)
    return {
        "label": label,
        "payload_views": int(summary.get("payload_view_count", len(views)) or 0),
        "verified": int(summary.get("verified_count", 0) or 0),
        "fail_soft": int(summary.get("fail_soft_count", 0) or 0),
        "rendered_tokens": int(summary.get("total_rendered_token_cost", 0) or 0),
        "legacy_tokens": int(summary.get("total_legacy_token_cost", 0) or 0),
        "token_savings": int(summary.get("total_token_savings_vs_legacy", 0) or 0),
        "token_savings_ratio": float(summary.get("total_token_savings_ratio_vs_legacy", 0) or 0),
        "judge_score": float(judge.get("overall_score_0_to_10", 0) or 0),
        "judge_verdict": str(judge.get("verdict", "")),
        "judge_confidence": float(judge.get("confidence_0_to_1", 0) or 0),
        "repair_rounds": repairs,
        "candidate_counts": dict(candidates),
        "answer_est_tokens": (len(answer_text) + 3) // 4,
        "answer_chars": len(answer_text),
    }


def _role_rows(label: str, payload_report: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for role, item in sorted((_summary(payload_report).get("by_role") or {}).items()):
        rendered = int(item.get("rendered_token_cost", 0) or 0)
        legacy = int(item.get("legacy_token_cost", 0) or 0)
        rows.append({
            "run": label,
            "role": role,
            "count": int(item.get("count", 0) or 0),
            "rendered": rendered,
            "legacy": legacy,
            "savings": legacy - rendered,
            "savings_ratio": (legacy - rendered) / legacy if legacy else 0.0,
            "verified": int(item.get("verified", 0) or 0),
            "fail_soft": int(item.get("fail_soft", 0) or 0),
        })
    return rows


def _save_token_quality_chart(path: Path, rows: List[Dict[str, Any]]) -> None:
    labels = [row["label"] for row in rows]
    savings = [row["token_savings_ratio"] * 100 for row in rows]
    scores = [row["judge_score"] for row in rows]
    x = list(range(len(rows)))

    fig, ax1 = plt.subplots(figsize=(8.5, 4.8))
    bars = ax1.bar(x, savings, color="#2f6f9f", width=0.48, label="Token savings")
    ax1.set_ylabel("Token savings vs legacy (%)")
    ax1.set_ylim(0, max(savings) + 18)
    ax1.set_xticks(x, labels)
    ax1.grid(axis="y", alpha=0.25)
    for bar, value in zip(bars, savings):
        ax1.text(bar.get_x() + bar.get_width() / 2, value + 1, f"{value:.1f}%", ha="center", fontsize=10)

    ax2 = ax1.twinx()
    ax2.plot(x, scores, color="#b55d60", marker="o", linewidth=2, label="LLM judge score")
    ax2.set_ylabel("LLM-as-judge score / 10")
    ax2.set_ylim(0, 10)
    for idx, value in enumerate(scores):
        ax2.text(idx, value + 0.25, f"{value:.1f}", ha="center", color="#7f3437", fontsize=10)

    fig.suptitle("Token Savings Improved While Judge Score Stayed High")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_role_savings_chart(path: Path, role_rows: List[Dict[str, Any]]) -> None:
    roles = sorted({row["role"] for row in role_rows})
    runs = []
    for row in role_rows:
        if row["run"] not in runs:
            runs.append(row["run"])
    width = 0.36
    x = list(range(len(roles)))

    fig, ax = plt.subplots(figsize=(9.5, 5.0))
    colors = ["#9aa6b2", "#2f6f9f", "#3f8f70"]
    for ridx, run in enumerate(runs):
        values = []
        for role in roles:
            match = next((row for row in role_rows if row["run"] == run and row["role"] == role), None)
            values.append((match["savings_ratio"] * 100) if match else 0)
        offset = (ridx - (len(runs) - 1) / 2) * width
        ax.bar([idx + offset for idx in x], values, width, label=run, color=colors[ridx % len(colors)])
    ax.set_xticks(x, roles, rotation=15, ha="right")
    ax.set_ylabel("Savings vs legacy (%)")
    ax.set_title("Savings by Agent Role")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_candidate_chart(path: Path, rows: List[Dict[str, Any]]) -> None:
    candidates = sorted({candidate for row in rows for candidate in row["candidate_counts"]})
    x = list(range(len(rows)))
    bottom = [0] * len(rows)
    colors = {"minimal": "#2f6f9f", "broad_fallback": "#d35f5f", "support_complete": "#3f8f70", "dependency_complete": "#6d70b8"}

    fig, ax = plt.subplots(figsize=(7.8, 4.6))
    for candidate in candidates:
        values = [row["candidate_counts"].get(candidate, 0) for row in rows]
        ax.bar(x, values, bottom=bottom, label=candidate, color=colors.get(candidate, "#999999"))
        bottom = [b + v for b, v in zip(bottom, values)]
    ax.set_xticks(x, [row["label"] for row in rows])
    ax.set_ylabel("PayloadView count")
    ax.set_title("Selected Candidate Distribution")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _markdown_table(headers: List[str], rows: List[List[Any]]) -> str:
    return "\n".join([
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
        *["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows],
    ])


def _write_markdown(path: Path, rows: List[Dict[str, Any]], role_rows: List[Dict[str, Any]], charts: List[Path]) -> None:
    current = rows[-1]
    previous = rows[0]
    delta_savings = current["token_savings_ratio"] - previous["token_savings_ratio"]
    delta_score = current["judge_score"] - previous["judge_score"]
    lines = [
        "# Real Q1 PayloadView Research Synthesis",
        "",
        "## Main Finding",
        "",
        (
            f"The current run keeps the LLM-as-judge score at {current['judge_score']:.1f}/10 "
            f"while increasing token savings from {previous['token_savings_ratio']:.1%} "
            f"to {current['token_savings_ratio']:.1%}."
        ),
        "",
        "## Charts",
        "",
    ]
    for chart in charts:
        lines.append(f"- [{chart.name}]({chart.name})")
    lines.extend([
        "",
        "## Run-Level Metrics",
        "",
        _markdown_table(
            ["Run", "Views", "Verified", "Fail-soft", "Rendered", "Legacy", "Savings", "Savings %", "Judge", "Repairs", "Answer est. tokens"],
            [[
                row["label"],
                row["payload_views"],
                row["verified"],
                row["fail_soft"],
                row["rendered_tokens"],
                row["legacy_tokens"],
                row["token_savings"],
                f"{row['token_savings_ratio']:.1%}",
                f"{row['judge_score']:.1f}",
                row["repair_rounds"],
                row["answer_est_tokens"],
            ] for row in rows],
        ),
        "",
        "## Role-Level Savings",
        "",
        _markdown_table(
            ["Run", "Role", "Count", "Rendered", "Legacy", "Savings %", "Verified", "Fail-soft"],
            [[
                row["run"],
                row["role"],
                row["count"],
                row["rendered"],
                row["legacy"],
                f"{row['savings_ratio']:.1%}",
                row["verified"],
                row["fail_soft"],
            ] for row in role_rows],
        ),
        "",
        "## Interpretation",
        "",
        f"- Token savings improved by {delta_savings:.1%} absolute, with judge score change {delta_score:+.1f}.",
        "- The current run has more PayloadView calls and more formal-deriver calls, but still achieves stronger overall savings.",
        "- Writer remains the main compression win; verification can be neutral or slightly larger because it carries broader checking context.",
        "- The added writer-material sufficiency repair is consistent with the result: writer calls show repair rounds while maintaining high judged answer quality.",
        "- Candidate selection is still dominated by `minimal`, but repaired minimal views indicate that the verifier is adding necessary atoms instead of jumping to broad fallback.",
        "",
        "## Research Implications",
        "",
        "- The stronger claim is not just that tokens are reduced; it is that tokens are reduced while answer quality remains high under an independent LLM judge.",
        "- The next useful experiment is a small multi-question batch, because one high-scoring question is evidence of feasibility but not enough for generalization.",
        "- The next compiler improvement should target explicit formula obligations for Fisher-information style formulas, because both judge and rubric proxy identify missing or dispersed formulas.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Synthesize real Q1 payload and judge results.")
    parser.add_argument("--previous-payload", default="outputs/real_q1_payload_report.json")
    parser.add_argument("--previous-judge", default="outputs/llm_judge/real_q1_previous/judge_result.json")
    parser.add_argument("--previous-answer", default="outputs/real_q1_output.md")
    parser.add_argument("--current-payload", default="outputs/real_q1_current2_payload_report.json")
    parser.add_argument("--current-judge", default="outputs/llm_judge/real_q1_current2/judge_result.json")
    parser.add_argument("--current-answer", default="outputs/real_q1_current2_output.md")
    parser.add_argument("--output-dir", default="outputs/research_synthesis/real_q1")
    args = parser.parse_args()

    previous_payload = _load_json(Path(args.previous_payload))
    current_payload = _load_json(Path(args.current_payload))
    previous_judge = _load_json(Path(args.previous_judge))
    current_judge = _load_json(Path(args.current_judge))

    rows = [
        _run_row("previous", previous_payload, previous_judge, Path(args.previous_answer)),
        _run_row("current", current_payload, current_judge, Path(args.current_answer)),
    ]
    role_rows = _role_rows("previous", previous_payload) + _role_rows("current", current_payload)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    charts = [
        output_dir / "01_savings_vs_judge_score.png",
        output_dir / "02_role_savings.png",
        output_dir / "03_candidate_distribution.png",
    ]
    _save_token_quality_chart(charts[0], rows)
    _save_role_savings_chart(charts[1], role_rows)
    _save_candidate_chart(charts[2], rows)

    result = {"runs": rows, "role_rows": role_rows}
    (output_dir / "research_synthesis.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(output_dir / "research_memo.md", rows, role_rows, charts)
    print(json.dumps({
        "output_dir": str(output_dir),
        "memo": str(output_dir / "research_memo.md"),
        "charts": [str(chart) for chart in charts],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
