#!/usr/bin/env python3
"""Aggregate Phase 4 pilot evidence and create exploratory figures."""

from __future__ import annotations

import json
from pathlib import Path
import re

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent.parent
PILOT = ROOT / "results" / "pilot"
FIGURES = ROOT / "figures" / "pilot"
PROCESSED = ROOT / "results" / "processed"


def load_summary(run: Path) -> dict:
    return json.loads((run / "derived-summary.json").read_text())


def ac_valid(run: Path) -> bool:
    manifest = json.loads((run / "manifest.json").read_text())
    start = manifest["environment_start"]["power_supplies"]["ACAD"]["online"]
    end = manifest["environment_end"]["power_supplies"]["ACAD"]["online"]
    return start == "1" and end == "1"


def capacity_rows() -> list[dict]:
    rows = []
    patterns = ("final-refine-mixed-*",)
    for pattern in patterns:
        for run in PILOT.glob(pattern):
            match = re.search(r"mixed-p(10|100)-w(1|2)-r(\d+)", run.name)
            if not match or not (run / "derived-summary.json").exists():
                continue
            summary = load_summary(run)
            outcomes = summary["measurement_outcomes"]
            rows.append(
                {
                    "run": run.name,
                    "workload": "mixed",
                    "period_ms": int(match.group(1)),
                    "workers": int(match.group(2)),
                    "rate": int(match.group(3)),
                    "completion_fraction": outcomes.get("completed", 0)
                    / summary["measurement_offered"],
                    "goodput": summary["timely_goodput_per_sec"],
                    "generator_valid": summary["provisional_generator_valid"],
                    "ac_valid": ac_valid(run),
                }
            )
    for run in PILOT.glob("final-refine-uniform-*"):
        match = re.search(r"uniform-p(10|100)-w(1|2)-r(\d+)", run.name)
        if not match or not (run / "derived-summary.json").exists():
            continue
        summary = load_summary(run)
        outcomes = summary["measurement_outcomes"]
        rows.append(
            {
                "run": run.name,
                "workload": "uniform_141k",
                "period_ms": int(match.group(1)),
                "workers": int(match.group(2)),
                "rate": int(match.group(3)),
                "completion_fraction": outcomes.get("completed", 0)
                / summary["measurement_offered"],
                "goodput": summary["timely_goodput_per_sec"],
                "generator_valid": summary["provisional_generator_valid"],
                "ac_valid": ac_valid(run),
            }
        )
    return rows


def plot_capacity(rows: list[dict]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    for ax, workload, title in zip(
        axes,
        ("mixed", "uniform_141k"),
        ("Mixed-duration workload", "Calibrated uniform workload"),
        strict=True,
    ):
        subset = [row for row in rows if row["workload"] == workload]
        for period, workers, marker in ((10, 1, "o"), (10, 2, "s"), (100, 1, "^"), (100, 2, "D")):
            points = sorted(
                [
                    row
                    for row in subset
                    if row["period_ms"] == period
                    and row["workers"] == workers
                    and row["ac_valid"]
                ],
                key=lambda row: row["rate"],
            )
            if points:
                ax.plot(
                    [row["rate"] for row in points],
                    [row["goodput"] for row in points],
                    marker=marker,
                    label=f"{period} ms, {workers} worker(s)",
                )
        invalid = [row for row in subset if not row["ac_valid"]]
        if invalid:
            ax.scatter(
                [row["rate"] for row in invalid],
                [row["goodput"] for row in invalid],
                marker="x",
                color="gray",
                label="battery-invalid",
            )
        maximum = max((row["rate"] for row in subset), default=1)
        ax.plot([0, maximum], [0, maximum], linestyle="--", color="black", linewidth=1, label="offered=goodput")
        ax.set(title=title, xlabel="Offered requests/s", ylabel="Timely goodput/s")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle("Exploratory capacity sweeps (pilot only)")
    fig.savefig(FIGURES / "capacity_sweeps.png", dpi=180)
    plt.close(fig)


def plot_comparisons() -> None:
    names = [
        "final-refine-mixed-p10-w1-r2000",
        "final-refine-mixed-p10-w1-r2100",
        "final-refine-mixed-p100-w1-r2000",
        "final-refine-mixed-p100-w1-r2100",
        "final-refine-uniform-p10-w1-r2600",
        "final-refine-uniform-p10-w1-r2700",
        "final-refine-uniform-p100-w1-r2600",
        "final-refine-uniform-p100-w1-r2700",
        "final-anchor-moderate-w2",
        "final-anchor-moderate-w8",
        "final-anchor-stress-w2",
        "final-anchor-stress-w8",
    ]
    runs = [PILOT / name for name in names]
    labels, goodput, p99, drops = [], [], [], []
    for run in runs:
        summary = load_summary(run)
        task_class = "long" if "mixed" in run.name else "uniform"
        labels.append(run.name.removeprefix("final-").replace("-", "\n"))
        goodput.append(summary["timely_goodput_per_sec"])
        p99.append(summary["by_class"][task_class]["latency"]["end_to_end_us"]["p99"] / 1_000)
        drops.append(summary["measurement_outcomes"].get("dropped_queue_full", 0))
    order = np.arange(len(labels))
    fig, axes = plt.subplots(2, 1, figsize=(14, 9), constrained_layout=True)
    colors = ["#4477aa" if value == 0 else "#cc6677" for value in drops]
    axes[0].bar(order, goodput, color=colors)
    axes[0].set(ylabel="Timely goodput/s", title="Selected common-rate pilot cells")
    axes[1].bar(order, p99, color=colors)
    axes[1].set_yscale("log")
    axes[1].set(ylabel="Class p99 end-to-end latency (ms, log scale)", title="Uniform p99 or mixed long-class p99")
    axes[1].set_xticks(order, labels, rotation=0, fontsize=6)
    for ax in axes:
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("AC/performance pilot observations; red indicates queue drops")
    fig.savefig(FIGURES / "selected_comparisons.png", dpi=180)
    plt.close(fig)


def plot_generator() -> None:
    runs = (
        sorted(PILOT.glob("gtpoll-*"))
        + sorted(PILOT.glob("final-feas2-*"))
        + sorted(PILOT.glob("final-anchor-*-w*"))
    )
    emission, write, backlog, names = [], [], [], []
    for run in runs:
        summary = load_summary(run)
        names.append(run.name)
        emission.append(summary["scheduler_gate"]["p99_lag_us"])
        write.append(summary["transport_gate"]["p99_write_completion_lag_us"])
        backlog.append(summary["transport_gate"]["maximum_sender_backlog"])
    fig, ax = plt.subplots(figsize=(10, 5), constrained_layout=True)
    ax.scatter(emission, write, c=backlog, cmap="viridis", s=55)
    ax.axhline(250, linestyle="--", color="red", label="proposed 250 µs minimum p99 limit")
    ax.set(xlabel="p99 scheduler-emission lag (µs)", ylabel="p99 socket-write-completion lag (µs)", title="Emission timing does not imply transport timing")
    ax.grid(alpha=0.25)
    ax.legend()
    colorbar = fig.colorbar(ax.collections[0], ax=ax)
    colorbar.set_label("Maximum sender backlog")
    fig.savefig(FIGURES / "generator_timing.png", dpi=180)
    plt.close(fig)


def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    rows = capacity_rows()
    (PROCESSED / "pilot_capacity_rows.json").write_text(json.dumps(rows, indent=2) + "\n")
    plot_capacity(rows)
    plot_comparisons()
    plot_generator()
    print(f"wrote {len(rows)} capacity rows and three figures")


if __name__ == "__main__":
    main()
