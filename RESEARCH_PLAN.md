# Beyond Core Counts: Revised CPUQuotaLab Research Plan

**Researcher:** Mohit Singh  
**Study type:** Independent reproduction and targeted extension  
**Phase:** Phase 4 complete; proposed protocol v0.2 awaiting explicit researcher approval
**Date:** 24 November 2026

## 1. Revised positioning

CPUQuotaLab will reproduce a core observation from Jeffery, Jensen, and Mortier: sizing runnable OS workers above effective CPU capacity can harm latency under Linux CPU quotas. It will then test a narrower question their study does not directly answer:

> How do fractional CPU quotas and CPU bandwidth replenishment periods interact with integer worker-pool sizing to influence end-to-end tail latency, throughput, resource efficiency, and short/long task outcomes under mixed-duration CPU-bound workloads?

The revised title is **Beyond Core Counts: Investigating Fractional CPU Quotas, Bandwidth Periods, and Thread Pool Sizing Under Mixed-Duration Workloads**.

The work is not a new scheduler, a general solution for production services, or evidence that quota-aware sizing is novel. The intended contribution is a controlled reproduction plus an empirical characterization of an unresolved integer-rounding trade-off.

## 2. Literature conclusion and candidate gap

The focused review is in [RELATED_WORK_MATRIX.md](RELATED_WORK_MATRIX.md). It found substantial overlap with every part of the motivation, but no reviewed source evaluates the complete interaction of:

- a fractional quota;
- floor versus ceiling worker counts;
- 10 ms versus 100 ms periods at equal long-run bandwidth;
- equal-mean uniform versus mixed-duration CPU work;
- intended-arrival end-to-end latency decomposed into queue and execution time; and
- separate short- and long-task tail outcomes.

This is a **candidate gap, not a proven novelty claim**. A focused search cannot prove that no prior study exists.

The question is practically grounded because runtimes disagree. Rust currently floors quota-derived `available_parallelism()`; Uber's `automaxprocs` adopted floor; Go 1.25 deliberately rounds fractional limits up. Their discussions identify underutilization versus throttling, but do not provide a controlled period × workload × end-to-end latency study.

## 3. Technical mechanism

For cgroup v2, `cpu.max = MAX PERIOD` provides `MAX / PERIOD` CPU-equivalents per enforcement interval. A 1.5-CPU limit can be:

- `15000 10000`: 15 ms CPU time every 10 ms; or
- `150000 100000`: 150 ms CPU time every 100 ms.

Long-run bandwidth is equal, but burst capacity and maximum replenishment wait differ. Quota regulates aggregate CPU time; it does not assign 1.5 cores or prevent simultaneous execution on multiple allowed CPUs.

At 1.5 CPUs, one worker cannot use more than one CPU at once and may underuse the budget; two workers can use the full budget but may exhaust it early and be throttled. Eight workers deliberately ignore quota. Which trade-off is preferable may depend on period, offered load, and service-time distribution.

## 4. Research questions

### Primary

At a 1.5-CPU quota, does choosing one worker (floor) versus two workers (ceiling) change end-to-end p99 latency, throughput, CPU efficiency, and throttling differently under 10 ms and 100 ms periods?

### Secondary

1. Does the result change between uniform and mixed-duration work when both have equal expected CPU demand?
2. Does ceiling improve utilization enough to compensate for additional throttling or latency?
3. Do short tasks suffer disproportionate queue delay behind long tasks, and does that depend on period and workers?
4. Is the effect in queue waiting, execution duration, or both?
5. How do quota-unaware eight-worker and fixed four-worker configurations compare with floor/ceiling?
6. At integer quotas of 1 and 2 CPUs, where floor and ceiling coincide, does the original quota-aware result reproduce?

## 5. Hypotheses and pre-data rules

All hypotheses are unverified.

- **H1 — rounding trade-off.** At 1.5 CPUs, two workers achieve higher throughput/utilization than one but may increase throttling and p99 under capacity stress.
- **H2 — period interaction.** A quota-exhaustion latency penalty is larger at 100 ms than 10 ms. This may be contradicted by short-period overhead, runtime-slice granularity, or phase effects.
- **H3 — duration-class interaction.** In mixed work, long requests amplify short-task queue tails. More workers may reduce queue wait while increasing execution variability; the net effect is unknown.
- **H4 — quota-unaware sizing.** Eight workers do not materially improve throughput over the better of one/two workers at 1.5 CPUs and increase p99 and/or CPU time per completion.
- **H5 — reproduction.** At two CPUs/100 ms with uniform work, two workers match or beat eight-worker throughput while reducing worker execution tails, consistent in direction with the Cambridge study.

Pre-data materiality rules:

