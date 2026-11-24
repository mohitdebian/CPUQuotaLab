#!/usr/bin/env python3
"""Generate the immutable five-block CPUQuotaLab schedule."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random


MASTER_SEED = 2027112401


def primary_cell(block: int, workload: str, load: str, period: int, workers: int,
                 request_seed: int, lead_in_ms: int) -> dict[str, object]:
    rate = {"mixed": {"moderate": 1200, "stress": 2200},
            "uniform": {"moderate": 1800, "stress": 3200}}[workload][load]
    queue = {"mixed": 550, "uniform": 800}[workload]
    cell_id = f"primary-b{block:02d}-{workload}-{load}-p{period}-w{workers}"
    return {
        "cell_id": cell_id, "stage": "initial16" if block <= 2 and workload == "mixed" and workers in (1, 2) else "future",
        "experiment": "primary", "block": block, "workload": workload, "load": load,
        "period_ms": period, "workers": workers, "quota_cpus": 1.5,
        "rate_per_sec": rate, "queue_capacity": queue, "request_seed": request_seed,
        "lead_in_ms": lead_in_ms,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("experiment_matrix.json"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and not args.force:
        raise FileExistsError(f"refusing to replace {args.output}")
    rng = random.Random(MASTER_SEED)
    cells: list[dict[str, object]] = []
    full_order = 0
    for block in range(1, 6):
        groups = [(workload, load) for workload in ("mixed", "uniform") for load in ("moderate", "stress")]
        rng.shuffle(groups)
        for workload, load in groups:
            request_seed = MASTER_SEED + block * 100 + (0 if workload == "mixed" else 20) + (0 if load == "moderate" else 1)
            lead_in_ms = 200 + rng.randrange(100)
            conditions = [(period, workers) for period in (10, 100) for workers in (1, 2, 8)]
            rng.shuffle(conditions)
            for period, workers in conditions:
                full_order += 1
                cell = primary_cell(block, workload, load, period, workers, request_seed, lead_in_ms)
                cell["full_order"] = full_order
                cells.append(cell)
        for load, rate in (("moderate", 3200), ("stress", 4300)):
            request_seed = MASTER_SEED + block * 100 + 40 + (0 if load == "moderate" else 1)
            lead_in_ms = 200 + rng.randrange(100)
            workers_order = [2, 8]
            rng.shuffle(workers_order)
            for workers in workers_order:
                full_order += 1
                cells.append({
                    "cell_id": f"anchor-b{block:02d}-{load}-p100-w{workers}", "stage": "future",
                    "experiment": "anchor", "block": block, "workload": "uniform", "load": load,
                    "period_ms": 100, "workers": workers, "quota_cpus": 2.0,
                    "rate_per_sec": rate, "queue_capacity": 1075,
                    "request_seed": request_seed, "lead_in_ms": lead_in_ms, "full_order": full_order,
                })
    initial = [cell for cell in cells if cell["stage"] == "initial16"]
    rng.shuffle(initial)
    for order, cell in enumerate(initial, 1):
        cell["stage_order"] = order
    document = {
        "schema_version": 1, "protocol_version": "1.0", "master_seed": MASTER_SEED,
        "generated_before_confirmatory_outcomes": True,
        "design": {"primary_runs": 120, "anchor_runs": 20, "total_runs": 140, "initial_stage_runs": 16},
        "frozen_common": {
            "warmup_seconds": 5, "measurement_seconds": 90, "drain_timeout_seconds": 10,
            "short_iterations": 76000, "long_iterations": 1140000, "uniform_iterations": 141000,
            "short_fraction": 0.9, "server_cpus": "0-7", "generator_cpus": "8-11",
            "writer_cpu": 9, "reader_cpu": 10, "scheduler_cpu": None, "spin_threshold_us": 500,
        },
        "cells": cells,
    }
    args.output.write_text(json.dumps(document, indent=2) + "\n")
    print(f"wrote {len(cells)} cells ({len(initial)} initial) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
