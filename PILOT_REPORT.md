# CPUQuotaLab Phase 4 Pilot Report

**Date:** 24 November 2026
**Evidence status:** exploratory pilot and apparatus validation only
**Collection revision:** `5a3d0aaa22b5619d03055648fa2e8db60b0294e6`
**Rust binary SHA-256:** `560be7281c580a4fc0e4bc521269f75d50ac54f3940e300d68042637b889e095`
**Analysis revision:** `0e1b0b11078b09e8b30fd8ae3c03ec5582a39ad9`
**Confirmatory collection:** not started

## 1. Result in plain language

A 1.5-CPU quota is a time budget. One native worker can execute on only one logical CPU at a time, so it cannot consume the fractional half CPU. Two workers can use more of the quota, although Linux may throttle them after they spend the budget. This pilot established workloads, offered loads, timing checks, and environmental rules for measuring that trade-off.

The pilot is complete. It supports the following proposed protocol values:

| Workload | Moderate rate | Stress rate | FIFO capacity |
|---|---:|---:|---:|
| Mixed 90/10 | 1,200/s | 2,200/s | 550 |
| Uniform 141,000 iterations | 1,800/s | 3,200/s | 800 |
| Two-CPU conceptual anchor | 3,200/s | 4,300/s | 1,075 |

All competing policies use the same rates, 5-second warm-up, 90-second measurement, and at most 10 seconds of drain. The proposed protocol remains inactive until the researcher approves it. Phase 5 has not begun.

## 2. Source audit and implementation checkpoint

The pre-pilot audit repaired four measurement risks:

1. admission time is captured while holding the FIFO lock, immediately before insertion;
2. an emission ledger gives every scheduled request an auditable completed, dropped, incomplete, failed, or unissued outcome;
3. the drain deadline starts at `MeasurementEnd`, not at a potentially delayed socket EOF; and
4. worker `CLOCK_THREAD_CPUTIME_ID` separates computation CPU time from elapsed execution.

`Mutex<VecDeque<T>>` makes queue operations atomic; `push_back` and `pop_front` provide FIFO admission/removal. Full-queue admission returns immediately rather than blocking. Multiple workers may complete out of order, which is expected and recorded. The deterministic wrapping-integer computation has loop-carried dependencies, passes through `black_box`, and returns a checksum, preventing it from being optimized away.

The validated audit checkpoint is `ae4ea0aef1945789bb4f3c4f929f40d26138fc1a`. Response batching was added in `d7e2679e41700f3c016cae3fdbec1cde8ced2175`. Environment capture, generator role affinity, busy-poll writing, and scheduler migration were then added through collection revision `5a3d0aa...`. Manifests preserve the exact revision, dirty state, binary hash, commands, environment, and cgroup placement.

## 3. Workload calibration

Calibration used release builds, a nonbinding two-CPU/100 ms scope, one worker, 400 requests/s, AC power, and three 10,000-request mixed batches.

| Class | Iterations | Mean worker CPU time across repeats | Target |
|---|---:|---:|---:|
| Short | 76,000 | 0.477–0.482 ms | approximately 0.5 ms |
| Long | 1,140,000 | 5.179–5.211 ms | approximately 5 ms |

The measured 90/10 expected CPU cost was 0.947–0.954 ms. The arithmetic equal-mean value of 182,400 iterations measured 1.067–1.106 ms because iteration cost is not perfectly linear across these loop lengths. Candidate measurements were 1.048 ms at 160,000, 1.006 ms at 145,000, 0.973 ms at 141,000, and 0.922 ms at 137,000 iterations. The proposed uniform control is therefore **141,000 iterations**, chosen for measured CPU-cost matching rather than exact iteration arithmetic.

Elapsed execution was normally only 2–3 µs above worker CPU time at low load. Under contention it can be much larger because elapsed time includes descheduling and quota throttling.

## 4. Measurement overhead

Minimal-work 10,000-request runs at 400/s measured:

| Measure | Per-response flush | Buffered responses |
|---|---:|---:|
| Restricted-scope CPU use | 1.231 s | 1.099 s |
| Restricted CPU/request | approximately 123 µs | approximately 110 µs |
| Worker computation CPU/request | 2.08 µs | 1.91 µs |
| Admission processing mean | 0.27 µs | 0.32 µs |

Removing a flush syscall per response reduced restricted CPU cost by about 11%. Remaining socket I/O, serialization, timestamps, locking, response handling, and support threads consume the same server quota and remain part of the measured system.

