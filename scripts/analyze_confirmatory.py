#!/usr/bin/env python3
"""Reproduce Phase 5 run metrics, paired effects, provenance, and four figures."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parent.parent
ATTEMPTS = ROOT / "results" / "confirmatory" / "attempts"
FIGURES = ROOT / "figures" / "confirmatory"
PROCESSED = ROOT / "results" / "processed" / "confirmatory"


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def quantile(values: list[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=np.float64), q, method="linear")) if values else float("nan")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def valid_index() -> list[dict[str, str]]:
    with (ROOT / "run_index.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if row["valid"] == "True"]


def run_metrics(index_row: dict[str, str], cells: dict[str, dict]) -> dict[str, object]:
    cell = cells[index_row["cell_id"]]
    run = ATTEMPTS / index_row["run_id"]
    summary, server, generator, manifest = (load(run / name) for name in ("derived-summary.json", "server-summary.json", "generator-summary.json", "manifest.json"))
    records = [json.loads(line) for line in (run / "requests.ndjson").read_text().splitlines() if line]
    measurement = [record for record in records if record["request"]["phase"] == "measurement"]
    complete = [record for record in measurement if record["final_outcome"] == "completed" and record["response"]]
    e2e = [(record["response"]["completion_ns"] - record["request"]["intended_arrival_ns"]) / 1e6 for record in complete]
    start, end = server["snapshots"]["measurement_start"], server["snapshots"]["measurement_end"]
    delta = {key: end["cpu_stat"][key] - start["cpu_stat"][key] for key in ("usage_usec", "nr_periods", "nr_throttled", "throttled_usec")}
    wall_s = (end["timestamp_ns"] - start["timestamp_ns"]) / 1e9
    completed = summary["measurement_outcomes"].get("completed", 0)
    dropped = sum(count for outcome, count in summary["measurement_outcomes"].items() if outcome.startswith("dropped"))
    incomplete = summary["measurement_outcomes"].get("incomplete", 0)
    admitted = completed + incomplete
    worker_cpu_us = sum(record["response"].get("execution_cpu_ns") or 0 for record in complete) / 1000
    queue_depths = [record["response"]["queue_len_at_admission"] for record in measurement if record["response"] is not None]
    queue_midpoint = len(queue_depths) // 2
    classes = summary["by_class"]
    def latency(task: str, metric: str, percentile: str) -> float:
        return classes[task]["latency"][metric][percentile] / 1000
    temperatures = []
    pcore_frequencies_ghz = []
    for sample in [manifest["environment_start"], *manifest["environment_samples"], manifest["environment_end"]]:
        temperatures.extend(float(item["temp_millicelsius"]) / 1000 for item in sample["temperatures"].values() if item.get("type") == "x86_pkg_temp" and item.get("temp_millicelsius"))
        pcore_frequencies_ghz.extend(float(sample["cpu_frequencies_khz"][f"cpu{cpu}"]) / 1_000_000 for cpu in range(8) if sample["cpu_frequencies_khz"].get(f"cpu{cpu}"))
    return {
        "run_id": index_row["run_id"], "cell_id": index_row["cell_id"], "block": cell["block"],
        "period_ms": cell["period_ms"], "workers": cell["workers"], "load": cell["load"], "rate_per_sec": cell["rate_per_sec"],
        "offered": summary["measurement_offered"], "completed": completed, "timely_completions": summary["timely_completions"],
        "dropped": dropped, "admitted": admitted, "incomplete": incomplete, "transport_failures": summary["measurement_outcomes"].get("failed", 0),
        "completion_fraction": completed / summary["measurement_offered"], "drop_fraction": dropped / summary["measurement_offered"],
        "incomplete_fraction": incomplete / admitted if admitted else float("nan"), "timely_goodput_rps": summary["timely_goodput_per_sec"],
        "eventual_throughput_rps": summary["eventual_completion_rate_per_sec"], "e2e_p50_ms": quantile(e2e, 0.5),
        "e2e_p95_ms": quantile(e2e, 0.95), "e2e_p99_ms": quantile(e2e, 0.99),
        "short_e2e_p99_ms": latency("short", "end_to_end_us", "p99"), "long_e2e_p99_ms": latency("long", "end_to_end_us", "p99"),
        "short_queue_p99_ms": latency("short", "queue_wait_us", "p99"), "long_queue_p99_ms": latency("long", "queue_wait_us", "p99"),
        "short_execution_p99_ms": latency("short", "execution_us", "p99"), "long_execution_p99_ms": latency("long", "execution_us", "p99"),
        "short_cpu_p99_ms": latency("short", "execution_cpu_us", "p99"), "long_cpu_p99_ms": latency("long", "execution_cpu_us", "p99"),
        "short_slowdown_p99": latency("short", "end_to_end_us", "p99") / latency("short", "execution_cpu_us", "p99"),
        "long_slowdown_p99": latency("long", "end_to_end_us", "p99") / latency("long", "execution_cpu_us", "p99"),
        "cpu_usage_seconds": delta["usage_usec"] / 1e6, "quota_utilization": delta["usage_usec"] / 1e6 / (wall_s * 1.5),
        "cpu_usec_per_completion": delta["usage_usec"] / max(completed, 1), "nr_periods": delta["nr_periods"],
        "nr_throttled": delta["nr_throttled"], "throttled_period_fraction": delta["nr_throttled"] / max(delta["nr_periods"], 1),
        "throttle_events_per_second": delta["nr_throttled"] / wall_s,
        "throttled_seconds_per_wall_second": delta["throttled_usec"] / 1_000_000 / wall_s,
        "throttled_usec": delta["throttled_usec"], "support_cpu_residual_usec": delta["usage_usec"] - worker_cpu_us,
        "queue_depth_first_half_mean": float(np.mean(queue_depths[:queue_midpoint])),
        "queue_depth_second_half_mean": float(np.mean(queue_depths[queue_midpoint:])),
        "generator_cpu_seconds": generator["process_cpu_time_ns"] / 1e9, "scheduler_p99_us": summary["scheduler_gate"]["p99_lag_us"],
        "write_completion_p99_us": summary["transport_gate"]["p99_write_completion_lag_us"],
        "max_sender_backlog": summary["transport_gate"]["maximum_sender_backlog"],
        "start_package_temp_c": temperatures[0], "max_package_temp_c": max(temperatures),
        "mean_pcore_frequency_ghz": float(np.mean(pcore_frequencies_ghz)),
        "start_wall_unix_ns": manifest["start_wall_unix_ns"], "end_wall_unix_ns": manifest["end_wall_unix_ns"],
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]) if rows else [],
            lineterminator="\n",
        )
        if rows: writer.writeheader(); writer.writerows(rows)


def paired_effects(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    metrics = ("timely_goodput_rps", "e2e_p99_ms", "quota_utilization", "throttled_period_fraction", "short_e2e_p99_ms", "long_e2e_p99_ms", "drop_fraction", "incomplete_fraction")
    lookup = {(row["block"], row["period_ms"], row["workers"], row["load"]): row for row in rows}
    effects = []
    comparisons = []
    for block in (1, 2):
        for period in (10, 100):
            for load in ("moderate", "stress"):
                comparisons.append(("workers_2_minus_1", (block, period, 1, load), (block, period, 2, load)))
        for workers in (1, 2):
            for load in ("moderate", "stress"):
                comparisons.append(("period_100_minus_10", (block, 10, workers, load), (block, 100, workers, load)))
    for name, left_key, right_key in comparisons:
        if left_key not in lookup or right_key not in lookup: continue
        left, right = lookup[left_key], lookup[right_key]
        for metric in metrics:
            left_value, right_value = float(left[metric]), float(right[metric])
            effects.append({"comparison": name, "block": left["block"], "period_ms": left["period_ms"] if name.startswith("workers") else "",
                            "workers": left["workers"] if name.startswith("period") else "", "load": left["load"], "metric": metric,
                            "left_value": left_value, "right_value": right_value, "absolute_difference": right_value - left_value,
                            "relative_difference_percent": (right_value / left_value - 1) * 100 if left_value else float("nan")})
    return effects


def style_axis(ax, ylabel: str) -> None:
    ax.set_ylabel(ylabel); ax.grid(axis="y", alpha=0.25); ax.set_axisbelow(True)


def plot_metric(rows: list[dict], metric: str, ylabel: str, filename: str, log: bool = False) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True, constrained_layout=True)
    colors = {1: "#0072B2", 2: "#D55E00"}
    for ax, load in zip(axes, ("moderate", "stress"), strict=True):
        for workers in (1, 2):
            for period_index, period in enumerate((10, 100)):
                values = [float(row[metric]) for row in rows if row["load"] == load and row["workers"] == workers and row["period_ms"] == period]
                x = period_index + (-0.09 if workers == 1 else 0.09)
                ax.scatter([x] * len(values), values, color=colors[workers], marker="o" if workers == 1 else "s", s=48, label=f"{workers} worker(s)" if period_index == 0 else None)
                if values: ax.hlines(float(np.median(values)), x - 0.06, x + 0.06, color=colors[workers], linewidth=2)
        ax.set_xticks((0, 1), ("10 ms", "100 ms")); ax.set_title(f"{load.capitalize()} ({1200 if load == 'moderate' else 2200}/s)")
        if log: ax.set_yscale("log")
        style_axis(ax, ylabel); ax.legend()
    fig.savefig(FIGURES / f"{filename}.png", dpi=200); fig.savefig(FIGURES / f"{filename}.pdf"); plt.close(fig)


def plot_cpu(rows: list[dict]) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(10, 7), sharex=True, constrained_layout=True)
    colors = {1: "#0072B2", 2: "#D55E00"}
    for column, load in enumerate(("moderate", "stress")):
        for workers in (1, 2):
            for index, period in enumerate((10, 100)):
                subset = [row for row in rows if row["load"] == load and row["workers"] == workers and row["period_ms"] == period]
                x = index + (-0.09 if workers == 1 else 0.09)
                for axis, metric in zip((axes[0, column], axes[1, column]), ("quota_utilization", "throttled_seconds_per_wall_second"), strict=True):
                    values = [float(row[metric]) * 100 for row in subset]; axis.scatter([x] * len(values), values, color=colors[workers], marker="o" if workers == 1 else "s", s=48, label=f"{workers} worker(s)" if index == 0 else None)
                    if values: axis.hlines(float(np.median(values)), x - 0.06, x + 0.06, color=colors[workers], linewidth=2)
        axes[0, column].set_title(load.capitalize()); axes[1, column].set_xticks((0, 1), ("10 ms", "100 ms"))
        for axis in axes[:, column]: axis.grid(axis="y", alpha=0.25); axis.legend()
    axes[0, 0].set_ylabel("Quota utilization (%)"); axes[1, 0].set_ylabel("Aggregate throttled s / wall s (%)")
    fig.savefig(FIGURES / "03_cpu_utilization_throttling.png", dpi=200); fig.savefig(FIGURES / "03_cpu_utilization_throttling.pdf"); plt.close(fig)


def plot_classes_outcomes(rows: list[dict]) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(9, 7.2), sharex=True, constrained_layout=True)
    conditions = [
        (load, period, workers)
        for load in ("moderate", "stress")
        for period in (10, 100)
        for workers in (1, 2)
    ]
    labels = [f"{load[:3].title()}\n{period} ms\n{workers} w" for load, period, workers in conditions]
    for index, (load, period, workers) in enumerate(conditions):
        subset = [
            row
            for row in rows
            if row["load"] == load
            and row["period_ms"] == period
            and row["workers"] == workers
        ]
        axes[0].scatter(
            [index - 0.08] * len(subset),
            [row["short_e2e_p99_ms"] for row in subset],
            color="#0072B2",
            marker="o",
            label="Short" if index == 0 else None,
        )
        axes[0].scatter(
            [index + 0.08] * len(subset),
            [row["long_e2e_p99_ms"] for row in subset],
            color="#D55E00",
            marker="s",
            label="Long" if index == 0 else None,
        )
        axes[1].scatter(
            [index - 0.08] * len(subset),
            [row["drop_fraction"] * 100 for row in subset],
            color="#CC79A7",
            marker="o",
            label="Dropped / offered" if index == 0 else None,
        )
        axes[1].scatter(
            [index + 0.08] * len(subset),
            [row["incomplete_fraction"] * 100 for row in subset],
            color="#666666",
            marker="s",
            label="Incomplete / admitted" if index == 0 else None,
        )
    axes[0].set_yscale("log")
    axes[0].set_ylabel("End-to-end p99 (ms, completed)")
    axes[1].set_ylabel("Request outcome (%)")
    axes[1].set_xticks(np.arange(len(conditions)), labels, fontsize=8)
    for axis in axes:
        axis.grid(axis="y", alpha=0.25)
        axis.legend(ncol=2)
    fig.savefig(FIGURES / "04_class_latency_outcomes.png", dpi=200)
    fig.savefig(FIGURES / "04_class_latency_outcomes.pdf")
    plt.close(fig)


def provenance() -> dict:
    attempts = []
    for run in sorted(ATTEMPTS.iterdir()):
        if not run.is_dir(): continue
        files = [{"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in sorted(run.iterdir()) if path.is_file()]
        attempts.append({"run_id": run.name, "files": files, "total_bytes": sum(item["bytes"] for item in files)})
    return {"schema_version": 1, "hash": "SHA-256", "attempt_count": len(attempts), "total_bytes": sum(item["total_bytes"] for item in attempts), "attempts": attempts}


def main() -> int:
    FIGURES.mkdir(parents=True, exist_ok=True); PROCESSED.mkdir(parents=True, exist_ok=True)
    matrix = load(ROOT / "experiment_matrix.json"); cells = {cell["cell_id"]: cell for cell in matrix["cells"]}
    rows = [run_metrics(row, cells) for row in valid_index()]
    rows.sort(key=lambda row: (row["block"], row["load"], row["period_ms"], row["workers"]))
    effects = paired_effects(rows)
    write_csv(ROOT / "run_level_metrics.csv", rows); write_csv(ROOT / "paired_effects.csv", effects)
    plot_metric(rows, "timely_goodput_rps", "Timely goodput (requests/s)", "01_throughput")
    plot_metric(rows, "e2e_p99_ms", "End-to-end p99 (ms, completed)", "02_end_to_end_p99", log=True)
    plot_cpu(rows); plot_classes_outcomes(rows)
    (ROOT / "dataset_provenance.json").write_text(json.dumps(provenance(), indent=2) + "\n")
    print(f"analyzed {len(rows)} valid runs and wrote {len(effects)} paired effects")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
