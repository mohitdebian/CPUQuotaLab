#!/usr/bin/env python3
"""Independent Phase 6 recomputation from immutable raw confirmatory records."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import statistics

import numpy as np


ROOT = Path(__file__).resolve().parent.parent
ATTEMPTS = ROOT / "results" / "confirmatory" / "attempts"


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def percentile(values: list[float], q: float) -> float:
    return float(np.quantile(np.asarray(values, dtype=np.float64), q, method="linear"))


def main() -> int:
    matrix = {cell["cell_id"]: cell for cell in load(ROOT / "experiment_matrix.json")["cells"]}
    with (ROOT / "run_index.csv").open(newline="") as handle:
        valid = [row for row in csv.DictReader(handle) if row["valid"] == "True"]
    audited = []
    for index in valid:
        cell = matrix[index["cell_id"]]
        run = ATTEMPTS / index["run_id"]
        records = [json.loads(line) for line in (run / "requests.ndjson").read_text().splitlines() if line]
        measurement = [record for record in records if record["request"]["phase"] == "measurement"]
        completed = [record for record in measurement if record["final_outcome"] == "completed"]
        outcomes: dict[str, int] = {}
        for record in measurement:
            outcomes[record["final_outcome"]] = outcomes.get(record["final_outcome"], 0) + 1
        server = load(run / "server-summary.json")
        measurement_end_ns = load(run / "generator-summary.json")["measurement_end_ns"]
        start = server["snapshots"]["measurement_start"]
        end = server["snapshots"]["measurement_end"]
        wall_s = (end["timestamp_ns"] - start["timestamp_ns"]) / 1e9
        delta = {key: end["cpu_stat"][key] - start["cpu_stat"][key] for key in ("usage_usec", "nr_periods", "nr_throttled", "throttled_usec")}
        row: dict[str, object] = {
            "run_id": index["run_id"], "block": cell["block"], "load": cell["load"], "period_ms": cell["period_ms"], "workers": cell["workers"],
            "offered": len(measurement), "completed": outcomes.get("completed", 0),
            "dropped": outcomes.get("dropped_queue_full", 0) + outcomes.get("dropped_queue_closed", 0),
            "incomplete": outcomes.get("incomplete", 0), "failed": outcomes.get("failed", 0),
            "timely_goodput_rps": sum(record["final_outcome"] == "completed" and record["response"]["completion_ns"] < measurement_end_ns for record in measurement) / 90,
            "quota_utilization": delta["usage_usec"] / 1_000_000 / (wall_s * 1.5),
            "throttle_events_per_second": delta["nr_throttled"] / wall_s,
            "throttled_seconds_per_wall_second": delta["throttled_usec"] / 1_000_000 / wall_s,
            "cpu_usec_per_completion": delta["usage_usec"] / max(len(completed), 1),
        }
        queue_depth = [record["response"]["queue_len_at_admission"] for record in measurement if record["response"] is not None]
        midpoint = len(queue_depth) // 2
        row["queue_depth_first_half_mean"] = float(np.mean(queue_depth[:midpoint]))
        row["queue_depth_second_half_mean"] = float(np.mean(queue_depth[midpoint:]))
        for task_class in ("short", "long"):
            selected = [record for record in completed if record["request"]["class"] == task_class]
            response = [record["response"] for record in selected]
            measurements = {
                "e2e_p99_ms": [(item["completion_ns"] - record["request"]["intended_arrival_ns"]) / 1e6 for item, record in zip(response, selected, strict=True)],
                "queue_p99_ms": [(item["execution_start_ns"] - item["admission_ns"]) / 1e6 for item in response],
                "elapsed_execution_p99_ms": [(item["completion_ns"] - item["execution_start_ns"]) / 1e6 for item in response],
                "cpu_execution_p99_ms": [item["execution_cpu_ns"] / 1e6 for item in response],
                "admission_p99_ms": [(item["admission_ns"] - item["server_receive_ns"]) / 1e6 for item in response],
                "scheduler_p99_ms": [(record["request"]["scheduler_emit_ns"] - record["request"]["intended_arrival_ns"]) / 1e6 for record in selected],
                "write_completion_p99_ms": [(record["socket_write_end_ns"] - record["request"]["intended_arrival_ns"]) / 1e6 for record in selected],
            }
            for name, values in measurements.items():
                row[f"{task_class}_{name}"] = percentile(values, 0.99)
        audited.append(row)

    totals = {key: sum(int(row[key]) for row in audited) for key in ("offered", "completed", "dropped", "incomplete", "failed")}
    comparisons = []
    lookup = {(row["block"], row["load"], row["period_ms"], row["workers"]): row for row in audited}
    for block in (1, 2):
        for load_name in ("moderate", "stress"):
            for period in (10, 100):
                left = lookup.get((block, load_name, period, 1)); right = lookup.get((block, load_name, period, 2))
                if left and right:
                    comparisons.append({
                        "block": block, "load": load_name, "period_ms": period,
                        "goodput_relative_percent": (right["timely_goodput_rps"] / left["timely_goodput_rps"] - 1) * 100,
                        "p99_relative_percent": (right["short_e2e_p99_ms"] / left["short_e2e_p99_ms"] - 1) * 100,
                        "overall_p99_relative_percent": None,
                    })
    # Overall p99 is recomputed separately to avoid substituting short-class p99.
    for comparison in comparisons:
        values = []
        for workers in (1, 2):
            row = lookup[(comparison["block"], comparison["load"], comparison["period_ms"], workers)]
            run = ATTEMPTS / row["run_id"]
            records = [json.loads(line) for line in (run / "requests.ndjson").read_text().splitlines() if line]
            e2e = [(record["response"]["completion_ns"] - record["request"]["intended_arrival_ns"]) / 1e6 for record in records if record["request"]["phase"] == "measurement" and record["final_outcome"] == "completed"]
            values.append(percentile(e2e, 0.99))
        comparison["overall_p99_relative_percent"] = (values[1] / values[0] - 1) * 100
    result = {
        "schema_version": 1, "source": "independent recomputation from requests.ndjson, manifests, and server cgroup snapshots",
        "valid_runs": len(audited), "totals": totals,
        "paired_worker_comparisons": len(comparisons),
        "median_goodput_relative_percent": statistics.median(item["goodput_relative_percent"] for item in comparisons),
        "median_overall_p99_relative_percent": statistics.median(item["overall_p99_relative_percent"] for item in comparisons),
        "runs": audited, "worker_comparisons": comparisons,
    }
    (ROOT / "audit_recomputation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("valid_runs", "totals", "paired_worker_comparisons", "median_goodput_relative_percent", "median_overall_p99_relative_percent")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