## 5. Generator accuracy and backpressure

Every raw record distinguishes intended arrival, scheduler emission, socket-write start, socket-write completion, server receive, and server admission. The scheduler never waits for a response. A dedicated writer busy-polls its in-process channel on E-core logical CPU 9; the reader uses CPU 10; the scheduler may migrate within the allowed E-core set 8–11. This consumes generator-side CPU intentionally, outside the restricted server cgroup.

The final 90-second feasibility run emitted and completed 108,000 measurement requests with no failure. It recorded:

- scheduler-emission p99: 112.252 µs;
- socket-write-completion p99: 125.709 µs;
- scheduler/write fractions later than one interval: 0.504%/0.512%;
- maximum sender backlog: 5; and
- generator process CPU: 146.36 s over approximately 95.6 s wall time.

Short high-rate checks at uniform 3,200/s, mixed 2,000/s, and anchor 4,000/s had write-completion p99 of 10, 17, and 9 µs respectively. Final anchor validations at 4,300/s had 4.7–5.5 µs write p99. A final AC/performance validation at the selected mixed stress rate of 2,200/s completed all 33,000 measurement requests, with scheduler/write p99 of 0.180/8.312 µs, backlog 1, and no failure.

The proposed calibrated validity gate is:

- scheduler median absolute lag no more than 25 µs;
- scheduler and socket-write-completion p99 no more than `max(250 µs, 25% of the inter-arrival interval)`;
- each fraction later than one full interval no more than 1%;
- maximum sender backlog no more than 32;
- zero transport failures and exact request reconciliation.

The 250 µs floor is one quarter of the approved 1 ms latency materiality floor. The 1% late-fraction limit admits rare non-real-time Linux wakeup outliers while still rejecting sustained timing distortion. A failed gate invalidates the attempt but never deletes it.

## 6. Capacity estimates

Capacity is called sustainable only when all arrivals complete, timely goodput tracks offered load, and queue depth does not trend persistently upward. The sweeps used common settings across worker counts and periods; rates were not tuned to favor a policy.

### Mixed workload, 1.5 CPUs

One worker was sustainable at 2,000/s under both periods. Mean admission queue depth was 40.6 then 44.6 at 10 ms and 71.3 then 74.3 at 100 ms. At 2,100/s, drops or growing queues appeared: completion fell to 99.95%/98.67%, with mean queue halves 255.7→324.1 and 390.5→413.0. Two workers completed 2,600/s under both periods with valid generator timing.

Thus the common stable brackets are **2,000–<2,100/s for one worker** and at least **2,600/s for two workers**. The proposed 2,200/s stress rate is exactly 110% of the one-worker stable boundary and below 90% of 2,600/s (2,340/s). The moderate rate remains 1,200/s.

### Uniform workload, 1.5 CPUs

Under continuous AC power and the performance platform profile:

| Workers | Period | Stable rate | Next unstable rate | Evidence at next rate |
|---:|---:|---:|---:|---|
| 1 | 10 ms | 2,600/s | 2,700/s | 99.70% completed; queue 362→698 |
| 1 | 100 ms | 2,600/s | 2,700/s | timely goodput 2,678/s; queue 13→154 |
| 2 | 10 ms | 3,800/s | 4,000/s | 98.61% completed; queue 544→796 |
| 2 | 100 ms | 3,800/s | 4,000/s | 99.69% completed; queue 303→680 |

The proposed uniform moderate rate is 1,800/s, below 70% of the 2,600/s one-worker boundary. The 3,200/s stress rate is above 110% of 2,600/s and below 90% of 3,800/s.

### Two-CPU conceptual anchor

With a two-CPU/100 ms quota and the same 141,000-iteration uniform work, both two and eight workers were sustainable at 4,800/s and unstable at 5,200/s. Proposed rates are 3,200/s moderate and 4,300/s stress. Final validation runs completed every request for both worker counts. At 4,300/s, uniform p99 end-to-end latency was 0.538 ms with two workers and 0.479 ms with eight.

This is a **conceptual reproduction anchor**, not a faithful reproduction of the Cambridge hardware, kernel, workload, duration, or load regime. Jeffery et al. use a Rust native-thread, open-loop `fib(30)` benchmark for their main overcommitment experiments and a Go comparison for quota-unaware runtime sizing. CPUQuotaLab also uses native Rust OS workers, but its deterministic mixed work, end-to-end timing, fractional quota, and 10/100 ms comparison are distinct.

