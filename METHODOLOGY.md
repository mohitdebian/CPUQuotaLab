# CPUQuotaLab Phase 2 Experimental Protocol

**Status:** Phase 4 complete; proposed protocol v0.2 awaits explicit researcher approval
**Date:** 24 November 2026  
**Applies to:** Pilot, 120-run primary matrix, and 20-run conceptual reproduction anchor

## 1. Scientific objective

Measure how an integer native-worker choice interacts with a 1.5-CPU cgroup v2 quota and 10/100 ms replenishment periods under equal-mean uniform and mixed-duration CPU work. Outcomes are intended-arrival end-to-end tail latency, its queue/execution components, throughput, drops/incompletes, quota utilization, and throttling.

The two-worker-versus-one-worker comparison tests a real floor/ceiling policy trade-off. The eight-worker condition is a quota-unaware baseline. The two-CPU anchor is a **conceptual reproduction** of Jeffery et al.; it does not replicate their hardware, kernel, Fibonacci implementation, complete load regime, or five-second measurement exactly.

## 2. Fixed environment and placement

### Verified topology

- Host: Intel Core i5-12450HX, one socket, eight physical cores, 12 online logical CPUs.
- P-core logical CPUs: `0-7`, in SMT sibling pairs `0-1`, `2-3`, `4-5`, `6-7`; reported maximum 4.4 GHz.
- E-core logical CPUs: `8`, `9`, `10`, `11`, each single-threaded; reported maximum 3.1 GHz.
- SMT is active. All CPUs were online at verification.

The P/E classification is supported by sysfs sibling/frequency data and Intel's 4P+4E specification; the kernel does not expose `topology/core_type` here.

### Process placement

- Launch server through a transient user scope with `systemd-run --user --scope`.
- Restrict server process and all descendants to affinity `0-7`.
- Restrict generator to affinity `8-11` and leave it outside the server scope.
- Keep `cpu.max.burst=0`.
- Do not change governors, SMT, kernel settings, security settings, or system-wide configuration.

### Mandatory containment assertion per run

After server readiness and immediately before measurement:

1. Resolve server and generator unified-cgroup paths from `/proc/<pid>/cgroup`.
2. Require different paths and require the server path to be the expected transient scope.
3. Enumerate `/proc/<server-pid>/task/*/cgroup`; require every server thread to match the server path.
4. Read `cgroup.procs`/`cgroup.threads` where available; require the generator PID absent.
5. Verify server affinity is exactly `0-7` and generator affinity exactly `8-11`.
6. Repeat thread membership at run end. Any failure invalidates the run but does not delete it.

## 3. CPU-quota configurations

Primary:

| Capacity | Period | Required `cpu.max` |
|---:|---:|---|
| 1.5 CPUs | 10 ms | `15000 10000` |
| 1.5 CPUs | 100 ms | `150000 100000` |

Conceptual reproduction anchor: 2 CPUs, 100 ms, `200000 100000`.

The anchor uses a separate pilot at this quota. Estimate stable capacities `S_anchor,2` and `S_anchor,8`, then freeze a common moderate rate no higher than 70% of their minimum and a common stress rate at 90% of their minimum (rounded down to a tested stable rate). If capacities differ by more than 5%, disclose that difference and retain the common lower-capacity rate. Do not choose a different offered rate for each worker policy. This condition is near-capacity stress, not deliberately hidden overload; all drops and incompletes remain visible.

Before each run, read back `cpu.max`, `cpu.max.burst`, and relevant ancestor limits. Abort that attempt on mismatch. Record `sched_cfs_bandwidth_slice_us` (currently 5000 µs).

## 4. Worker policies

- floor: 1 worker at 1.5 CPUs;
- ceiling: 2 workers at 1.5 CPUs;
- visible/allowed: 8 workers, based on allowed logical CPUs and ignoring bandwidth;
- fixed 4: pilot-only unless a non-monotonic or otherwise informative pilot result justifies adding it;
- Rust default: record `std::thread::available_parallelism()` but do not duplicate a fixed-count run merely to relabel it.

