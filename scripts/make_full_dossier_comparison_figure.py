from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt_k(value: int) -> str:
    return f"{value / 1000:.1f}k"


def _badge(ax, xy, text: str, color: str, width: float = 0.88) -> None:
    x, y = xy
    patch = FancyBboxPatch(
        (x, y),
        width,
        0.16,
        boxstyle="round,pad=0.018,rounding_size=0.025",
        linewidth=0,
        facecolor=color,
        alpha=0.13,
        transform=ax.transAxes,
    )
    ax.add_patch(patch)
    ax.text(x + 0.035, y + 0.08, text, transform=ax.transAxes, va="center", ha="left", fontsize=11, color="#263238")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create paper figure: full dossier payload vs PayloadView.")
    parser.add_argument("--payload-report", default="outputs/real_q1_current2_payload_report.json")
    parser.add_argument("--judge-result", default="outputs/llm_judge/real_q1_current2/judge_result.json")
    parser.add_argument("--output-dir", default="outputs/paper_figures")
    args = parser.parse_args()

    report = _load_json(Path(args.payload_report))
    judge = _load_json(Path(args.judge_result))
    summary = report["summary"]
    legacy = int(summary["total_legacy_token_cost"])
    payload = int(summary["total_rendered_token_cost"])
    savings_ratio = float(summary["total_token_savings_ratio_vs_legacy"])
    verified = int(summary["verified_count"])
    total_views = int(summary["payload_view_count"])
    fail_soft = int(summary["fail_soft_count"])
    judge_score = float(judge["overall_score_0_to_10"])

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.titleweight": "bold",
        "axes.labelcolor": "#37474f",
        "xtick.color": "#37474f",
        "ytick.color": "#37474f",
    })

    fig = plt.figure(figsize=(9.4, 4.9), facecolor="white")
    gs = fig.add_gridspec(1, 2, width_ratios=[1.35, 1.0], wspace=0.28)
    ax = fig.add_subplot(gs[0, 0])
    ax_info = fig.add_subplot(gs[0, 1])

    colors = ["#b8c0cc", "#2f6f9f"]
    labels = ["Full-dossier\nlegacy payload", "Compiled\nPayloadView"]
    values = [legacy, payload]
    bars = ax.bar(labels, [v / 1000 for v in values], color=colors, width=0.55)
    ax.set_ylabel("Estimated input tokens (thousands)")
    ax.set_title("PayloadView Cuts Context Load")
    ax.grid(axis="y", color="#d9dee5", linewidth=0.8, alpha=0.7)
    ax.set_axisbelow(True)
    ymax = legacy / 1000 * 1.22
    ax.set_ylim(0, ymax)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + ymax * 0.025,
            _fmt_k(value),
            ha="center",
            va="bottom",
            fontsize=12,
            fontweight="bold",
            color="#263238",
        )

    x0, x1 = 0, 1
    y = legacy / 1000 * 1.08
    ax.annotate(
        "",
        xy=(x1, payload / 1000 + 8),
        xytext=(x0, y),
        arrowprops=dict(arrowstyle="->", color="#b55d60", lw=2.0),
    )
    ax.text(
        0.5,
        y + ymax * 0.035,
        f"{savings_ratio:.1%} fewer tokens",
        ha="center",
        va="bottom",
        fontsize=13,
        fontweight="bold",
        color="#b55d60",
    )

    ax_info.axis("off")
    ax_info.set_title("Quality Signals Preserved", loc="left")
    _badge(ax_info, (0.02, 0.72), f"LLM-as-judge: {judge_score:.1f}/10 ({judge.get('verdict', '')})", "#3f8f70")
    _badge(ax_info, (0.02, 0.50), f"Payload verifier: {verified}/{total_views} views passed", "#2f6f9f")
    _badge(ax_info, (0.02, 0.28), f"Fail-soft fallbacks: {fail_soft}", "#8d4d9d")
    ax_info.text(
        0.02,
        0.08,
        "Real Q1 end-to-end run. Token counts compare\n"
        "the legacy full-dossier-style prompt payload\n"
        "against the compiled minimal-sufficient PayloadView.",
        transform=ax_info.transAxes,
        ha="left",
        va="bottom",
        fontsize=9.5,
        color="#607d8b",
        linespacing=1.35,
    )

    fig.suptitle("Minimum-Sufficient Payloads Reduce Context Without Lowering Judged Answer Quality", fontsize=13.5, fontweight="bold", y=0.98)
    fig.subplots_adjust(top=0.83, bottom=0.18, left=0.08, right=0.98)

    for ext in ("png", "pdf", "svg"):
        fig.savefig(output_dir / f"full_dossier_vs_payloadview.{ext}", dpi=300 if ext == "png" else None)
    plt.close(fig)

    print(json.dumps({
        "png": str(output_dir / "full_dossier_vs_payloadview.png"),
        "pdf": str(output_dir / "full_dossier_vs_payloadview.pdf"),
        "svg": str(output_dir / "full_dossier_vs_payloadview.svg"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