## 7. Sample-size feasibility and percentile reliability

The final 90-second mixed run at 1,200/s completed all 108,000 requests, including **10,829 long requests**. The 10,000-long target applies to each individual non-overloaded run, not to a pooled experimental cell. With 10,000 long observations, about 100 observations lie above the empirical p99 cutoff. That supports descriptive per-run p99 values, while uncertainty and comparisons still use five paired run-level summaries. Overloaded runs are retained even if they cannot meet the class count; their completion-only percentiles are labeled conditional.

## 8. CPU accounting and environment

A sustained CPU-bound validation matched configured quota within about 0.3%:

| Period | Usage/wall normalized by 1.5 CPUs | Throttled periods |
|---:|---:|---:|
| 10 ms | 1.001 | 300/301 |
| 100 ms | 1.003 | 30/31 |

Pilot counters were coherent: one worker near its mixed boundary consumed about 0.98 CPU without throttling; two workers at 2,600/s consumed 1.41–1.42 CPU equivalents. The 10 ms case throttled in 1,044/1,500 periods and the 100 ms case in 69/150. `throttled_usec` is treated as aggregate throttled runqueue time, not wall-clock delay.

The runner samples power, battery, platform profile, governor, frequency, temperature, load, pressure, affinity, cgroup membership, `cpu.max`, and CPU counters. Valid final capacity/anchor blocks had AC online and `performance` profile at start and end. Server threads remained in the restricted scope on logical CPUs 0–7; generator threads remained outside it on 8–11. The proposed confirmatory environmental gate additionally requires AC at every sample, performance profile at every sample, and starting package temperature no more than 60°C.

## 9. Failures and unexpected observations

- A launcher-affinity race and normal server-exit race were fixed before the audit checkpoint.
- Equal arithmetic iterations did not produce equal measured CPU cost.
- Per-response flushing added measurable system CPU overhead.
- Pinning the scheduler to a single E-core produced rare long wakeup tails; allowing it to migrate within 8–11 improved the 90-second timing result.
- A busy-poll writer made socket handoff predictable but consumes roughly one generator-side CPU.
- An AC disconnect during an earlier uniform block changed the profile to `low-power`; all affected runs remain preserved and excluded. The complete final block was repeated on AC/performance.
- The interactive, non-real-time laptop still produces rare sub-millisecond scheduling outliers, motivating explicit attempt-replacement rules.

## 10. Figures and retained evidence

- [Capacity sweeps](figures/pilot/capacity_sweeps.png)
- [Selected boundary and anchor cells](figures/pilot/selected_comparisons.png)
- [Generator emission versus write timing](figures/pilot/generator_timing.png)

At completion, `results/pilot` contains 317 attempt directories and approximately 5.17 GB of raw and derived evidence. This includes invalid, superseded, battery-powered, and failed attempts. Smoke data are not used as scientific evidence, and pilot data will not enter confirmatory analysis.

## 11. Proposed final matrix, runtime, and storage

- Primary: 2 periods × 3 workers × 2 workloads × 2 loads × 5 repeats = **120 runs**.
- Conceptual anchor: 2 workers × 2 loads × 5 repeats = **20 runs**.
- Total: **140 runs**.

At 5 seconds warm-up, 90 seconds measurement, and up to 10 seconds drain, the timed upper envelope is 14,700 seconds, or **4.08 hours**. Including setup, randomized transitions, cooling, checks, and retained replacements, budget **5–7 hours**.

The planned rates imply approximately 32.8 million request records including warm-up. At the observed approximately 669 bytes per record, raw NDJSON is about 22 GB. Reserve **30 GB** for NDJSON, manifests, logs, summaries, figures, and failed replacement attempts.

## 12. Remaining limitations and decision

- Five run-level repeats give modest statistical precision.
- The host is one hybrid laptop with dynamic frequency and thermal behavior.
- Affinity/cgroup placement is sampled every 200 ms rather than continuously traced.
- The generator consumes substantial E-core CPU, although it is separated from server P-cores and cgroup budget.
- Synthetic CPU work and Unix sockets are mechanism probes, not production-service models.
- Completion-only latency under overload is conditional on admission/completion and must be interpreted with drop/incomplete rates.

**Phase 4 is complete. `FROZEN_PROTOCOL.md` v0.2 is a complete proposal for researcher review, but it is not active. No full 140-run confirmatory experiment has started.**