Workers are native Rust OS threads. This is comparable in broad mechanism to Jeffery et al.'s Rust native-thread overcommitment benchmark, but not a faithful reproduction. Their separate Go quota comparison concerns `GOMAXPROCS`, which limits simultaneously executing goroutines inside a runtime with garbage collection and background work. Go provides fractional-rounding policy motivation only.

## 5. Request system

### Admission and queue

- One external generator and one server process communicate over a Unix-domain socket.
- Server uses one bounded FIFO queue shared by all workers.
- Queue-full admission is an explicit drop, timestamped and returned to the generator/collector.
- Provisional queue capacity per workload is `clamp(ceil(0.25 × R_stress), 256, 4096)` requests, representing roughly 250 ms of stress-load arrivals. Freeze it after pilot and keep it identical across periods and worker policies for that workload.
- No retries. A retry would change offered load and latency semantics.

### Timing clock

- Use `std::time::Instant` for local scheduling/calibration durations.
- Cross-process serialized timestamps use Linux `clock_gettime(CLOCK_MONOTONIC)` in nanoseconds so generator and server timestamps share one monotonic clock domain.
- A minimal wrapper may require a small `unsafe` FFI call through `libc`; its only invariant is a valid writable `timespec` pointer and a checked return value. Test monotonicity, nonnegative differences, and clock resolution before use.
- Wall-clock time is metadata only, never used for latency.

### Per-request record

`request_id`, seed/sequence index, phase, class, intended arrival, actual submission, admission decision/time, execution start, completion, worker ID, checksum/outcome, and drop/failure reason.

End-to-end latency is `completion - intended_arrival`. Queue wait is `execution_start - admission`. Execution duration is `completion - execution_start`. Submission lag is `actual_submission - intended_arrival`.

## 6. Workload definition and calibration

- Short work target: approximately 0.5 ms unrestricted single-worker CPU time.
- Long work target: approximately 5 ms, about 10× short.
- Mixed sequence: 90% short, 10% long, deterministically seeded.
- Uniform iterations: weighted expected mixed iterations, `0.9S + 0.1L` (approximately 0.95 ms if targets hold).
- Same integer computation and input-generation rules for every class; only iteration count differs.
- Consume a deterministic checksum and use `black_box` to make wholesale elimination unlikely; verify nonzero work cost in the exact release build rather than treating the source construct as an absolute compiler guarantee.

Calibration uses release mode, repeated batches rather than single-call timings, and reports median and dispersion. Freeze iteration counts before confirmatory work. Recalibration after primary data begins is prohibited; a necessary change creates a new protocol/version and dataset.

## 7. Pilot capacity estimation

Pilot data is exploratory and stored separately.

For each workload and period at 1.5 CPUs:

1. Sweep offered rates for one and two workers using the same request sequence principles.
2. Refine around the transition using smaller rate steps.
3. Define a rate as stable only when admission fraction is at least 99.9%, incomplete fraction is at most 0.1%, generator timing passes, and queue occupancy has no sustained upward trend over the final half of measurement.
4. Let `S_floor` and `S_ceil` be the highest stable offered rates for 1 and 2 workers respectively. Record uncertainty/step size; do not present them as exact capacities.

### Frozen offered loads

- **Moderate:** `R_mod ≤ 0.70 × min(S_floor, S_ceil)`.
- **Capacity stress:** choose within `1.10 × S_floor ≤ R_stress ≤ 0.90 × S_ceil` when possible.
- If that interval is empty, choose the smallest tested rate above `1.05 × S_floor`, explicitly state whether two workers also overload, and preserve all drops/incompletes.

Within a workload, the final absolute rate is identical across worker policies. Period-specific capacities may be estimated, but the confirmatory comparison uses a shared rate chosen conservatively across both periods so period is not confounded with offered load.

## 8. Generator timing validation

The generator schedules every request against its intended time; it never waits for the previous response and never shifts future intended times after a delay. This avoids coordinated omission. Late requests are submitted and marked late unless the run is aborting; they are not silently skipped.