- throughput: more than **5%** relative median difference;
- p99 latency: more than **10% and at least 1 ms**; the absolute threshold may be revised after calibration but before confirmatory runs;
- class disparity: normalized slowdown, `end_to_end_latency / calibrated_service_demand`, reported separately for short and long tasks.

Failure to reject a test is not equivalence. Raw run points, paired effects, and uncertainty are primary.

## 6. System architecture

The proposed architecture is retained:

1. **Open-loop generator outside the server cgroup:** seeded intended arrivals/classes over a Unix socket; records actual submission and generator lag.
2. **Admission inside the restricted scope:** records arrival/admission/drop and inserts into a bounded FIFO queue.
3. **Native pool:** `std::thread` workers and a `Mutex<VecDeque<_>>` with condition variables and explicit shutdown.
4. **Deterministic CPU work:** the same computation at calibrated iteration counts; checksum plus `black_box` prevents elimination.
5. **Request instrumentation:** intended arrival, submission, admission, execution start, completion, class, outcome, worker.
6. **Resource monitoring:** pre/post `cpu.stat`, `cpu.stat.local` when present, PSI, procfs counters, frequency, and temperature.
7. **Immutable output:** unique run IDs/manifests; failed attempts retained; no timed-path disk writes.

The same release binary, queue, work function, and instrumentation are used across policies.

## 7. Workloads

- **Uniform control:** every request has identical CPU work.
- **Mixed duration:** provisionally 90% short and 10% long, with long work about 10× short; one seeded sequence is reused across matched cells.

To isolate distribution shape from mean demand:

`uniform_iterations = 0.9 × short_iterations + 0.1 × long_iterations`.

The pilot targets about 0.5 ms short, 5 ms long, and 0.95 ms uniform service time in single-worker unrestricted calibration. Exact iterations are frozen before primary data.

“Fairness” here means class-specific normalized response outcomes under the same FIFO policy, not Linux fairness between cgroups.

## 8. Policies and baselines

- **Visible/allowed CPUs:** intersection of affinity and inherited effective cpuset, ignoring quota; proposed value 8.
- **Quota floor:** `max(1, floor(effective_quota))`, capped by allowed CPUs; 1 at quota 1.5.
- **Quota ceiling:** `max(1, ceil(effective_quota))`, capped by allowed CPUs; 2 at quota 1.5.
- **Fixed:** explicit 1, 2, 4, or 8.
- **Rust default:** observe `available_parallelism()` inside each scope. Its current source documents floor, but the installed version/result is recorded rather than assumed.

Coincident policies are labels on one configuration, not duplicate runs. Detection walks the process cgroup and ancestors, selects the strictest normalized finite quota, and reports host count, affinity, cpuset, and quota separately.

## 9. Placement and verified feasibility

Phase 1 verified without privileged changes:

- 1.5 CPUs/10 ms produced `cpu.max = 15000 10000`;
- 1.5 CPUs/100 ms produced `cpu.max = 150000 100000`;
- `cpu.max.burst = 0` in both scopes.

Proposed placement:

- server on P-core logical CPUs `0-7`;
- generator on E-core CPUs `8-11`;
- server alone in a transient user scope;
- generator outside that scope.

This reduces generator and P/E migration interference but does not dedicate cores; background work and SMT remain. The visible baseline is eight allowed logical CPUs, not twelve host CPUs or eight physical cores.

Topology was reverified from sysfs and `lscpu`: 12 online logical CPUs, eight physical cores, four SMT sibling pairs `0-1`, `2-3`, `4-5`, `6-7` at a reported 4.4 GHz maximum, and four single-thread sibling sets `8`, `9`, `10`, `11` at 3.1 GHz. This matches Intel's 4 P-core + 4 E-core specification. P/E labels are inferred from sibling structure, frequency, and the vendor specification; Linux did not expose `core_type` on this host.

A sustained three-second validation with two CPU-bound processes at 1.5 CPUs showed normalized quota utilization of 1.001 at 10 ms and 1.003 at 100 ms. Throttled-period fractions were 300/301 and 30/31 respectively. The parent and both children had affinity `0-7` and identical transient-scope cgroup membership, while the outside controller remained in its original application scope. These are capability/accounting checks, not benchmark results.

## 10. Pilot and reduced matrix

A full cross-product would be wasteful before calibration. Use staged selection.

### Pilot screen (exploratory only)

- quotas 1, 1.5, 2;
- periods 10, 100 ms;
- workers 1, 2, 4, 8;
- uniform and mixed work;
- short runs and a load sweep.

Pilot data remains under `results/pilot/` and is never pooled with confirmatory data. It determines whether four workers adds information and whether both load levels/period effects are measurable.

