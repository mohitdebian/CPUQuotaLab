#!/usr/bin/env python3
"""Create a run-level summary from immutable CPUQuotaLab request records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    return parser.parse_args()


def percentiles(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"n": 0, "mean": None, "p50": None, "p95": None, "p99": None}
    data = np.asarray(values, dtype=np.float64)
    quantiles = np.quantile(data, [0.50, 0.95, 0.99], method="linear")
    return {
        "n": int(data.size),
        "mean": float(np.mean(data)),
        "p50": float(quantiles[0]),
        "p95": float(quantiles[1]),
        "p99": float(quantiles[2]),
    }


def latency_summary(records: list[dict[str, Any]]) -> dict[str, object]:
    completed = [
        record
        for record in records
        if record["final_outcome"] == "completed" and record["response"] is not None
    ]

    def duration(start: str, end: str) -> list[float]:
        values = []
        for record in completed:
            response = record["response"]
            start_value = response[start]
            end_value = response[end]
            if start_value is not None and end_value is not None:
                values.append((end_value - start_value) / 1_000.0)
        return values

    e2e_us = [
        (record["response"]["completion_ns"] - record["request"]["intended_arrival_ns"])
        / 1_000.0
        for record in completed
    ]
    scheduler_lag_us = [
        (record["request"]["scheduler_emit_ns"] - record["request"]["intended_arrival_ns"])
        / 1_000.0
        for record in records
    ]
    socket_handoff_us = [
        (record["socket_write_end_ns"] - record["request"]["scheduler_emit_ns"]) / 1_000.0
        for record in records
        if record["socket_write_end_ns"] is not None
    ]
    writer_queue_us = [
        (record["socket_write_start_ns"] - record["request"]["scheduler_emit_ns"])
        / 1_000.0
        for record in records
        if record["socket_write_start_ns"] is not None
    ]
    socket_write_us = [
        (record["socket_write_end_ns"] - record["socket_write_start_ns"]) / 1_000.0
        for record in records
        if record["socket_write_start_ns"] is not None
        and record["socket_write_end_ns"] is not None
    ]
    server_from_write_start_us = [
        (record["response"]["server_receive_ns"] - record["socket_write_start_ns"])
        / 1_000.0
        for record in records
        if record["response"] is not None and record["socket_write_start_ns"] is not None
    ]
    server_from_write_end_us = [
        (record["response"]["server_receive_ns"] - record["socket_write_end_ns"])
        / 1_000.0
        for record in records
        if record["response"] is not None and record["socket_write_end_ns"] is not None
    ]
    admission_processing_us = [
        (record["response"]["admission_ns"] - record["response"]["server_receive_ns"])
        / 1_000.0
        for record in completed
        if record["response"]["admission_ns"] is not None
    ]
    execution_cpu_us = [
        record["response"]["execution_cpu_ns"] / 1_000.0
        for record in completed
        if record["response"]["execution_cpu_ns"] is not None
    ]
    return {
        "end_to_end_us": percentiles(e2e_us),
        "queue_wait_us": percentiles(duration("admission_ns", "execution_start_ns")),
        "execution_us": percentiles(duration("execution_start_ns", "completion_ns")),
        "execution_cpu_us": percentiles(execution_cpu_us),
        "scheduler_lag_us": percentiles(scheduler_lag_us),
        "socket_handoff_us": percentiles(socket_handoff_us),
        "writer_queue_us": percentiles(writer_queue_us),
        "socket_write_us": percentiles(socket_write_us),
        "server_receive_from_write_start_us": percentiles(server_from_write_start_us),
        "server_receive_from_write_end_us": percentiles(server_from_write_end_us),
        "admission_processing_us": percentiles(admission_processing_us),
    }


def main() -> int:
    args = parse_args()
    run_dir = args.run_dir.resolve()
    generator = json.loads((run_dir / "generator-summary.json").read_text())
    records = [
        json.loads(line)
        for line in (run_dir / "requests.ndjson").read_text().splitlines()
        if line
    ]
    measurement = [record for record in records if record["request"]["phase"] == "measurement"]
    measurement_seconds = generator["config"]["measurement_seconds"]
    measurement_end = generator["measurement_end_ns"]
    timely = sum(
        record["final_outcome"] == "completed"
        and record["response"]["completion_ns"] < measurement_end
        for record in measurement
    )
    counts: dict[str, int] = {}
    for record in measurement:
        outcome = record["final_outcome"]
        counts[outcome] = counts.get(outcome, 0) + 1

    by_class = {}
    for task_class in ("uniform", "short", "long"):
        selected = [
            record for record in measurement if record["request"]["class"] == task_class
        ]
        if selected:
            by_class[task_class] = {
                "offered": len(selected),
                "outcomes": {
                    outcome: sum(record["final_outcome"] == outcome for record in selected)
                    for outcome in sorted({record["final_outcome"] for record in selected})
                },
                "latency": latency_summary(selected),
            }

    interval_us = 1_000_000.0 / generator["config"]["rate_per_sec"]
    lags = np.asarray(
        [
            (record["request"]["scheduler_emit_ns"] - record["request"]["intended_arrival_ns"])
            / 1_000.0
            for record in measurement
        ],
        dtype=np.float64,
    )
    completed_writes = [
        record for record in measurement if record["socket_write_error"] is None
        and record["socket_write_end_ns"] is not None
    ]
    write_completion_lags = np.asarray(
        [
            (record["socket_write_end_ns"] - record["request"]["intended_arrival_ns"])
            / 1_000.0
            for record in completed_writes
        ],
        dtype=np.float64,
    )
    scheduler_limit_us = max(250.0, 0.25 * interval_us)
    scheduler_gate = {
        "median_absolute_lag_us": float(np.median(np.abs(lags))),
        "p99_lag_us": float(np.quantile(lags, 0.99, method="linear")),
        "fraction_later_than_one_interval": float(np.mean(lags > interval_us)),
        "configured_p99_limit_us": scheduler_limit_us,
    }
    scheduler_gate["passes"] = (
        scheduler_gate["median_absolute_lag_us"] <= 25.0
        and scheduler_gate["p99_lag_us"] <= scheduler_gate["configured_p99_limit_us"]
        and scheduler_gate["fraction_later_than_one_interval"] <= 0.01
    )
    write_limit_us = max(250.0, 0.25 * interval_us)
    transport_gate = {
        "completed_socket_writes": len(completed_writes),
        "transport_failures": sum(record["final_outcome"] == "failed" for record in measurement),
        "maximum_sender_backlog": generator["maximum_observed_sender_backlog"],
        "p99_write_completion_lag_us": (
            float(np.quantile(write_completion_lags, 0.99, method="linear"))
            if write_completion_lags.size else None
        ),
        "fraction_write_completion_later_than_interval": (
            float(np.mean(write_completion_lags > interval_us))
            if write_completion_lags.size else None
        ),
        "configured_p99_limit_us": write_limit_us,
    }
    transport_gate["passes"] = (
        len(completed_writes) == len(measurement)
        and transport_gate["transport_failures"] == 0
        and transport_gate["maximum_sender_backlog"] <= 32
        and transport_gate["p99_write_completion_lag_us"] is not None
        and transport_gate["p99_write_completion_lag_us"] <= write_limit_us
        and transport_gate["fraction_write_completion_later_than_interval"] <= 0.01
    )

    summary = {
        "schema_version": 1,
        "source_run_dir": str(run_dir),
        "quantile_method": "numpy.linear",
        "measurement_offered": len(measurement),
        "measurement_outcomes": counts,
        "timely_completions": timely,
        "timely_goodput_per_sec": timely / measurement_seconds,
        "eventual_completion_rate_per_sec": counts.get("completed", 0)
        / measurement_seconds,
        "scheduler_gate": scheduler_gate,
        "transport_gate": transport_gate,
        "provisional_generator_valid": scheduler_gate["passes"] and transport_gate["passes"],
        "by_class": by_class,
    }
    destination = run_dir / "derived-summary.json"
    destination.write_text(json.dumps(summary, indent=2) + "\n")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
