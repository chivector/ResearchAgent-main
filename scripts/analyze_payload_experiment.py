from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


RUBRIC_PROXY_GROUPS = {
    "Background protocol": [
        ("weak coupling Hamiltonian", ["h_int", "interaction hamiltonian", "delta(t", "impulsive"]),
        ("postselected final state", ["postselected", "psi_f"]),
        ("Kraus operator M", ["kraus", "m =", "hat{m}"]),
    ],
    "Entanglement efficiency": [
        ("same weak value", ["same weak value", "without reducing", "fixed weak value"]),
        ("max Ps via Var(A)", ["var(a)", "variance", "max p_s"]),
        ("n^2 variance scaling", ["n^2", "lambda_max", "lambda_min"]),
        ("entangled initial/post state", ["entangled", "lambda_max", "lambda_min", "psi_f"]),
    ],
    "Fixed Ps alternative": [
        ("fixed postselection probability", ["fixed postselection probability", "fixed p_s"]),
        ("sqrt((1-Ps)/Ps) weak value", ["sqrt", "1-p_s", "p_s", "perp"]),
        ("max weak value formula", ["max", "weak value", "var(a)", "p_s"]),
    ],
    "Fisher information": [
        ("QFI definition", ["quantum fisher information", "partial_g", "i(g)"]),
        ("eta efficiency factor", ["eta", "var(a)", "a^2"]),
        ("I prime relation", ["i'(g)", "eta", "var(f)"]),
        ("dn postselections", ["d^n", "a_w^{(k)}", "phi_k"]),
        ("Cramer-Rao bound", ["cramer", "1 / 2n", "1/2n", "sigma_z"]),
    ],
    "Conclusion": [
        ("n-fold efficiency statement", ["factor of n", "n p_s", "postselection efficiency"]),
        ("Heisenberg scaling statement", ["heisenberg", "standard quantum limit"]),
    ],
}


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _estimate_token_cost(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _norm_text(text: str) -> str:
    text = text.lower()
    text = text.replace("\\\\", "\\")
    text = text.replace("\\", "")
    text = text.replace("_", "_")
    text = text.replace("−", "-")
    text = re.sub(r"\s+", " ", text)
    return text


def _contains_all(text: str, needles: Iterable[str]) -> bool:
    return all(_norm_text(needle) in text for needle in needles)


def _rubric_proxy(answer_text: str) -> Dict[str, Any]:
    normalized = _norm_text(answer_text)
    groups: Dict[str, Any] = {}
    total_hits = 0
    total_items = 0
    for group_name, items in RUBRIC_PROXY_GROUPS.items():
        rows = []
        hits = 0
        for item_name, needles in items:
            present = _contains_all(normalized, needles)
            hits += int(present)
            total_hits += int(present)
            total_items += 1
            rows.append({
                "item": item_name,
                "present": present,
                "needles": needles,
            })
        groups[group_name] = {
            "hit_count": hits,
            "item_count": len(items),
            "coverage": hits / len(items) if items else 0.0,
            "items": rows,
        }
    return {
        "coverage": total_hits / total_items if total_items else 0.0,
        "hit_count": total_hits,
        "item_count": total_items,
        "groups": groups,
    }


def _views(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(report.get("payload_views") or [])


def _role_metrics(views: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    metrics: Dict[str, Dict[str, Any]] = {}
    for view in views:
        role = str(view.get("role") or "unknown")
        bucket = metrics.setdefault(
            role,
            {
                "count": 0,
                "rendered": 0,
                "legacy": 0,
                "verified": 0,
                "fail_soft": 0,
                "repairs": 0,
            },
        )
        rendered = int(view.get("rendered_token_cost", view.get("token_cost", 0)) or 0)
        legacy = int(view.get("legacy_token_cost", 0) or 0)
        bucket["count"] += 1
        bucket["rendered"] += rendered
        bucket["legacy"] += legacy
        bucket["verified"] += int(bool(view.get("payload_verified")))
        bucket["fail_soft"] += int(not bool(view.get("payload_verified")))
        bucket["repairs"] += int(view.get("repair_rounds", 0) or 0)
    for bucket in metrics.values():
        bucket["savings"] = bucket["legacy"] - bucket["rendered"]
        bucket["savings_ratio"] = bucket["savings"] / bucket["legacy"] if bucket["legacy"] else 0.0
    return metrics


def _write_metrics_csv(path: Path, views: List[Dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(
            fp,
            fieldnames=[
                "index",
                "role",
                "task_id",
                "candidate_name",
                "payload_verified",
                "rendered_token_cost",
                "legacy_token_cost",
                "token_savings",
                "token_savings_ratio",
                "repair_rounds",
                "selected_atom_count",
                "gap_count",
            ],
        )
        writer.writeheader()
        for idx, view in enumerate(views, 1):
            rendered = int(view.get("rendered_token_cost", view.get("token_cost", 0)) or 0)
            legacy = int(view.get("legacy_token_cost", 0) or 0)
            savings = legacy - rendered
            writer.writerow({
                "index": idx,
                "role": view.get("role", ""),
                "task_id": view.get("task_id", ""),
                "candidate_name": view.get("candidate_name", ""),
                "payload_verified": bool(view.get("payload_verified")),
                "rendered_token_cost": rendered,
                "legacy_token_cost": legacy,
                "token_savings": savings,
                "token_savings_ratio": round(savings / legacy, 4) if legacy else "",
                "repair_rounds": int(view.get("repair_rounds", 0) or 0),
                "selected_atom_count": len(view.get("selected_atoms") or []),
                "gap_count": len(view.get("gaps") or []),
            })


def _save_token_by_role_chart(path: Path, role_metrics: Dict[str, Dict[str, Any]]) -> None:
    roles = sorted(role_metrics)
    rendered = [role_metrics[r]["rendered"] for r in roles]
    legacy = [role_metrics[r]["legacy"] for r in roles]
    x = list(range(len(roles)))
    width = 0.36

    fig, ax = plt.subplots(figsize=(9, 5.2))
    ax.bar([i - width / 2 for i in x], legacy, width, label="Legacy payload", color="#9aa6b2")
    ax.bar([i + width / 2 for i in x], rendered, width, label="PayloadView rendered", color="#2f6f9f")
    for i, role in enumerate(roles):
        ratio = role_metrics[role]["savings_ratio"]
        ymax = max(legacy[i], rendered[i])
        ax.text(i, ymax * 1.03, f"-{ratio:.0%}", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x, roles, rotation=20, ha="right")
    ax.set_ylabel("Estimated tokens")
    ax.set_title("Payload Token Cost by Role")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_per_view_chart(path: Path, views: List[Dict[str, Any]]) -> None:
    labels = [f"{idx}. {v.get('role')}\n{v.get('candidate_name')}" for idx, v in enumerate(views, 1)]
    legacy = [int(v.get("legacy_token_cost", 0) or 0) for v in views]
    rendered = [int(v.get("rendered_token_cost", v.get("token_cost", 0)) or 0) for v in views]
    x = list(range(len(views)))
    width = 0.38

    fig, ax = plt.subplots(figsize=(12, 5.6))
    ax.bar([i - width / 2 for i in x], legacy, width, label="Legacy", color="#b5b5b5")
    ax.bar([i + width / 2 for i in x], rendered, width, label="PayloadView", color="#3f8f70")
    ax.set_xticks(x, labels, rotation=35, ha="right", fontsize=8)
    ax.set_ylabel("Estimated tokens")
    ax.set_title("Per-Call Payload Cost")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_candidate_repair_chart(path: Path, views: List[Dict[str, Any]]) -> None:
    candidate_counts = Counter(str(v.get("candidate_name") or "unknown") for v in views)
    repair_rounds = [int(v.get("repair_rounds", 0) or 0) for v in views]
    roles = [str(v.get("role") or "unknown") for v in views]

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))
    candidates = list(candidate_counts)
    axes[0].bar(candidates, [candidate_counts[c] for c in candidates], color="#6d70b8")
    axes[0].set_title("Selected Candidate Types")
    axes[0].set_ylabel("Count")
    axes[0].grid(axis="y", alpha=0.25)

    colors = {"formal_deriver": "#2f6f9f", "task_executor": "#3f8f70", "writer": "#ba7a2f", "verification": "#8d4d9d"}
    x = list(range(len(views)))
    axes[1].bar(x, repair_rounds, color=[colors.get(role, "#777777") for role in roles])
    axes[1].set_xticks(x, [str(i) for i in range(1, len(views) + 1)])
    axes[1].set_xlabel("Payload call index")
    axes[1].set_ylabel("Repair rounds")
    axes[1].set_title("Verifier-Driven Repair Rounds")
    axes[1].grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_health_chart(path: Path, summary: Dict[str, Any]) -> None:
    total_rendered = int(summary.get("total_rendered_token_cost", 0) or 0)
    total_legacy = int(summary.get("total_legacy_token_cost", 0) or 0)
    verified = int(summary.get("verified_count", 0) or 0)
    fail_soft = int(summary.get("fail_soft_count", 0) or 0)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    axes[0].pie(
        [verified, fail_soft],
        labels=["Verified", "Fail-soft"],
        autopct="%1.0f%%",
        startangle=90,
        colors=["#3f8f70", "#d35f5f"],
    )
    axes[0].set_title("Payload Verifier Outcome")

    axes[1].bar(["Legacy", "PayloadView"], [total_legacy, total_rendered], color=["#9aa6b2", "#2f6f9f"])
    ratio = (total_legacy - total_rendered) / total_legacy if total_legacy else 0.0
    axes[1].set_title(f"Total Payload Cost (-{ratio:.1%})")
    axes[1].set_ylabel("Estimated tokens")
    axes[1].grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _save_rubric_proxy_chart(path: Path, rubric_proxy: Dict[str, Any]) -> None:
    groups = rubric_proxy["groups"]
    names = list(groups)
    coverage = [groups[name]["coverage"] for name in names]
    labels = [f"{groups[name]['hit_count']}/{groups[name]['item_count']}" for name in names]

    fig, ax = plt.subplots(figsize=(9.5, 4.8))
    bars = ax.barh(names, coverage, color="#b55d60")
    ax.set_xlim(0, 1)
    ax.set_xlabel("Proxy coverage")
    ax.set_title("Rubric-Sensitive Coverage Proxy from Final Answer")
    ax.grid(axis="x", alpha=0.25)
    for bar, label in zip(bars, labels):
        ax.text(min(bar.get_width() + 0.02, 0.95), bar.get_y() + bar.get_height() / 2, label, va="center")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _markdown_table(headers: List[str], rows: List[List[Any]]) -> str:
    line1 = "| " + " | ".join(headers) + " |"
    line2 = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return "\n".join([line1, line2] + body)


def _write_markdown_report(
    path: Path,
    report: Dict[str, Any],
    role_metrics: Dict[str, Dict[str, Any]],
    rubric_proxy: Dict[str, Any],
    charts: List[Path],
) -> None:
    summary = report.get("summary") or {}
    role_rows = []
    for role, metrics in sorted(role_metrics.items()):
        role_rows.append([
            role,
            metrics["count"],
            metrics["rendered"],
            metrics["legacy"],
            metrics["savings"],
            f"{metrics['savings_ratio']:.1%}",
            metrics["verified"],
            metrics["fail_soft"],
            metrics["repairs"],
        ])

    proxy_rows = []
    for group_name, group in rubric_proxy["groups"].items():
        missing = [item["item"] for item in group["items"] if not item["present"]]
        proxy_rows.append([
            group_name,
            f"{group['hit_count']}/{group['item_count']}",
            f"{group['coverage']:.1%}",
            "; ".join(missing) if missing else "-",
        ])

    lines = [
        "# PayloadView Experiment Analysis: real_q1",
        "",
        "## Summary",
        "",
        _markdown_table(
            ["Metric", "Value"],
            [
                ["payload_view_count", summary.get("payload_view_count", "")],
                ["verified_count", summary.get("verified_count", "")],
                ["fail_soft_count", summary.get("fail_soft_count", "")],
                ["total_rendered_token_cost", summary.get("total_rendered_token_cost", "")],
                ["total_legacy_token_cost", summary.get("total_legacy_token_cost", "")],
                ["total_token_savings_vs_legacy", summary.get("total_token_savings_vs_legacy", "")],
                ["total_token_savings_ratio_vs_legacy", f"{summary.get('total_token_savings_ratio_vs_legacy', 0):.1%}"],
                ["rubric_proxy_coverage", f"{rubric_proxy['coverage']:.1%}"],
            ],
        ),
        "",
        "## Token Metrics by Role",
        "",
        _markdown_table(
            ["Role", "Count", "Rendered", "Legacy", "Savings", "Savings %", "Verified", "Fail-soft", "Repair rounds"],
            role_rows,
        ),
        "",
        "## Rubric-Sensitive Coverage Proxy",
        "",
        "This is a deterministic keyword/formula proxy, not a grader. It highlights likely answer-quality risks after payload compression.",
        "",
        _markdown_table(["Rubric group", "Hits", "Coverage", "Missing proxy items"], proxy_rows),
        "",
        "## Interpretation",
        "",
        "- Expected: PayloadView reduces repeated context substantially, especially for writer calls.",
        "- Expected: Most calls choose `minimal`; repair rounds appear only where dependency/support closure is needed.",
        "- Expected: Verification is compressed less than writer/task calls because it is allowed to see broader context.",
        "- Risk: `payload_verified=true` is a payload sufficiency signal, not an answer correctness signal.",
        "- Risk: The final answer still misses several formula-level rubric proxies, so the next iteration should add rubric-sensitive obligation atoms.",
        "- Risk: Current minimal-view selection optimizes token cost after graph verifier pass; if verifier does not encode formula obligations, it can choose a view that is too small for scoring quality.",
        "",
        "## Charts",
        "",
    ]
    for chart in charts:
        lines.append(f"- [{chart.name}]({chart.name})")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze PayloadView experiment report.")
    parser.add_argument("--payload-report", default="outputs/real_q1_payload_report.json")
    parser.add_argument("--answer-file", default="outputs/real_q1_output.md")
    parser.add_argument("--output-dir", default="outputs/payload_analysis/real_q1")
    args = parser.parse_args()

    report_path = Path(args.payload_report)
    answer_path = Path(args.answer_file)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report = _load_json(report_path)
    views = _views(report)
    answer_text = answer_path.read_text(encoding="utf-8", errors="replace") if answer_path.exists() else ""
    rubric_proxy = _rubric_proxy(answer_text)
    role_metrics = _role_metrics(views)

    metrics_csv = output_dir / "payload_view_metrics.csv"
    proxy_json = output_dir / "rubric_proxy.json"
    report_md = output_dir / "analysis_report.md"

    _write_metrics_csv(metrics_csv, views)
    proxy_json.write_text(json.dumps(rubric_proxy, ensure_ascii=False, indent=2), encoding="utf-8")

    charts = [
        output_dir / "01_token_cost_by_role.png",
        output_dir / "02_per_view_token_cost.png",
        output_dir / "03_candidate_repair_profile.png",
        output_dir / "04_payload_health_summary.png",
        output_dir / "05_rubric_proxy_coverage.png",
    ]
    _save_token_by_role_chart(charts[0], role_metrics)
    _save_per_view_chart(charts[1], views)
    _save_candidate_repair_chart(charts[2], views)
    _save_health_chart(charts[3], report.get("summary") or {})
    _save_rubric_proxy_chart(charts[4], rubric_proxy)
    _write_markdown_report(report_md, report, role_metrics, rubric_proxy, charts)

    print(json.dumps({
        "output_dir": str(output_dir),
        "summary": report.get("summary") or {},
        "rubric_proxy_coverage": rubric_proxy["coverage"],
        "charts": [str(chart) for chart in charts],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
