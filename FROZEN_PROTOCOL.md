# CPUQuotaLab Frozen Protocol v1.0

**Status:** INITIAL PHASE 5 SUBSET CLOSED; NO FURTHER COLLECTION AUTHORIZED
**Date:** 24 November 2026
**Authorization:** researcher-approved staged collection; remaining 124 runs are not authorized

## 1. Immutable instrument

- collection source revision: `5a3d0aaa22b5619d03055648fa2e8db60b0294e6`;
- benchmark binary SHA-256: `560be7281c580a4fc0e4bc521269f75d50ac54f3940e300d68042637b889e095`;
- calibrated analysis revision: `0e1b0b11078b09e8b30fd8ae3c03ec5582a39ad9`;
- preliminary confirmatory analysis revision: `9623adca150ca48bcf81a5cae41a90c550fcae1d`;
- Rust 1.100.0, Cargo 1.100.0, Rustfmt 1.11.0-stable, Clippy 0.1.100;
- release profile and locked dependencies from `Cargo.toml`/`Cargo.lock`;
- Linux cgroup v2 transient user scopes;
- server allowed CPUs 0–7; generator allowed CPUs 8–11;
- generator writer CPU 9, reader CPU 10, scheduler migratable only within 8–11;
- generator spin threshold 500 µs;
- `cpu.max.burst=0`; no governor, SMT, kernel, or security-setting changes.

Any collection-code, workload, timing, affinity, or analysis-gate change requires a new protocol version and targeted validation.

## 2. Workloads

- short: 76,000 deterministic wrapping-integer iterations;
- long: 1,140,000 iterations;
- mixed: seeded 90% short/10% long sequence;
- uniform: 141,000 iterations, selected for measured CPU-cost equality;
- checksum returned and XOR-accounted for every completion.

The uniform control is not arithmetic iteration equality. Calibration distributions and this distinction must remain visible.

## 3. Quotas, periods, and workers

Primary 1.5-CPU quota:

- 10 ms: `cpu.max = 15000 10000`;
- 100 ms: `cpu.max = 150000 100000`.

Primary native Rust worker counts are 1 (floor), 2 (ceiling), and 8 (allowed/visible baseline).

The conceptual anchor uses 2 CPUs, 100 ms, `cpu.max = 200000 100000`, and 2 or 8 native workers. It is not a faithful Cambridge reproduction. Jeffery et al. primarily use a Rust native-thread `fib(30)` open-loop benchmark for their thread-overcommitment results and use Go for a quota-awareness comparison; CPUQuotaLab's anchor differs in hardware, kernel, work function, duration, and load regime.

## 4. Frozen offered loads

| Experiment | Moderate | Stress | FIFO capacity |
|---|---:|---:|---:|
| Mixed primary | 1,200/s | 2,200/s | 550 |
| Uniform primary | 1,800/s | 3,200/s | 800 |
| Uniform two-CPU anchor | 3,200/s | 4,300/s | 1,075 |

Rates and FIFO sizes are identical across competing worker counts and, for primary runs, both periods. They may not be tuned after inspecting confirmatory outcomes.

## 5. Run timeline and request inclusion

1. Validate binary, source cleanliness, cgroup, quota, affinity, power, profile, and temperature.
2. Run 5 seconds of warm-up; retain records but exclude them from measurement metrics.
3. Run 90 seconds of measurement using absolute monotonic intended arrivals.
4. At `T1`, stop measurement arrivals and send `MeasurementEnd`.
5. Drain until all admitted work resolves or 10 seconds from `T1` expires.
6. Mark queued work not started by the deadline `incomplete`; never silently discard it.
7. Capture final cgroup, process, environment, and accounting state.

Measurement denominators include every request whose intended arrival is in `[T0,T1)`, including transport failure, drop, incomplete, and eventual completion. Timely goodput counts completion before `T1`; eventual throughput counts completion during the allowed drain. Latency percentiles use completed measurement requests and are explicitly conditional when any measurement request drops or remains incomplete.

## 6. Generator validity

Each attempt must have:

- exact reconciliation of planned, unissued, emitted, attempted, written, responded, completed, dropped, incomplete, and failed counts;
- zero transport failures;
- median absolute scheduler lag no more than 25 µs;
- scheduler p99 no more than `max(250 µs, 0.25 × inter-arrival interval)`;
- scheduler emissions later than one interval no more than 1%;
- socket-write-completion p99 no more than the same limit;
- write completions later than one interval no more than 1%;
- maximum sender backlog no more than 32;
- server and generator containment/affinity checks passing at every sample.

