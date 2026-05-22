from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]

COLORS = {
    "ink": "#17212b",
    "muted": "#607080",
    "grid": "#d8dee8",
    "blue": "#2563a6",
    "cyan": "#2b8c9f",
    "green": "#3b8f6a",
    "gold": "#b9852f",
    "red": "#b85c5c",
    "violet": "#7257a8",
    "gray": "#9aa6b2",
    "panel": "#f7f9fc",
}


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"rows": [], "role_rows": []}
    return json.loads(path.read_text(encoding="utf-8", errors="replace"))


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _num(value: Optional[float], digits: int = 1) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def _complete_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [row for row in rows if row.get("status") == "complete"]


def _mean(values: List[float]) -> Optional[float]:
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def _aggregate_role_rows(role_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    aggregate: Dict[str, Dict[str, int]] = defaultdict(lambda: {"rendered": 0, "legacy": 0, "count": 0})
    for row in role_rows:
        role = str(row.get("role") or "unknown")
        aggregate[role]["rendered"] += int(row.get("rendered_tokens") or 0)
        aggregate[role]["legacy"] += int(row.get("legacy_tokens") or 0)
        aggregate[role]["count"] += int(row.get("count") or 0)
    rows = []
    for role, item in aggregate.items():
        legacy = item["legacy"]
        rendered = item["rendered"]
        ratio = (legacy - rendered) / legacy if legacy else None
        rows.append(
            {
                "role": role,
                "count": item["count"],
                "rendered_tokens": rendered,
                "legacy_tokens": legacy,
                "token_savings_ratio": ratio,
                "token_savings": legacy - rendered if legacy else None,
            }
        )
    return sorted(rows, key=lambda row: (row["token_savings_ratio"] is None, -(row["token_savings_ratio"] or 0)))


def _summary(rows: List[Dict[str, Any]], role_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    complete = _complete_rows(rows)
    quality_rows = complete or rows
    scored = [row for row in rows if row.get("judge_score") is not None]
    with_savings = [row for row in rows if row.get("token_savings_ratio") is not None]
    views = sum(int(row.get("payload_view_count") or 0) for row in rows)
    verified = sum(int(row.get("verified_count") or 0) for row in rows)
    fail_soft = sum(int(row.get("fail_soft_count") or 0) for row in rows)
    roles = _aggregate_role_rows(role_rows)
    return {
        "case_count": len(rows),
        "complete_case_count": len(complete),
        "missing_case_count": len(rows) - len(complete),
        "avg_token_savings_ratio": _mean([float(row["token_savings_ratio"]) for row in with_savings]),
        "avg_judge_score": _mean([float(row["judge_score"]) for row in scored]),
        "payload_view_count": views,
        "verified_count": verified,
        "fail_soft_count": fail_soft,
        "verifier_pass_rate": (verified / views) if views else None,
        "role_rows": roles,
        "best_role": roles[0] if roles else None,
        "reference_formula_coverage": _mean(
            [float(row["reference_formula_coverage"]) for row in quality_rows if row.get("reference_formula_coverage") is not None]
        ),
        "problem_formula_coverage": _mean(
            [float(row["problem_formula_coverage"]) for row in quality_rows if row.get("problem_formula_coverage") is not None]
        ),
        "rubric_keyword_coverage": _mean(
            [float(row["rubric_keyword_coverage"]) for row in quality_rows if row.get("rubric_keyword_coverage") is not None]
        ),
    }


def _candidate_totals(rows: List[Dict[str, Any]]) -> Counter:
    counter: Counter[str] = Counter()
    for row in rows:
        counter.update(row.get("candidate_counts") or {})
    return counter


def _improvement_items(summary: Dict[str, Any], rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    missing = int(summary.get("missing_case_count") or 0)
    formula_cov = summary.get("reference_formula_coverage")
    verifier_rate = summary.get("verifier_pass_rate")
    repairs = sum(int(row.get("repair_rounds") or 0) for row in rows)
    candidates = _candidate_totals(rows)
    fallback_count = int(candidates.get("broad_fallback", 0))

    return [
        {
            "id": "formula_obligations",
            "title": "Formula-level obligation compiler",
            "impact": 9.3,
            "effort": 4.2,
            "confidence": 0.90 if formula_cov is not None and formula_cov < 0.45 else 0.72,
            "evidence": f"Reference-formula coverage proxy is {_pct(formula_cov)}.",
            "deliverable": "Extract key equations into obligation atoms and make the verifier check explicit formula coverage.",
            "next_step": "Add formula atoms in memory_graph.py and formula-slot checks in payload_compiler.py.",
        },
        {
            "id": "batch_generalization",
            "title": "Multi-question generalization study",
            "impact": 8.8,
            "effort": 3.0,
            "confidence": 0.86 if missing else 0.78,
            "evidence": f"{missing} planned batch cases still need complete artifacts.",
            "deliverable": "Run the 7-case default batch and report savings/quality by problem type.",
            "next_step": "Run run_midterm_batch.py with --skip-existing, then rerun both analysis scripts.",
        },
        {
            "id": "verification_budget",
            "title": "Verification payload split",
            "impact": 7.6,
            "effort": 4.8,
            "confidence": 0.80,
            "evidence": "Verification can compress less than writer because it carries broad audit context.",
            "deliverable": "Separate answer-contract, evidence-audit, and risk-audit views with role-specific budgets.",
            "next_step": "Add verification subroles and compare token cost against current single verification view.",
        },
        {
            "id": "repair_calibration",
            "title": "Repair and candidate calibration",
            "impact": 7.4,
            "effort": 5.0,
            "confidence": 0.76 if repairs or fallback_count else 0.62,
            "evidence": f"{repairs} repair rounds and {fallback_count} broad fallback selections observed.",
            "deliverable": "Use candidate history to tune role profiles and reduce avoidable repair/fallback calls.",
            "next_step": "Log verifier gap types by role and introduce candidate-specific budget thresholds.",
        },
        {
            "id": "ablation_suite",
            "title": "Ablation study for research claims",
            "impact": 8.1,
            "effort": 6.2,
            "confidence": 0.70,
            "evidence": "Current evidence compares legacy vs PayloadView, but not no-repair/no-license/no-formula variants.",
            "deliverable": "Run full, PayloadView, no-repair, and no-license-gate variants on the same cases.",
            "next_step": "Add an offline ablation harness before adding new model calls.",
        },
        {
            "id": "trace_story",
            "title": "Traceable demo narrative",
            "impact": 6.5,
            "effort": 2.6,
            "confidence": 0.84,
            "evidence": "Existing payload reports contain selected atoms, repairs, and verifier gaps but need narrative packaging.",
            "deliverable": "Create one slide showing problem -> memory graph -> payload view -> judge result.",
            "next_step": "Export one exemplar PayloadView with selected atoms and repair history.",
        },
    ]


def _apply_theme() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "axes.labelcolor": COLORS["ink"],
            "xtick.color": COLORS["muted"],
            "ytick.color": COLORS["muted"],
            "text.color": COLORS["ink"],
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def _card(ax, xy, wh, title: str, value: str, subtitle: str, color: str) -> None:
    x, y = xy
    w, h = wh
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.018,rounding_size=0.03",
        transform=ax.transAxes,
        facecolor="white",
        edgecolor="#d7dee8",
        linewidth=1.0,
    )
    ax.add_patch(patch)
    ax.add_patch(
        FancyBboxPatch(
            (x + 0.025, y + h - 0.13),
            0.08,
            0.075,
            boxstyle="round,pad=0.01,rounding_size=0.025",
            transform=ax.transAxes,
            facecolor=color,
            edgecolor=color,
            alpha=0.95,
        )
    )
    ax.text(x + 0.12, y + h - 0.078, title, transform=ax.transAxes, fontsize=10.5, fontweight="bold", va="center")
    ax.text(x + 0.04, y + 0.20, value, transform=ax.transAxes, fontsize=24, fontweight="bold", color=color, va="bottom")
    ax.text(
        x + 0.04,
        y + 0.06,
        subtitle,
        transform=ax.transAxes,
        fontsize=8.7,
        color=COLORS["muted"],
        va="bottom",
        linespacing=1.12,
    )


def _save_dashboard(path: Path, rows: List[Dict[str, Any]], summary: Dict[str, Any]) -> None:
    fig = plt.figure(figsize=(13.5, 7.2))
    gs = fig.add_gridspec(2, 3, height_ratios=[1.0, 1.25], width_ratios=[1.2, 1.05, 1.05], hspace=0.33, wspace=0.25)
    ax_cards = fig.add_subplot(gs[0, :])
    ax_cards.axis("off")

    best_role = summary.get("best_role") or {}
    _card(
        ax_cards,
        (0.02, 0.12),
        (0.22, 0.72),
        "Token savings",
        _pct(summary.get("avg_token_savings_ratio")),
        "compiled PayloadView\nvs legacy payload",
        COLORS["blue"],
    )
    _card(
        ax_cards,
        (0.27, 0.12),
        (0.22, 0.72),
        "Judge score",
        _num(summary.get("avg_judge_score"), 2),
        "average\nLLM-as-judge score",
        COLORS["green"],
    )
    _card(
        ax_cards,
        (0.52, 0.12),
        (0.22, 0.72),
        "Verifier pass",
        _pct(summary.get("verifier_pass_rate")),
        f"{summary.get('verified_count', 0)}/{summary.get('payload_view_count', 0)} PayloadViews",
        COLORS["violet"],
    )
    _card(
        ax_cards,
        (0.77, 0.12),
        (0.21, 0.72),
        "Best role",
        str(best_role.get("role", "n/a")),
        f"saves {_pct(best_role.get('token_savings_ratio'))}",
        COLORS["gold"],
    )

    ax_cases = fig.add_subplot(gs[1, 0])
    data = [row for row in rows if row.get("token_savings_ratio") is not None]
    if data:
        labels = [row["case_label"].replace("anchor_real_q1_hq", "anchor").replace("batch_", "") for row in data]
        values = [row["token_savings_ratio"] * 100 for row in data]
        colors = [COLORS["blue"] if row.get("status") == "complete" else COLORS["gray"] for row in data]
        ax_cases.barh(labels, values, color=colors, height=0.58)
        ax_cases.set_xlim(0, max(75, max(values) + 10))
        ax_cases.set_xlabel("Savings (%)")
        ax_cases.set_title("Case-Level Compression")
        ax_cases.grid(axis="x", color=COLORS["grid"], alpha=0.8)
        for idx, value in enumerate(values):
            ax_cases.text(value + 1, idx, f"{value:.1f}%", va="center", fontsize=9)
    else:
        ax_cases.text(0.5, 0.5, "No complete cases yet", ha="center", va="center", transform=ax_cases.transAxes)
        ax_cases.set_title("Case-Level Compression")

    ax_coverage = fig.add_subplot(gs[1, 1])
    cov_names = ["Problem\nformulas", "Reference\nformulas", "Rubric\nkeywords"]
    cov_values = [
        summary.get("problem_formula_coverage"),
        summary.get("reference_formula_coverage"),
        summary.get("rubric_keyword_coverage"),
    ]
    cov_plot = [0 if value is None else value * 100 for value in cov_values]
    ax_coverage.bar(cov_names, cov_plot, color=[COLORS["green"], COLORS["red"], COLORS["cyan"]], width=0.55)
    ax_coverage.set_ylim(0, 112)
    ax_coverage.set_ylabel("Coverage proxy (%)")
    ax_coverage.set_title("Quality Risk Signals", pad=15)
    ax_coverage.grid(axis="y", color=COLORS["grid"], alpha=0.8)
    for idx, value in enumerate(cov_plot):
        label = "n/a" if cov_values[idx] is None else f"{value:.0f}%"
        ax_coverage.text(idx, value + 3, label, ha="center", fontsize=10, fontweight="bold")

    ax_roles = fig.add_subplot(gs[1, 2])
    roles = summary.get("role_rows") or []
    if roles:
        labels = [row["role"] for row in roles]
        values = [(row.get("token_savings_ratio") or 0) * 100 for row in roles]
        ax_roles.scatter(values, labels, s=95, color=COLORS["blue"], zorder=3)
        for y, value in enumerate(values):
            ax_roles.plot([0, value], [y, y], color=COLORS["grid"], linewidth=4, solid_capstyle="round", zorder=1)
            if value < 0:
                ax_roles.text(2.0, y, f"{value:.1f}%", va="center", ha="left", fontsize=9)
            else:
                ax_roles.text(value + 1.2, y, f"{value:.1f}%", va="center", fontsize=9)
        ax_roles.set_xlim(min(-12, min(values) - 8), max(80, max(values) + 12))
        ax_roles.set_xlabel("Savings (%)")
        ax_roles.set_title("Role Compression Profile")
        ax_roles.grid(axis="x", color=COLORS["grid"], alpha=0.75)
    else:
        ax_roles.text(0.5, 0.5, "No role data yet", ha="center", va="center", transform=ax_roles.transAxes)
        ax_roles.set_title("Role Compression Profile")

    fig.suptitle("PayloadView Midterm Research Dashboard", fontsize=17, fontweight="bold", x=0.05, y=0.98, ha="left")
    fig.text(0.05, 0.935, "Evidence chain: compact context, verifier repair, quality scoring, and next research steps.", fontsize=10.5, color=COLORS["muted"])
    fig.savefig(path, dpi=220)
    plt.close(fig)


def _save_improvement_matrix(path: Path, items: List[Dict[str, Any]]) -> None:
    fig, ax = plt.subplots(figsize=(10.8, 6.6))
    ax.axvspan(1, 4.5, color="#eaf4ef", alpha=0.85)
    ax.axhspan(7.5, 10, color="#f9f1df", alpha=0.55)
    ax.axvline(5.0, color=COLORS["grid"], linewidth=1.2)
    ax.axhline(7.5, color=COLORS["grid"], linewidth=1.2)

    palette = [COLORS["blue"], COLORS["green"], COLORS["gold"], COLORS["violet"], COLORS["cyan"], COLORS["red"]]
    label_offsets = {
        "formula_obligations": (0.15, 0.12),
        "batch_generalization": (0.15, 0.12),
        "verification_budget": (0.15, 0.10),
        "repair_calibration": (0.15, -0.18),
        "ablation_suite": (0.15, 0.12),
        "trace_story": (0.15, 0.10),
    }
    for idx, item in enumerate(items):
        size = 450 + item["confidence"] * 850
        ax.scatter(item["effort"], item["impact"], s=size, color=palette[idx % len(palette)], alpha=0.82, edgecolor="white", linewidth=1.2)
        dx, dy = label_offsets.get(item["id"], (0.15, 0.08))
        ax.text(item["effort"] + dx, item["impact"] + dy, item["title"], fontsize=9.3, fontweight="bold")

    ax.text(1.25, 9.58, "Near-term high-value zone", fontsize=10.5, fontweight="bold", color=COLORS["green"])
    ax.set_xlim(1, 9.2)
    ax.set_ylim(4.5, 10)
    ax.set_xlabel("Implementation effort")
    ax.set_ylabel("Research / defense impact")
    ax.set_title("Improvement Priority Matrix")
    ax.grid(color=COLORS["grid"], alpha=0.6)
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)


def _save_evidence_chain(path: Path, summary: Dict[str, Any]) -> None:
    fig, ax = plt.subplots(figsize=(12.5, 5.2))
    ax.axis("off")
    steps = [
        ("Typed memory graph", "obligations, evidence,\nclaims, derivations", COLORS["blue"]),
        ("Payload compiler", "minimal sufficient\nrole-specific view", COLORS["green"]),
        ("Verifier repair", f"{summary.get('verified_count', 0)}/{summary.get('payload_view_count', 0)} views passed\nfail-soft tracked", COLORS["violet"]),
        ("Quality judge", f"score {_num(summary.get('avg_judge_score'), 2)}\ncoverage proxies", COLORS["gold"]),
        ("Research loop", "formula obligations\nbatch generalization", COLORS["red"]),
    ]
    xs = [0.10, 0.30, 0.50, 0.70, 0.90]
    y = 0.53
    for idx, ((title, body, color), x) in enumerate(zip(steps, xs)):
        w = 0.15 if idx < 4 else 0.16
        box = FancyBboxPatch(
            (x - w / 2, y - 0.21),
            w,
            0.42,
            boxstyle="round,pad=0.025,rounding_size=0.04",
            transform=ax.transAxes,
            facecolor="white",
            edgecolor=color,
            linewidth=1.8,
        )
        ax.add_patch(box)
        ax.text(x, y + 0.08, title, transform=ax.transAxes, ha="center", va="center", fontsize=11, fontweight="bold", color=color)
        ax.text(x, y - 0.08, body, transform=ax.transAxes, ha="center", va="center", fontsize=9.4, color=COLORS["ink"], linespacing=1.25)
        if idx < len(xs) - 1:
            arrow = FancyArrowPatch(
                (x + w / 2 + 0.01, y),
                (xs[idx + 1] - w / 2 - 0.01, y),
                transform=ax.transAxes,
                arrowstyle="-|>",
                mutation_scale=18,
                linewidth=1.6,
                color=COLORS["muted"],
            )
            ax.add_patch(arrow)

    ax.text(0.04, 0.9, "Research Claim Structure", transform=ax.transAxes, fontsize=16, fontweight="bold", ha="left")
    ax.text(
        0.04,
        0.82,
        "The strongest defense story is not more agents; it is measured context control with auditability.",
        transform=ax.transAxes,
        fontsize=10.5,
        color=COLORS["muted"],
        ha="left",
    )
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _save_roadmap(path: Path, items: List[Dict[str, Any]]) -> None:
    phases = [
        ("Now", "Run 7-case batch\nRefresh report and charts", COLORS["blue"]),
        ("Next", "Formula obligations\nVerifier formula slots", COLORS["green"]),
        ("Then", "Ablation suite\nNo-repair / no-license variants", COLORS["gold"]),
        ("After", "Role budgets\nVerification payload split", COLORS["violet"]),
    ]
    fig, ax = plt.subplots(figsize=(12.2, 4.8))
    ax.axis("off")
    y = 0.54
    ax.plot([0.08, 0.92], [y, y], transform=ax.transAxes, color=COLORS["grid"], linewidth=5, solid_capstyle="round")
    for idx, (title, body, color) in enumerate(phases):
        x = 0.1 + idx * 0.27
        ax.scatter([x], [y], transform=ax.transAxes, s=520, color=color, edgecolor="white", linewidth=2.2, zorder=3)
        ax.text(x, y, str(idx + 1), transform=ax.transAxes, ha="center", va="center", fontsize=13, color="white", fontweight="bold")
        ax.text(x, y + 0.18, title, transform=ax.transAxes, ha="center", fontsize=13, fontweight="bold", color=color)
        ax.text(x, y - 0.23, body, transform=ax.transAxes, ha="center", fontsize=10, linespacing=1.28, color=COLORS["ink"])
    ax.text(0.04, 0.9, "Research Roadmap After Midterm", transform=ax.transAxes, fontsize=16, fontweight="bold", ha="left")
    ax.text(0.04, 0.82, "Prioritize work that converts current signals into stronger, generalizable evidence.", transform=ax.transAxes, fontsize=10.5, color=COLORS["muted"])
    fig.savefig(path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def _save_gap_bars(path: Path, summary: Dict[str, Any]) -> None:
    names = ["Problem formulas", "Reference formulas", "Rubric keywords", "Verifier pass"]
    values = [
        summary.get("problem_formula_coverage"),
        summary.get("reference_formula_coverage"),
        summary.get("rubric_keyword_coverage"),
        summary.get("verifier_pass_rate"),
    ]
    plot_values = [0 if value is None else value * 100 for value in values]
    targets = [95, 75, 85, 98]
    colors = [COLORS["green"], COLORS["red"], COLORS["cyan"], COLORS["violet"]]

    fig, ax = plt.subplots(figsize=(10.4, 5.2))
    y = list(range(len(names)))
    ax.barh(y, targets, color="#eef2f7", height=0.68, label="Target")
    ax.barh(y, plot_values, color=colors, height=0.44, label="Current")
    for idx, value in enumerate(plot_values):
        label = "n/a" if values[idx] is None else f"{value:.0f}%"
        ax.text(min(value + 2, 96), idx, label, va="center", fontsize=10, fontweight="bold")
    ax.set_yticks(y, names)
    ax.set_xlim(0, 105)
    ax.set_xlabel("Coverage / pass rate (%)")
    ax.set_title("Research Gap Signals")
    ax.grid(axis="x", color=COLORS["grid"], alpha=0.75)
    ax.legend(frameon=False, loc="lower right")
    fig.tight_layout()
    fig.savefig(path, dpi=220)
    plt.close(fig)


def _markdown_table(headers: List[str], rows: List[List[Any]]) -> str:
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
            *["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows],
        ]
    )


def _write_research_report(path: Path, charts: List[Path], summary: Dict[str, Any], items: List[Dict[str, Any]]) -> None:
    item_rows = [
        [
            idx + 1,
            item["title"],
            f"{item['impact']:.1f}",
            f"{item['effort']:.1f}",
            f"{item['confidence']:.0%}",
            item["deliverable"],
        ]
        for idx, item in enumerate(sorted(items, key=lambda item: item["impact"] / item["effort"], reverse=True))
    ]
    lines = [
        "# Midterm Research Pack",
        "",
        "## Research Positioning",
        "",
        "The defensible research contribution is an auditable context-control mechanism for multi-agent scientific reasoning. The current evidence supports a sharper story than simply adding more agents: PayloadView reduces repeated context while preserving verifier and judge quality signals.",
        "",
        "## Evidence Summary",
        "",
        _markdown_table(
            ["Signal", "Current value", "Interpretation"],
            [
                ["Average token savings", _pct(summary.get("avg_token_savings_ratio")), "Compression is already measurable against legacy full-dossier prompts."],
                ["Average judge score", _num(summary.get("avg_judge_score"), 2), "Answer quality remains high on available complete cases."],
                ["Verifier pass rate", _pct(summary.get("verifier_pass_rate")), "Payload sufficiency is explicitly checked before model calls."],
                ["Reference formula coverage", _pct(summary.get("reference_formula_coverage")), "Main quality risk: key equations are not yet first-class obligations."],
                ["Complete cases", str(summary.get("complete_case_count", 0)), "Batch completion is the fastest way to strengthen generalization claims."],
            ],
        ),
        "",
        "## Recommended Improvement Direction",
        "",
        _markdown_table(["Rank", "Improvement", "Impact", "Effort", "Confidence", "Concrete deliverable"], item_rows),
        "",
        "## Charts",
        "",
    ]
    for chart in charts:
        lines.append(f"- [{chart.name}]({chart.name})")
    lines.extend(
        [
            "",
            "## Narrative for Defense",
            "",
            "1. Start with the dashboard: show savings, judge quality, verifier pass rate, and role-level compression.",
            "2. Use the evidence-chain figure to explain why this is a research mechanism, not only an engineering wrapper.",
            "3. Use the priority matrix to justify the next iteration: formula-level obligations first, batch generalization second.",
            "4. Use the gap chart to acknowledge limitations clearly and turn them into a concrete research roadmap.",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a polished midterm research pack from analyzed PayloadView results.")
    parser.add_argument("--results-json", default="outputs/midterm_showcase/results.json")
    parser.add_argument("--output-dir", default="outputs/midterm_showcase/research_pack")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    results_path = Path(args.results_json)
    output_dir = Path(args.output_dir)
    if not results_path.is_absolute():
        results_path = ROOT / results_path
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    _apply_theme()
    results = _load_json(results_path)
    rows = list(results.get("rows") or [])
    role_rows = list(results.get("role_rows") or [])
    summary = _summary(rows, role_rows)
    items = _improvement_items(summary, rows)

    charts = [
        output_dir / "01_research_dashboard.png",
        output_dir / "02_improvement_priority_matrix.png",
        output_dir / "03_evidence_chain.png",
        output_dir / "04_research_roadmap.png",
        output_dir / "05_gap_signals.png",
    ]
    _save_dashboard(charts[0], rows, summary)
    _save_improvement_matrix(charts[1], items)
    _save_evidence_chain(charts[2], summary)
    _save_roadmap(charts[3], items)
    _save_gap_bars(charts[4], summary)

    report_path = output_dir / "research_findings.md"
    cards_path = output_dir / "research_cards.json"
    _write_research_report(report_path, charts, summary, items)
    cards_path.write_text(json.dumps({"summary": summary, "improvements": items}, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "report": str(report_path),
                "cards": str(cards_path),
                "charts": [str(chart) for chart in charts],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