The scheduling thread hands messages to an independent socket-writer thread through an internal channel, while a third thread reads responses. Therefore, socket backpressure cannot delay the creation of later intended arrivals and silently create closed-loop behavior. Each request records scheduler emit and socket-write start/end times plus sender backlog. A pilot-frozen backlog ceiling causes an explicit aborted attempt rather than unbounded hidden buffering. The generator records its process CPU clock and every observed thread affinity.

A pilot run is timing-valid only when:

- median absolute submission lag ≤25 µs;
- scheduler and socket-write-completion p99 ≤`max(250 µs, 0.25 × inter-arrival interval)`;
- each fraction later than one entire interval ≤1%;
- maximum sender backlog ≤32 and zero transport failures;
- intended request count exactly matches the configured schedule; and
- generator CPU time and affinity are recorded.

These tolerances bound p99 scheduling error below the provisional 1 ms material-latency floor while acknowledging non-real-time Linux. Failure blocks confirmatory collection. Remedies, in order: improve sleep-then-short-spin scheduling, reduce offered rate, lengthen request service calibration, or declare the load infeasible. No real-time scheduler privileges will be requested.

## 9. Run phases and request inclusion

### Timeline

1. **Setup/readiness:** server starts, workers/monitor initialize, containment checks pass, counters snapshot.
2. **Warm-up:** 5 s at the configured offered load; tagged `warmup`.
3. **Measurement:** contiguous interval `[T0,T1)`; new requests tagged `measurement` by intended arrival time.
4. **Drain:** generator stops creating arrivals at `T1`; server drains for at most 10 s.
5. **Forced close:** remaining requests are marked incomplete with reason; graceful worker shutdown follows.
6. **Final snapshot:** counters, containment, frequency, temperature, manifest status.

Warm-up traffic is not flushed at `T0`, preserving steady-state queue conditions, but warm-up requests never enter measurement-request latency summaries. Their completions are separately countable so boundary behavior remains auditable.

### Measurement duration and class-tail sufficiency

- Frozen-proposal duration: 90 s for every competing policy and workload.
- Each individual non-overloaded mixed run requires at least 10,000 completed long requests, normally implying at least 100,000 total completions. Thus every five-repeat cell normally contains at least 50,000 long completions, but percentiles are still calculated per run. Roughly 100 observations lie in the upper 1% of the long class per run, making p99 descriptive rather than exact.
- Uniform runs require at least 10,000 completions, though duration should normally match the mixed-workload duration to preserve environmental comparability.
- If stress overload prevents 10,000 long completions by 120 s, report the class p99 as exploratory/conditional rather than extending only selected policy cells after seeing outcomes.

### Throughput definitions

- **Offered rate:** measurement-intended requests / measurement duration.
- **Admitted rate:** measurement-tagged admissions / duration.
- **Timely goodput (primary):** measurement-tagged requests completed before `T1` / duration.
- **Window completion rate:** all completions timestamped in `[T0,T1)`, broken down by request phase / duration.
- **Eventual completion rate:** measurement-tagged requests completed by drain deadline / duration.
- **Drop fraction:** measurement-tagged queue-full drops / measurement offered.
- **Incomplete fraction:** admitted measurement requests not completed by drain deadline / admitted measurement requests.

### Latency inclusion

Latency distributions contain measurement-tagged, admitted requests completed by the drain deadline. Dropped requests have an admission outcome, not a fabricated latency. Incomplete requests are right-censored/count outcomes and excluded from percentile computation. When drops or incompletes exist, percentiles are labeled conditional on completion. If incompletes exceed 1% of admitted requests, completion-only p99 is not interpreted as an unconditional service tail.

## 10. System accounting

Take exact pre-warm-up, `T0`, `T1`, and post-drain snapshots of the target scope and observable ancestors.