Arrivals never wait for responses. Gate failure invalidates an attempt; its directory remains immutable and a replacement receives a new attempt ID.

## 7. Environmental validity

- AC online at start, every one-second environment sample, and end; battery must not report discharging.
- Platform profile `performance` at start, every sample, and end.
- Starting package/CPU temperature no more than 60°C.
- Server threads confined to 0–7 and the requested transient cgroup at every approximately 200 ms placement sample.
- Generator threads confined to 8–11 and never members of the server cgroup at every placement sample.
- Actual `cpu.max` and `cpu.max.burst` exactly match the protocol.
- Record temperature, per-CPU frequency, governor, load, CPU/memory/I/O pressure, power, affinity, and cgroup counters.
- Do not change governor, platform profile, SMT, kernel settings, or host security configuration during collection.

If the temperature rule fails, wait without changing host configuration and create a new attempt. Apply the rule without reference to latency or throughput.

## 8. Matrix, blocking, and seeds

Primary: 2 periods × 3 workers × 2 workloads × 2 loads × 5 repeats = 120 valid runs. Anchor: 2 workers × 2 loads × 5 repeats = 20 valid runs.

Use five randomized complete blocks from master seed `2027112401`. The complete 140-cell schedule is preserved in `experiment_matrix.json`. Within each workload/load/block, randomize the six primary period/worker cells. Reuse the same request seed and arrival phase offset across matched cells. Randomize anchor worker order within load/block. Replacement attempts keep the original cell/seed but receive a new attempt ID and remain linked to the invalid attempt.

Phase 5 initially executes only the 16 cells comprising blocks 1–2, mixed workload, moderate/stress loads, 10/100 ms periods, and 1/2 workers. This staged subset was selected before confirmatory outcomes and remains part of the full design. It does not replace the 140-run plan. At most one replacement is permitted per cell; a second invalid attempt stops collection for investigation.

Pilot, invalid confirmatory attempts, valid confirmatory attempts, and processed outputs remain separately identifiable.

## 9. Sample-size rule

Every individual non-overloaded mixed run must complete at least 10,000 long requests. At the fixed 1,200/s moderate rate and 90 seconds, the pilot completed 10,829. A prespecified stress run that overloads may fail this count; retain it and label long-tail estimates conditional/exploratory rather than extending only that policy's duration.

## 10. Metrics and statistical analysis

Primary throughput is timely goodput. Also report offered, admitted, measurement-window, and eventual completion rates; drop, failure, and incomplete fractions; queue-depth evolution; quota utilization; and throttling counters.

Use intended arrival for end-to-end latency. Separately report scheduler lag, writer-queue delay, socket-write duration, write-to-server-receive delay, admission processing, FIFO queue wait, elapsed execution, and worker-thread CPU execution. Report uniform, short, and long classes separately.

Do not pool requests across runs as independent replicates. For the initial two-block subset, show both runs, median/range, and paired absolute/relative effects; do not claim significance or calculate unreliable confidence intervals. The eventual five-block analysis may add NumPy-seeded paired bootstrap intervals. Retain the approved materiality rules: more than 5% throughput difference; more than 10% p99 latency difference plus at least 1 ms absolute difference. Pilot values do not enter confirmatory estimates.

## 11. CPU accounting

Use target-scope measurement-window deltas for `usage_usec`, `nr_periods`, `nr_throttled`, and `throttled_usec`. Normalize primary quota utilization by 1.5 CPUs and anchor utilization by 2 CPUs. Treat `throttled_usec` as aggregate throttled runqueue time, never direct wall delay. Report all server support-thread CPU inside the same quota.

## 12. Evidence language and activation

Keep theoretical predictions, capability tests, pilot observations, confirmatory results, and interpretation distinct. Report overload, drops, invalid attempts, and negative results. The anchor is conceptual unless original experimental conditions are faithfully reproduced.

Activation prerequisites are complete:

- [x] workloads calibrated and compiler-resistance checked;
- [x] generator emission, write, backlog, and admission timing validated;
- [x] CPU accounting validated at both periods;
- [x] mixed, uniform, and anchor capacities bracketed under AC/performance;
- [x] shared moderate/stress rates and FIFO capacities selected;
- [x] per-run long-class feasibility demonstrated;
- [x] runtime and storage recalculated;
- [x] researcher authorized the predeclared 16-run Phase 5 subset.

The initial stage closed with 15 valid cells and one missing cell after the finite retry limit. The remaining 124 planned cells and any additional replacement require separate explicit authorization.
