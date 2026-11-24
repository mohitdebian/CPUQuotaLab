#!/usr/bin/env python3
"""Resumable runner for the predeclared Phase 5 initial subset."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parent.parent
ATTEMPTS = ROOT / "results" / "confirmatory" / "attempts"
PROGRESS = ROOT / "experiment_progress.json"
RUN_INDEX = ROOT / "run_index.csv"
INVALID_INDEX = ROOT / "invalid_attempts.csv"
EXPECTED_BINARY_SHA256 = "560be7281c580a4fc0e4bc521269f75d50ac54f3940e300d68042637b889e095"
MAX_ATTEMPTS_PER_CELL = 2


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()


def read(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except OSError:
        return None


def package_temp_c() -> float | None:
    for zone in Path("/sys/class/thermal").glob("thermal_zone*"):
        if read(zone / "type") == "x86_pkg_temp":
            value = read(zone / "temp")
            return float(value) / 1000 if value else None
    return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def environment_valid(manifest: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    samples = [manifest["environment_start"], *manifest["environment_samples"], manifest["environment_end"]]
    for sample in samples:
        if sample["power_supplies"].get("ACAD", {}).get("online") != "1":
            reasons.append("AC not continuously online")
            break
    if any(sample.get("platform_profile") != "performance" for sample in samples):
        reasons.append("platform profile was not continuously performance")
    start_temps = manifest["environment_start"]["temperatures"]
    package = next((entry.get("temp_millicelsius") for entry in start_temps.values() if entry.get("type") == "x86_pkg_temp"), None)
    if package is None or float(package) > 60000:
        reasons.append(f"starting package temperature invalid: {package}")
    return not reasons, reasons


def validate_attempt(run_dir: Path, cell: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    required = ("manifest.json", "requests.ndjson", "server-summary.json", "generator-summary.json", "derived-summary.json")
    missing = [name for name in required if not (run_dir / name).is_file()]
    if missing:
        return False, [f"missing files: {', '.join(missing)}"]
    manifest = load_json(run_dir / "manifest.json")
    summary = load_json(run_dir / "derived-summary.json")
    server = load_json(run_dir / "server-summary.json")
    generator = load_json(run_dir / "generator-summary.json")
    if manifest.get("status") != "complete": reasons.append(f"orchestrator status {manifest.get('status')}")
    if manifest.get("binary_sha256") != EXPECTED_BINARY_SHA256: reasons.append("binary SHA-256 mismatch")
    if server["snapshots"]["server_start"]["cpu_max"] != manifest["expected_cpu_max"]: reasons.append("cpu.max mismatch")
    if server["snapshots"]["server_start"].get("cpu_max_burst") != "0": reasons.append("cpu.max.burst mismatch")
    env_ok, env_reasons = environment_valid(manifest)
    if not env_ok: reasons.extend(env_reasons)
    if not summary.get("provisional_generator_valid"): reasons.append("generator timing/backpressure gate failed")
    if sum(summary["measurement_outcomes"].values()) != summary["measurement_offered"]: reasons.append("measurement outcomes do not reconcile")
    if generator.get("planned_requests") != generator.get("scheduled_requests") + generator.get("unissued_requests"): reasons.append("generator planned count does not reconcile")
    if cell["load"] == "moderate" and summary.get("by_class", {}).get("long", {}).get("outcomes", {}).get("completed", 0) < 10000: reasons.append("non-overloaded long-class count below 10,000")
    return not reasons, reasons


def write_state(rows: list[dict], started: str) -> None:
    fields = ["cell_id", "attempt", "run_id", "status", "valid", "reasons", "started_at", "ended_at", "elapsed_seconds", "bytes"]
    with RUN_INDEX.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    invalid = [row for row in rows if row["status"] == "complete" and not row["valid"]]
    with INVALID_INDEX.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(invalid)
    valid_cells = {row["cell_id"] for row in rows if row["valid"]}
    progress = {
        "schema_version": 1, "protocol_version": "1.0", "started_at": started, "updated_at": now(),
        "target_cells": 16, "valid_cells": len(valid_cells), "attempts": len(rows),
        "invalid_attempts": len(invalid), "remaining_cells": 16 - len(valid_cells),
        "finite_retry_policy": {"maximum_attempts_per_cell": MAX_ATTEMPTS_PER_CELL, "action_after_repeated_failure": "stop"},
    }
    PROGRESS.write_text(json.dumps(progress, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=ROOT / "experiment_matrix.json")
    parser.add_argument("--stage", default="initial16")
    args = parser.parse_args()
    matrix = load_json(args.matrix)
    cells = sorted((cell for cell in matrix["cells"] if cell["stage"] == args.stage), key=lambda cell: cell["stage_order"])
    ATTEMPTS.mkdir(parents=True, exist_ok=True)
    existing_rows = []
    if RUN_INDEX.exists():
        with RUN_INDEX.open(newline="") as handle: existing_rows = list(csv.DictReader(handle))
        for row in existing_rows:
            row["attempt"] = int(row["attempt"]); row["valid"] = row["valid"] == "True"
    rows = existing_rows
    started = load_json(PROGRESS).get("started_at", now()) if PROGRESS.exists() else now()
    binary = ROOT / "target" / "release" / "cpu-quota-lab"
    if sha256(binary) != EXPECTED_BINARY_SHA256: raise RuntimeError("release binary does not match frozen SHA-256")
    if shutil.disk_usage(ROOT).free < 4 * 1024**3: raise RuntimeError("less than 4 GiB free")
    for position, cell in enumerate(cells, 1):
        if any(row["cell_id"] == cell["cell_id"] and row["valid"] for row in rows):
            continue
        prior = [row for row in rows if row["cell_id"] == cell["cell_id"]]
        if len(prior) >= MAX_ATTEMPTS_PER_CELL:
            raise RuntimeError(f"retry limit reached for {cell['cell_id']}")
        while True:
            temp = package_temp_c()
            if read(Path("/sys/class/power_supply/ACAD/online")) != "1": raise RuntimeError("AC power is offline")
            if read(Path("/sys/firmware/acpi/platform_profile")) != "performance": raise RuntimeError("platform profile is not performance")
            if temp is not None and temp <= 60.0: break
            print(f"cooling before {cell['cell_id']}: package {temp} C", flush=True); time.sleep(10)
        attempt = len(prior) + 1
        run_id = f"v1-{cell['cell_id']}-a{attempt:02d}"
        print(f"[{position}/16] starting {run_id} at {now()} ({temp:.1f} C)", flush=True)
        command = [sys.executable, str(ROOT / "scripts" / "run_experiment.py"), "--output-root", str(ATTEMPTS),
                   "--run-id", run_id, "--quota-cpus", str(cell["quota_cpus"]), "--period-ms", str(cell["period_ms"]),
                   "--workers", str(cell["workers"]), "--queue-capacity", str(cell["queue_capacity"]),
                   "--workload", str(cell["workload"]), "--rate", str(cell["rate_per_sec"]),
                   "--warmup-seconds", "5", "--measurement-seconds", "90", "--lead-in-ms", str(cell["lead_in_ms"]),
                   "--spin-threshold-us", "500", "--seed", str(cell["request_seed"]),
                   "--short-iterations", "76000", "--long-iterations", "1140000", "--uniform-iterations", "141000",
                   "--server-cpus", "0-7", "--generator-cpus", "8-11", "--writer-cpu", "9", "--reader-cpu", "10",
                   "--drain-timeout-seconds", "10"]
        begin = time.time(); status = "complete"; reasons: list[str] = []
        result = subprocess.run(command, cwd=ROOT, check=False)
        run_dir = ATTEMPTS / run_id
        if result.returncode == 0:
            subprocess.run([sys.executable, str(ROOT / "scripts" / "summarize_run.py"), str(run_dir)], cwd=ROOT, check=True)
            valid, reasons = validate_attempt(run_dir, cell)
        else:
            status = "failed"; valid = False; reasons = [f"orchestrator exit {result.returncode}"]
        size = sum(path.stat().st_size for path in run_dir.rglob("*") if path.is_file()) if run_dir.exists() else 0
        row = {"cell_id": cell["cell_id"], "attempt": attempt, "run_id": run_id, "status": status,
               "valid": valid, "reasons": "; ".join(reasons), "started_at": datetime.fromtimestamp(begin, timezone.utc).astimezone().isoformat(),
               "ended_at": now(), "elapsed_seconds": round(time.time() - begin, 3), "bytes": size}
        rows.append(row); write_state(rows, started)
        print(f"[{position}/16] {run_id}: valid={valid}; {row['reasons'] or 'all gates passed'}", flush=True)
        if not valid and attempt >= MAX_ATTEMPTS_PER_CELL:
            raise RuntimeError(f"repeated validity failure for {cell['cell_id']}: {reasons}")
    write_state(rows, started)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