### Confirmatory core (recommended)

| Factor | Levels |
|---|---|
| Quota | 1.5 CPUs |
| Period | 10, 100 ms |
| Workers | 1 floor, 2 ceiling, 8 visible |
| Workload | uniform, mixed |
| Offered load | moderate, capacity stress; fixed per workload |
| Repetitions | 5 |

This is **120 runs**. Add four workers only if the pilot shows a useful intermediate/non-monotonic response, making 160.

### Reproduction anchor

At 2 CPUs, 100 ms, uniform work, compare 2 versus 8 workers at moderate and capacity-stress loads for five repetitions: **20 runs**.

The anchor has its own pilot capacities because its quota and worker policies differ from the 1.5-CPU study. Let `S_anchor,2` and `S_anchor,8` be the highest stable rates for two and eight workers. Freeze `R_anchor,mod ≤ 0.70 × min(S_anchor,2, S_anchor,8)` and `R_anchor,stress = 0.90 × min(S_anchor,2, S_anchor,8)`, rounded down to a tested rate that passes the stability and generator-timing gates. If the two capacity estimates differ by more than 5%, retain the common lower-capacity rate and report the difference; never tune the offered rate separately by worker count. This near-capacity condition tests overcommitment without redefining the anchor as an overload experiment.

### Optional boundary check

If time/stability permit, mixed work at quotas 1 and 2, both periods, quota-matched versus visible workers, capacity stress, five repeats: **40 runs**.

Default confirmatory total: 140 runs; 180 with boundary checks.

## 11. Load and run protocol

For each workload and period at 1.5 CPUs, pilot separate sustainable capacities for one worker (`S_floor`) and two workers (`S_ceil`). Freeze two absolute rates shared by every worker policy:

- **moderate:** at most 70% of `min(S_floor, S_ceil)`, so both policies should be stable;
- **capacity stress:** choose a rate satisfying `1.10 × S_floor ≤ R_stress ≤ 0.90 × S_ceil` when that interval exists. This deliberately stresses floor-policy underutilization while leaving headroom for ceiling. If no interval exists, use the smallest rate above `1.05 × S_floor`, disclose whether ceiling also overloads, and do not manufacture separation.

Rates are never retuned per worker policy. Dropped and incomplete requests remain first-class outcomes. Each run uses a readiness phase, 5 s warm-up, the pilot-selected 90 s measurement duration, then a maximum 10 s drain. Each individual non-overloaded mixed run must complete at least 10,000 long-class requests. About 100 observations then lie in the upper 1% of the long class per run; this supports a descriptive p99 but does not make a single-run p99 exact. Randomized blocks use a recorded seed and identical matched sequences.

Generator timing must pass the frozen-proposal gates: median absolute scheduler lag ≤25 µs; scheduler and socket-write-completion p99 ≤`max(250 µs, 25% of the inter-arrival interval)`; no more than 1% at either stage later than one interval; backlog ≤32; and zero transport failures. Complete distributions and generator CPU use are retained. A failed attempt remains preserved and requires a separately identified replacement.

Randomize initial arrival phase relative to quota period and record it to avoid period-lock artifacts.

## 12. Metrics

Per-run request summaries:

- offered/admitted/completed requests/s;
- median, mean, p95, p99 intended-arrival end-to-end latency;
- submission lag, admission delay, queue wait, execution duration;
- queue-full drops, failures, uncompleted requests;
- queue occupancy and worker busy fraction;
- all latency/outcome metrics separately for short and long classes;
- normalized slowdown and class completion/drop shares.

System counter deltas:

- `usage_usec`, user/system CPU, normalized quota utilization;
- completions per CPU-second;
- `nr_periods`, `nr_throttled`, throttled-period fraction;
- `throttled_usec`, explicitly aggregated runqueue throttling, not wall time;
- `cpu.stat.local` and PSI where available;
- voluntary/nonvoluntary context switches, frequency, temperature.

Unavailable unprivileged `perf` events are excluded rather than prompting a security change.

Primary throughput is **timely goodput**: measurement-tagged requests completed before measurement end divided by measurement duration. Also report admitted rate, server completions timestamped inside the window, and eventual measurement-tagged completions by the drain deadline. Latency percentiles include only measurement-tagged admitted requests completed by the drain deadline; they are explicitly conditional on completion whenever drops or incompletes occur. If more than 1% of admitted requests remain incomplete, completion-only p99 is not treated as an unconditional tail result.

## 13. Statistical analysis

The independent unit is a run; request observations only estimate that run's distribution.