- Measurement CPU use: `T1 - T0` delta of `usage_usec`.
- Normalized quota utilization: `delta_usage_usec / (measurement_wall_usec × 1.5)` for primary runs.
- Throttled-period fraction: `delta_nr_throttled / delta_nr_periods` for the target scope, undefined if denominator zero.
- `throttled_usec` is aggregated throttled runqueue time and never called wall-clock delay.
- `cpu.stat` bandwidth counters are non-hierarchical; record target and ancestor counters plus `cpu.stat.local` when available.
- Completions per CPU-second uses measurement CPU delta and a clearly matched completion definition.

### Completed sustained validation

A three-second, two-process CPU-bound test produced:

| Period | `cpu.max` | Usage delta | Wall | Normalized utilization | `nr_throttled/nr_periods` |
|---:|---|---:|---:|---:|---:|
| 10 ms | `15000 10000` | 4,511,664 µs | 3.004648 s | 1.001041 | 300/301 |
| 100 ms | `150000 100000` | 4,556,995 µs | 3.027988 s | 1.003305 | 30/31 |

All worker processes shared the transient scope and affinity `0-7`; the outside controller remained in a different cgroup. This validates accounting/containment capability only and will not be mixed with benchmark data.

## 11. Experimental matrix and randomization

Primary: 2 periods × 3 worker counts × 2 workloads × 2 loads × 5 repetitions = 120 runs. Conceptual reproduction: 2 workers × 2 loads × 5 repetitions = 20 runs at 2 CPUs/100 ms/uniform. Four-worker and integer-boundary extensions remain pilot-gated.

With 5 s warm-up, 90 s measurement, and at most 10 s drain, the 140-run timed upper envelope is 4.08 hours. Budget 5–7 operational hours including setup, cooling, checks, and retained replacement attempts; reserve 30 GB free storage.

Use randomized complete blocks. A block fixes workload, load, and repetition seed, then randomizes the six period/worker cells. Rotate block order across workloads/loads with a recorded master seed. Never rerun silently; replacements retain failed attempt IDs and reasons.

## 12. Analysis plan

The independent unit is a run. Compute per-run percentiles with a documented NumPy quantile method and keep raw request records immutable.

- Show every run point, median, IQR/range, paired absolute and relative differences.
- Pair policies within blocks; use NumPy-seeded paired bootstrap intervals and label five-pair uncertainty exploratory.
- Report short and long results separately; do not pool request observations across runs as independent samples.
- Plot latency CDFs only for prespecified representative cells and include drop/incomplete annotations.
- Explore throttling–latency association without causal wording.
- Use Python standard library, NumPy, and Matplotlib initially. Pandas/SciPy are unnecessary unless a later analysis requirement is documented and approved.

## 13. Integrity and evidence labels

- **Established fact:** supported by authoritative documentation or verified topology/interface readings.
- **Theoretical prediction:** mechanism-based expectation or hypothesis, not data.
- **Capability validation:** confirms the apparatus works, not a performance result.
- **Measured observation:** produced by a frozen-protocol run and traceable to raw data.
- **Interpretation:** proposed explanation, explicitly separated from observation.

Negative, overloaded, inconclusive, or contradictory outcomes remain in the dataset/report. Pilot data is never presented as confirmatory.

## 14. Approved and pinned toolchain

The approved official `rustup` procedure was executed without root privilege:

1. The installer was downloaded from `https://sh.rustup.rs` to a temporary file, hashed, and inspected before execution.
2. Stable Rust was installed under the user account with the default profile.
3. `rust-toolchain.toml` pins Rust 1.100.0 and requires Rustfmt and Clippy.
4. Exact versions, hash, timestamps, and the one installation retry/failure mode are recorded in `RESEARCH_LOG.md`.

The installation wrote to `~/.rustup` and `~/.cargo`; no system package or privileged configuration was changed.

## 15. Freeze checklist

Implementation approval and final freeze are distinct. Implementation is complete. Before confirmatory data:

- researcher approves the post-pilot protocol addendum;
- workload costs and materiality threshold are calibrated and frozen;
- offered loads, queue capacity, measurement duration, seeds, and generator timing pass are recorded in a versioned protocol addendum;
- containment/accounting automated checks pass;
- exact compiler profile/flags and output schema are documented;
- pilot results remain isolated from primary results.
