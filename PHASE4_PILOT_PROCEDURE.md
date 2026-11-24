# Proposed Phase 4 Pilot Procedure

**Status:** Proposed for researcher review; executing this pilot does not authorize confirmatory collection.

## 1. Preflight and apparatus checks

1. Rebuild with the pinned release toolchain and rerun formatter, Clippy, and all tests.
2. Capture kernel, systemd, CPU topology, SMT siblings, online CPUs, frequency policy, thermal sensors, cgroup mount/controller state, Rust versions, Git revision/diff, and Python/NumPy/Matplotlib versions.
3. Reconfirm P-core server mask `0-7` and E-core generator mask `8-11`. Run one short attempt for each period and require every repeated thread-affinity and cgroup-separation assertion to pass.
4. Repeat the sustained CPU-accounting check in the Rust server scope. Require measured quota utilization within ±2% of the configured limit after excluding startup, and verify the expected order of `nr_periods` for 10 ms versus 100 ms. This tolerance is an apparatus gate, not a performance claim.
5. Run a deliberate queue-overload check and reconcile, exactly, `offered = completed + dropped + incomplete + socket-write failures` for measurement-tagged requests.

## 2. Work-cost calibration

Use the release binary, one worker, an unrestricted or nonbinding two-CPU scope, low offered load, and enough requests for stable execution-duration estimates. Adjust only iteration counts.

- Choose short iterations for approximately 0.5 ms median execution.
- Choose long iterations for approximately 5 ms and confirm it is about 10× short.
- Set uniform iterations exactly to `round(0.9 × short + 0.1 × long)`.
- Run at least three calibration batches of at least 10,000 requests each. Record median, p95, coefficient of variation, temperature, frequency information available to the process, and checksums.
- Freeze one iteration triplet. Do not recalibrate after inspecting confirmatory outcomes.

Instrumentation overhead should be estimated with a minimal-work configuration and reported, but never subtracted from observed request latency unless a correction rule is approved before confirmatory collection.

## 3. Generator timing and backpressure calibration

For every candidate offered rate, run the generator on CPUs `8-11` while the server is both lightly loaded and deliberately slow. Confirm that intended times remain an arithmetic sequence even when socket writes slow down.

Require, per run:

- median absolute scheduler lag ≤25 µs;
- p99 lag ≤`max(100 µs, 0.10 × inter-arrival interval)`;
- no more than 0.1% later than one interval;
- intended count equals scheduled count unless an explicit backlog abort occurs;
- no writer backlog trend under a scientifically usable rate; and
- generator process CPU utilization leaves adequate E-core headroom.

Choose and freeze `spin_threshold_us` and `max_sender_backlog`. The ceiling must be finite and low enough to expose sustained socket backpressure rather than absorb an entire run in memory. Any abort invalidates the attempt but its records remain.

## 4. Capacity sweeps

Use short exploratory runs first, then repeat points near the boundary with 30-second measurement windows.

For each combination of workload (`uniform`, `mixed`) and period (10, 100 ms) at 1.5 CPUs:

1. Coarsely sweep common offered rates with one and two workers.
2. Refine around the first queue growth/drop boundary in steps no larger than 5%.
3. Repeat the highest apparently stable point and its neighboring point three times.
4. Call a point stable only if admission ≥99.9%, incomplete ≤0.1%, timing passes, and queue occupancy shows no sustained second-half growth.
5. Record `S_floor` and `S_ceil` as tested-rate intervals, not exact physical constants.

Select one moderate and one capacity-stress rate per workload, shared across both periods and every worker policy, using the formulas in `METHODOLOGY.md`. The stress condition must expose one-worker underutilization where the measured capacities permit it. If it overloads two workers too, say so before freezing; do not discard the condition or hide drops.

For the two-CPU conceptual anchor, separately estimate `S_anchor,2` and `S_anchor,8` at 100 ms with uniform work. Freeze a moderate rate at no more than 70% of the smaller capacity and a stress rate at 90% of the smaller tested stable capacity. Never tune the rate by anchor worker count.

## 5. Queue, duration, and percentile reliability

Set provisional queue capacity to `clamp(ceil(0.25 × R_stress), 256, 4096)` independently for each workload, then keep it fixed across periods and workers for that workload. Verify explicit drops at the boundary.

For mixed work, estimate the completed long-request rate at the slowest non-overloaded planned cell. Choose one measurement duration per workload as:

`ceil(10,000 / completed_long_requests_per_second)`, clamped to 30–120 seconds.

Every individual non-overloaded mixed run—not merely the aggregate five-run cell—must complete at least 10,000 long requests. At that minimum, approximately 100 observations occupy the upper 1% of the long class, so per-run p99 is usable descriptively but remains noisy. If a prespecified overloaded stress cell cannot reach the target by 120 seconds, retain it and label its class p99 exploratory and conditional on completion.

Recalculate the final wall-time budget after duration selection. Across 140 runs, the protocol envelope is 1.75 hours at 30-second measurements to 5.25 hours at 120-second measurements before setup, cooling, and retry overhead; a 90-second measurement implies about 4.1 timed hours.

## 6. Materiality and freeze

Before examining confirmatory comparisons, use pilot repeat variation and measurement resolution to decide whether the provisional absolute p99 floor of 1 ms is defensible. Keep the approved 5% throughput and 10% latency relative thresholds unless a documented calibration reason requires a change. Any change must refer to apparatus noise or scale, not to which hypothesis it favors.

Create a versioned, researcher-approved protocol addendum containing:

- exact iteration counts and observed calibration distributions;
- moderate/stress rates for primary and anchor experiments;
- queue capacities, measurement durations, warm-up/drain values;
- generator spin/backlog settings and timing-validation evidence;
- randomized block seed, per-run arrival-phase offsets, and request seeds;
- final materiality thresholds;
- software revision, tool versions, output schema version, and hashes; and
- a statement that pilot directories are excluded from confirmatory analysis.

Only after that addendum is approved and frozen may the 140-run confirmatory matrix start.
