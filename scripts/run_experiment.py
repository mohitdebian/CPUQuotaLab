#!/usr/bin/env python3
"""Run one immutable CPUQuotaLab experiment attempt.

The script uses only Python's standard library. It verifies affinity and cgroup
separation while the two Rust processes run. It never deletes an existing run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_optional(path: Path) -> str | None:
    try:
        return path.read_text().strip()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def environment_sample() -> dict[str, object]:
    temperatures = {}
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        temperatures[zone.name] = {
            "type": read_optional(zone / "type"),
            "temp_millicelsius": read_optional(zone / "temp"),
        }
    frequencies = {
        cpu.name: read_optional(cpu / "cpufreq" / "scaling_cur_freq")
        for cpu in sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*"))
    }
    power = {}
    for supply in sorted(Path("/sys/class/power_supply").glob("*")):
        power[supply.name] = {
            "type": read_optional(supply / "type"),
            "online": read_optional(supply / "online"),
            "status": read_optional(supply / "status"),
            "capacity_percent": read_optional(supply / "capacity"),
        }
    return {
        "wall_unix_ns": time.time_ns(),
        "monotonic_ns": time.monotonic_ns(),
        "loadavg": read_optional(Path("/proc/loadavg")),
        "cpu_pressure": read_optional(Path("/proc/pressure/cpu")),
        "memory_pressure": read_optional(Path("/proc/pressure/memory")),
        "io_pressure": read_optional(Path("/proc/pressure/io")),
        "cpu_frequencies_khz": frequencies,
        "temperatures": temperatures,
        "power_supplies": power,
        "platform_profile": read_optional(Path("/sys/firmware/acpi/platform_profile")),
        "scaling_governors": {
            cpu.name: read_optional(cpu / "cpufreq" / "scaling_governor")
            for cpu in sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*"))
        },
    }


def git_metadata(workdir: Path) -> dict[str, object]:
    def run(*args: str) -> str | None:
        result = subprocess.run(
            ["git", *args], cwd=workdir, text=True, capture_output=True, check=False
        )
        return result.stdout.strip() if result.returncode == 0 else None

    return {
        "revision": run("rev-parse", "HEAD"),
        "branch": run("branch", "--show-current"),
        "status_porcelain": run("status", "--porcelain", "--untracked-files=no"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, default=Path("target/release/cpu-quota-lab"))
    parser.add_argument("--output-root", type=Path, default=Path("results/pilot"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--quota-cpus", type=float, default=1.5)
    parser.add_argument("--period-ms", type=int, choices=(10, 100), default=100)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--queue-capacity", type=int, default=256)
    parser.add_argument("--workload", choices=("uniform", "mixed"), required=True)
    parser.add_argument("--rate", type=float, required=True)
    parser.add_argument("--warmup-seconds", type=float, default=5.0)
    parser.add_argument("--measurement-seconds", type=float, default=30.0)
    parser.add_argument("--lead-in-ms", type=int, default=200)
    parser.add_argument("--spin-threshold-us", type=int, default=100)
    parser.add_argument("--max-sender-backlog", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--short-iterations", type=int, default=50_000)
    parser.add_argument("--long-iterations", type=int, default=500_000)
    parser.add_argument("--uniform-iterations", type=int, default=95_000)
    parser.add_argument("--server-cpus", default="0-7")
    parser.add_argument("--generator-cpus", default="8-11")
    parser.add_argument("--scheduler-cpu", type=int)
    parser.add_argument("--writer-cpu", type=int, default=9)
    parser.add_argument("--reader-cpu", type=int, default=10)
    parser.add_argument("--ready-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--drain-timeout-seconds", type=int, default=10)
    return parser.parse_args()


def cgroup_of(pid: int) -> str:
    for line in Path(f"/proc/{pid}/cgroup").read_text().splitlines():
        if line.startswith("0::"):
            return line[3:]
    raise RuntimeError(f"no unified cgroup for PID {pid}")


def expand_cpu_list(spec: str) -> set[int]:
    cpus: set[int] = set()
    for part in spec.split(","):
        if "-" in part:
            start, end = (int(value) for value in part.split("-", 1))
            cpus.update(range(start, end + 1))
        else:
            cpus.add(int(part))
    return cpus


def task_affinities(pid: int) -> dict[int, set[int]]:
    result: dict[int, set[int]] = {}
    for task in Path(f"/proc/{pid}/task").iterdir():
        status = (task / "status").read_text().splitlines()
        line = next(value for value in status if value.startswith("Cpus_allowed_list:"))
        result[int(task.name)] = expand_cpu_list(line.split(":", 1)[1].strip())
    return result


def assert_affinity(pid: int, expected: set[int], role: str) -> dict[int, list[int]]:
    observed = task_affinities(pid)
    mismatches = {tid: cpus for tid, cpus in observed.items() if cpus != expected}
    if mismatches:
        raise RuntimeError(f"{role} affinity mismatch: {mismatches}")
    return {tid: sorted(cpus) for tid, cpus in observed.items()}


def assert_affinity_within(pid: int, allowed: set[int], role: str) -> dict[int, list[int]]:
    observed = task_affinities(pid)
    mismatches = {
        tid: cpus for tid, cpus in observed.items() if not cpus or not cpus.issubset(allowed)
    }
    if mismatches:
        raise RuntimeError(f"{role} affinity escaped allowed CPUs: {mismatches}")
    return {tid: sorted(cpus) for tid, cpus in observed.items()}


def wait_for_affinity(
    process: subprocess.Popen[bytes], expected: set[int], role: str, timeout: float
) -> dict[int, list[int]]:
    """Allow the taskset launcher to exec before enforcing steady-state affinity."""
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"{role} exited before affinity validation with status {process.returncode}"
            )
        try:
            return assert_affinity_within(process.pid, expected, role)
        except (FileNotFoundError, RuntimeError) as error:
            last_error = error
            time.sleep(0.01)
    raise RuntimeError(f"{role} affinity did not stabilize: {last_error}")


def wait_for(path: Path, process: subprocess.Popen[bytes], timeout: float) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        if process.poll() is not None:
            raise RuntimeError(f"server exited before readiness with status {process.returncode}")
        time.sleep(0.05)
    raise TimeoutError(f"timed out waiting for {path}")


def main() -> int:
    args = parse_args()
    start_wall = time.time_ns()
    run_dir = args.output_root.resolve() / args.run_id
    binary_path = args.binary.resolve()
    if not binary_path.is_file():
        raise FileNotFoundError(f"benchmark binary not found: {binary_path}")
    run_dir.mkdir(parents=True, exist_ok=False)
    socket_path = Path(f"/tmp/cpuquota-lab-{os.getpid()}-{args.run_id}.sock")
    manifest: dict[str, object] = {
        "schema_version": 1,
        "run_id": args.run_id,
        "status": "starting",
        "start_wall_unix_ns": start_wall,
        "arguments": vars(args) | {"binary": str(args.binary), "output_root": str(args.output_root)},
        "socket_path": str(socket_path),
        "orchestrator_pid": os.getpid(),
        "orchestrator_cgroup": cgroup_of(os.getpid()),
        "binary_sha256": sha256_file(binary_path),
        "python_version": sys.version,
        "source": git_metadata(Path(__file__).resolve().parent.parent),
        "environment_start": environment_sample(),
        "environment_samples": [],
        "affinity_checks": [],
    }
    manifest_path = run_dir / "manifest.json"

    quota_usec = round(args.quota_cpus * args.period_ms * 1000)
    quota_percent = args.quota_cpus * 100.0
    server_cmd = [
        "systemd-run", "--user", "--scope", "--quiet",
        f"-p", f"CPUQuota={quota_percent}%",
        f"-p", f"CPUQuotaPeriodSec={args.period_ms}ms",
        "taskset", "-c", args.server_cpus,
        str(binary_path), "server",
        "--socket", str(socket_path),
        "--output-dir", str(run_dir),
        "--workers", str(args.workers),
        "--queue-capacity", str(args.queue_capacity),
        "--drain-timeout-seconds", str(args.drain_timeout_seconds),
        "--short-iterations", str(args.short_iterations),
        "--long-iterations", str(args.long_iterations),
        "--uniform-iterations", str(args.uniform_iterations),
    ]
    generator_cmd = [
        "taskset", "-c", args.generator_cpus,
        str(binary_path), "generator",
        "--socket", str(socket_path),
        "--output-dir", str(run_dir),
        "--workload", args.workload,
        "--rate", str(args.rate),
        "--warmup-seconds", str(args.warmup_seconds),
        "--measurement-seconds", str(args.measurement_seconds),
        "--lead-in-ms", str(args.lead_in_ms),
        "--spin-threshold-us", str(args.spin_threshold_us),
        "--max-sender-backlog", str(args.max_sender_backlog),
        "--writer-cpu", str(args.writer_cpu),
        "--reader-cpu", str(args.reader_cpu),
        "--seed", str(args.seed),
    ]
    if args.scheduler_cpu is not None:
        generator_cmd.extend(["--scheduler-cpu", str(args.scheduler_cpu)])
    manifest["expected_cpu_max"] = f"{quota_usec} {args.period_ms * 1000}"
    manifest["server_command"] = server_cmd
    manifest["generator_command"] = generator_cmd
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    server_stdout = (run_dir / "server.stdout.log").open("wb")
    server_stderr = (run_dir / "server.stderr.log").open("wb")
    generator_stdout = (run_dir / "generator.stdout.log").open("wb")
    generator_stderr = (run_dir / "generator.stderr.log").open("wb")
    server = None
    generator = None
    try:
        server = subprocess.Popen(server_cmd, stdout=server_stdout, stderr=server_stderr)
        ready_path = run_dir / "server-ready.json"
        wait_for(ready_path, server, args.ready_timeout_seconds)
        ready = json.loads(ready_path.read_text())
        server_pid = int(ready["pid"])
        server_cgroup = cgroup_of(server_pid)
        if server_cgroup == manifest["orchestrator_cgroup"]:
            raise RuntimeError("server and orchestrator unexpectedly share a cgroup")
        expected_server = expand_cpu_list(args.server_cpus)
        expected_generator = expand_cpu_list(args.generator_cpus)
        check = {
            "monotonic_ns": time.monotonic_ns(),
            "server": assert_affinity(server_pid, expected_server, "server"),
            "server_cgroup": server_cgroup,
        }
        manifest["affinity_checks"].append(check)  # type: ignore[union-attr]

        generator = subprocess.Popen(generator_cmd, stdout=generator_stdout, stderr=generator_stderr)
        initial_generator_affinity = wait_for_affinity(
            generator, expected_generator, "generator", 1.0
        )
        initial_generator_cgroup = cgroup_of(generator.pid)
        if initial_generator_cgroup == server_cgroup:
            raise RuntimeError("generator entered the restricted server scope")
        manifest["affinity_checks"].append(  # type: ignore[union-attr]
            {
                "monotonic_ns": time.monotonic_ns(),
                "server": assert_affinity(server_pid, expected_server, "server"),
                "server_cgroup": cgroup_of(server_pid),
                "generator": initial_generator_affinity,
                "generator_cgroup": initial_generator_cgroup,
            }
        )
        next_environment_sample = time.monotonic()
        while generator.poll() is None:
            server_status_during_generator = server.poll()
            if server_status_during_generator not in (None, 0):
                raise RuntimeError(
                    "server failed while generator was active with status "
                    f"{server_status_during_generator}"
                )
            current = {
                "monotonic_ns": time.monotonic_ns(),
                "generator": assert_affinity_within(
                    generator.pid, expected_generator, "generator"
                ),
                "generator_cgroup": cgroup_of(generator.pid),
            }
            if server_status_during_generator is None:
                current["server"] = assert_affinity(
                    server_pid, expected_server, "server"
                )
                current["server_cgroup"] = cgroup_of(server_pid)
            else:
                current["server_exit_status"] = server_status_during_generator
            if current["generator_cgroup"] == server_cgroup:
                raise RuntimeError("generator entered the restricted server scope")
            manifest["affinity_checks"].append(current)  # type: ignore[union-attr]
            if time.monotonic() >= next_environment_sample:
                manifest["environment_samples"].append(  # type: ignore[union-attr]
                    environment_sample()
                )
                next_environment_sample += 1.0
            time.sleep(0.2)
        if generator.returncode != 0:
            raise RuntimeError(f"generator exited with status {generator.returncode}")
        server_status = server.wait(timeout=15)
        if server_status != 0:
            raise RuntimeError(f"server exited with status {server_status}")
        summary = json.loads((run_dir / "server-summary.json").read_text())
        observed_cpu_max = summary["snapshots"]["server_start"]["cpu_max"]
        if observed_cpu_max != manifest["expected_cpu_max"]:
            raise RuntimeError(
                f"cpu.max mismatch: expected {manifest['expected_cpu_max']}, got {observed_cpu_max}"
            )
        manifest["status"] = "complete"
    except Exception as error:
        manifest["status"] = "failed"
        manifest["failure"] = repr(error)
        if generator is not None and generator.poll() is None:
            generator.terminate()
        if server is not None and server.poll() is None:
            server.terminate()
        raise
    finally:
        manifest["end_wall_unix_ns"] = time.time_ns()
        manifest["environment_end"] = environment_sample()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        server_stdout.close()
        server_stderr.close()
        generator_stdout.close()
        generator_stderr.close()
        if socket_path.exists():
            socket_path.unlink()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"run_experiment.py: {exc}", file=sys.stderr)
        raise SystemExit(1)