- Show every run point plus median/IQR/range.
- Pair floor/ceiling and 10/100 ms comparisons within randomized blocks.
- Report absolute/relative effects with paired bootstrap intervals; five-pair intervals are exploratory.
- Compare run-level short and long class summaries.
- Use a compact period × worker × workload × load model only secondarily and inspect assumptions.
- Explore throttled-period fraction versus p99 with stratified scatter/Spearman association; do not infer causation.
- Report overload, drops, failures, and contradictions for every prespecified cell.

## 14. Key threats and controls

| Threat | Control/interpretation |
|---|---|
| Hybrid P/E laptop and SMT | P-core-only server, E-core generator, topology disclosed |
| Interactive background activity | randomized blocks, ≥5 repeats, PSI/load records, retain unusual runs |
| DVFS/turbo/thermal drift | warm-up, frequency/temperature records, randomized order; no host changes |
| Arrival/quota phase locking | randomize and record phase |
| Kernel runtime-slice granularity | host value is 5 ms, half the short period; record it per experiment and interpret 10 ms results as kernel-specific |
| FIFO head-of-line blocking | intentional/fixed; decompose queue/execution; no priority-queue generalization |
| Open-loop overload | bounded queue, pilot-fixed rates, explicit drops/uncompleted accounting |
| Synthetic work | mechanism probe only; no production/gRPC claim |
| Small run count/p99 noise | ≥10k completions/run, raw points/effects, cautious uncertainty |
| Instrumentation | buffered records, no per-request I/O, pilot overhead check |
| Kernel/runtime version | exact versions and observed runtime baseline stored |
| Focused literature search | avoid novelty claims and state search scope/date |

## 15. Estimated effort

| Activity | Estimate |
|---|---:|
| Protocol review/freeze | 1–2 h |
| Rust engine, detection, tests | 8–12 h |
| Automation and pilot | 3–5 h |
| Default 140-run set | 4.08 h timed upper envelope for 5 s warm-up + 90 s measurement + up to 10 s drain |
| Operational overhead/cooling/retries | budget approximately 0.75–2 h beyond timed runs; revise after pilot |
| Optional boundary checks | ~1 h budget |
| Analysis/figures | 4–6 h |
| Report/docs/review | 5–8 h |

This remains feasible in three to four focused days only if extensions are pilot-gated.

## 16. Toolchain and analysis dependencies

The researcher approved the official user-local `rustup` procedure. Phase 3 installed and pinned Rust 1.100.0 with Cargo, Rustfmt, and Clippy; exact versions and installer provenance are recorded in `RESEARCH_LOG.md`. No root privilege was used.

Initial analysis will use the already available NumPy 2.5.4 and Matplotlib 3.11.2 plus Python's standard library. Pandas and SciPy are not required for Phase 3 or the pilot. Any later dependency must be justified, isolated, and recorded.

Jeffery et al.'s main overcommitment benchmark uses Rust native OS threads, while its quota-awareness comparison also evaluates Go. Go evidence remains policy motivation only: `GOMAXPROCS` limits concurrently executing goroutines and interacts with garbage collection and background work. CPUQuotaLab uses fixed native Rust OS worker threads and no async runtime, so its results cannot be claimed as a Go runtime evaluation or faithful reproduction.

## 17. Evidence language

Protocol statements such as “a longer period may allow a longer replenishment wait” and hypotheses H1–H5 are theoretical predictions. Capability checks establish only that the interfaces, containment, and counters work. Measured performance claims will appear only after frozen-protocol runs and will be labeled observations, followed separately by interpretation.

## 18. Phase checkpoint and review state

Completed: reframed as reproduction plus targeted extension; reviewed academic, kernel, and runtime evidence; identified fractional rounding as the narrow opportunity; verified both periods; defined a reduced core plus reproduction anchor.

Remaining uncertainties: period effects may be smaller than laptop noise; workload mixture may need pre-data adjustment; the 1 ms threshold depends on calibration; P-core placement changes the visible baseline from 12 host CPUs to 8 allowed CPUs.

The researcher approved the Phase 2 experimental design and Phase 4 pilot work. That approval is **not** the final protocol freeze. Phase 4 has now calibrated workload iterations, offered rates, queue capacities, a common 90-second duration, timing tolerances, and environmental gates. These values are written in proposed `FROZEN_PROTOCOL.md` v0.2 and remain inactive until explicit researcher approval.

Phase 3 implemented the Rust instrument, orchestration, structured output, component/end-to-end tests, and small smoke checks. Phase 4 completed the source audit, workload and overhead calibration, generator validation, AC/performance capacity sweeps, sample-size feasibility test, and conceptual-anchor calibration. Pilot observations remain exploratory and are excluded from confirmatory estimates. The next approval point is activation of `FROZEN_PROTOCOL.md`; the 140-run confirmatory matrix remains prohibited.
