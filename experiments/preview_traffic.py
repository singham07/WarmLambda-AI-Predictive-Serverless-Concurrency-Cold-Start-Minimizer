"""
experiments/preview_traffic.py
================================
Visualise request-arrival counts per 10 s for all four traffic scenarios.

Usage
-----
    python -m experiments.preview_traffic

Saves
-----
    results/traffic_preview.png
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root (c:/warmlambda) is on sys.path regardless of CWD.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import matplotlib  # noqa: E402  (must come after path patch)
matplotlib.use("Agg")  # headless – no display required

import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as ticker  # noqa: E402
import numpy as np  # noqa: E402

from warmlambda.core.config import SimConfig  # noqa: E402
from warmlambda.core.traffic import SCENARIOS, generate_trace  # noqa: E402

# ── Visual theme ────────────────────────────────────────────────────────────

_PALETTE = {
    "moderate":  "#4C72B0",
    "high_load": "#DD8452",
    "extreme":   "#55A868",
    "periodic":  "#C44E52",
}

_DESCRIPTIONS = {
    "moderate":  "Base 3 req/s · ±30 % sine (period 1200 s)",
    "high_load": "Base 30 req/s · linear ramp 0.6× → 1.4×",
    "extreme":   "Base 2 req/s · 3-6 random spikes × 15",
    "periodic":  "Base 5 req/s · 60 % sine (period 600 s)",
}


def main() -> None:
    cfg = SimConfig(duration_s=3600.0)
    seed = 42
    bin_size_s = 10.0
    n_bins = int(cfg.duration_s / bin_size_s)
    edges = np.arange(n_bins + 1) * bin_size_s
    centers = (edges[:-1] + edges[1:]) / 2.0

    scenarios = list(SCENARIOS)  # preserves insertion order
    n_sc = len(scenarios)

    fig, axes = plt.subplots(
        n_sc, 1,
        figsize=(15, 3.6 * n_sc),
        sharex=True,
        facecolor="#0F1117",
    )
    fig.subplots_adjust(hspace=0.05, top=0.93)
    fig.suptitle(
        "WarmLambda AI – Simulated Traffic  (seed = 42, 1-hour run)",
        fontsize=14,
        fontweight="bold",
        color="white",
        y=0.97,
    )

    for ax, scenario in zip(axes, scenarios):
        color = _PALETTE[scenario]
        trace = generate_trace(scenario, cfg, seed=seed)
        arrivals = np.array([r.arrival_s for r in trace])
        counts, _ = np.histogram(arrivals, bins=edges)

        # ── Area + line ──
        ax.fill_between(centers, counts, alpha=0.25, color=color)
        ax.plot(centers, counts, color=color, linewidth=1.5, zorder=3)

        # ── Running-mean overlay (60 s window) ──
        window = max(1, int(60.0 / bin_size_s))
        kernel = np.ones(window) / window
        smoothed = np.convolve(counts, kernel, mode="same")
        ax.plot(centers, smoothed, color="white", linewidth=1.0,
                alpha=0.55, linestyle="--", zorder=4, label="60 s rolling avg")

        # ── Labels / styling ──
        n_req = len(trace)
        ax.set_facecolor("#161B22")
        ax.set_ylabel("Req / 10 s", color="white", fontsize=9)
        ax.tick_params(colors="white", labelsize=8)
        for spine in ax.spines.values():
            spine.set_edgecolor("#30363D")
        ax.yaxis.set_major_locator(ticker.MaxNLocator(nbins=4, integer=True))
        ax.grid(axis="y", color="#30363D", linewidth=0.6, zorder=0)

        # Scenario badge
        ax.text(
            0.01, 0.88,
            f"  {scenario}  ",
            transform=ax.transAxes,
            fontsize=10, fontweight="bold",
            color="white",
            bbox=dict(boxstyle="round,pad=0.3", facecolor=color, alpha=0.85),
            va="top",
        )
        # Description + count
        ax.text(
            0.99, 0.88,
            f"{_DESCRIPTIONS[scenario]}   │   n = {n_req:,}",
            transform=ax.transAxes,
            fontsize=8.5, color="#C9D1D9",
            ha="right", va="top",
        )

        ax.legend(loc="upper right", fontsize=7.5, framealpha=0.3,
                  labelcolor="white", handlelength=1.5)

    axes[-1].set_xlabel("Simulation time (s)", color="white", fontsize=10)
    axes[-1].tick_params(axis="x", colors="white")

    # ── Save ────────────────────────────────────────────────────────────────
    results_dir = _PROJECT_ROOT / "results"
    results_dir.mkdir(exist_ok=True)
    out_path = results_dir / "traffic_preview.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f"[preview_traffic] Saved -> {out_path}")


if __name__ == "__main__":
    main()
