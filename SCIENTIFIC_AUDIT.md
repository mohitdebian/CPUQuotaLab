# CPUQuotaLab Scientific Audit

**Audit date:** 24 November 2026  
**Scope:** source, protocol, 17 confirmatory attempt directories, analysis, figures, literature positioning, and repository state  
**Raw-data policy:** no raw record was modified

## Executive assessment

No critical defect was found that invalidates the 15 accepted runs. Source/binary provenance, exact request reconciliation, cgroup settings, generator gates, affinity separation, and environmental acceptance are supported by manifests and raw records. The headline goodput and p99 effects independently reproduce from `requests.ndjson`.

The audit found two major reporting problems: the Phase 5 document rewrote the original hypothesis labels after outcomes were known, and the analysis compared throttled-period percentages across unequal 10/100 ms periods without sufficient qualification. Both are corrected. The evidence supports a queue-dominated latency difference, but it does not by itself prove the scheduler mechanism causing the unexpected period interaction.

## Findings

### Critical

None identified.

### Major A1 - Post-outcome hypothesis relabeling

**Finding.** `PRELIMINARY_STATISTICAL_ANALYSIS.md` replaced the original H1-H3 wording with new labels such as “one worker underuses fractional capacity.” This violates the pre-data hypothesis rule even though the underlying observations were reported honestly.

**Correction.** Restored the exact H1-H5 text from `RESEARCH_PLAN.md` and assessed each without redefinition:

- **H1 - rounding trade-off:** partially supported. Two workers increased utilization and completion and sharply reduced p99; the predicted possibility of higher p99 under stress was not observed.
- **H2 - period interaction:** the measured overall end-to-end direction is contradicted; the specific quota-exhaustion mechanism is inconclusive. The original prediction was a larger quota-exhaustion penalty at 100 ms, but observed end-to-end p99 was lower at 100 ms. Individual exhaustion intervals were not traced, so this does not show that every quota-exhaustion pause is shorter at 100 ms.
- **H3 - duration-class interaction:** partially supported. Both classes were dominated by queue wait; long tasks had higher tails, and two workers reduced both. The current subset cannot isolate “long requests amplify short tails” from aggregate FIFO load because there is no uniform control.
- **H4 - quota-unaware sizing:** not yet evaluated; no eight-worker confirmatory cells.
- **H5 - reproduction:** not yet evaluated; no two-CPU anchor confirmatory cells.

### Major A2 - Cross-period throttling comparison

**Finding.** A 34% throttled-period fraction at 10 ms and 11.5% at 100 ms use very different numbers of enforcement periods. Comparing those percentages alone can misstate severity.

**Correction.** The analysis and CPU figure now retain the raw fraction but emphasize normalized throttle events/s and aggregate `throttled_usec` per wall second. For two-worker stress, medians were 33.86 events/s and 0.150 aggregate throttled s/wall s at 10 ms, versus 1.15 events/s and 0.015 at 100 ms. Kernel documentation describes `nr_throttled` and `throttled_usec` as bandwidth counters; neither is a direct per-request delay measure.

### Major A3 - Aggregation concealed load-specific effects

**Finding.** The headline medians pooled moderate and stress pairs. The +3.06% goodput and -90.36% p99 results are arithmetically correct but obscure different regimes.

**Correction.** Condition-specific summaries are now primary. At moderate load, median paired goodput changed +0.028% and p99 -87.41% (three available pairs). At stress, medians were +3.55% and -93.01% (four pairs). No goodput pair crossed +5%; every p99 pair crossed both latency thresholds.

### Major A4 - Incomplete replication structure

**Finding.** The block-2/10 ms/two-worker/moderate cell is missing after two thermal-invalid attempts. That condition has one valid run, and comparisons requiring its second block are unavailable.

**Correction.** Figures show individual runs, paired tables use only available matched blocks, and reports explicitly identify the missing cell. No interval or significance claim is made.

### Minor A5 - “Support CPU overhead” residual

**Finding.** Subtracting complete-request worker CPU from measurement-window cgroup CPU is not a clean support-thread measurement when work crosses measurement boundaries.

**Correction.** Renamed it `support_cpu_residual_usec`; it is retained for diagnostics but not interpreted as exact support-thread overhead in conclusions.

### Minor A6 - Queue-depth selection

**Finding.** The former queue-depth diagnostic used completed requests only, excluding dropped requests when the FIFO was full.

**Correction.** Queue-depth half means now use every measurement response, including drops. Latency percentiles remain completion-conditional by definition.

### Minor A7 - Thermal preflight race

**Finding.** Two attempts passed a pre-launch sensor read but their manifest start snapshots exceeded 60°C.

**Correction.** Existing classification is correct and both attempts remain immutable. Future collection should require a below-threshold stability interval, but this would be a protocol amendment and was not retroactively applied.

### Informational A8 - Related-work positioning

Jeffery et al. primarily use a Rust native-thread open-loop `fib(30)` benchmark and separately use Go for quota-awareness. Linux documents quotas as CPU-time throughput limits replenished by period and distributed to per-CPU runqueues in slices. Go 1.25 rounds fractional CPU limits up for `GOMAXPROCS`; Rust exposes only an approximate parallelism hint. CPUQuotaLab is therefore a targeted preliminary empirical extension, not the invention of quota-aware sizing and not proof of novelty.

## Independent numerical verification

`scripts/audit_confirmatory.py` ignores `run_level_metrics.csv` and recomputes from raw NDJSON, server snapshots, manifests, and the predeclared matrix. Its output, `audit_recomputation.json`, verifies:

| Quantity | Independent result |
|---|---:|
| Valid runs | 15 |
| Offered | 2,340,000 |
| Completed | 2,314,313 |
| Dropped | 25,687 |
| Incomplete / failed | 0 / 0 |
| Available worker-count pairs | 7 |
| Median paired timely-goodput change | +3.060587% |
| Median paired overall-p99 change | -90.359088% |

The independent results agree with the published CSV values to displayed precision.

## Mechanism evidence

Queue waiting accounts for nearly all end-to-end p99 in the key cells:

| Load / period / workers | Short E2E / queue / CPU p99 (ms) | Long E2E / queue / CPU p99 (ms) | Mean queue depth halves |
|---|---|---|---|
| Stress / 10 / 1 | 295.78 / 295.57 / 0.239 | 304.31 / 301.30 / 3.056 | 457.8 / 470.9 |
| Stress / 10 / 2 | 26.87 / 26.55 / 0.243 | 31.55 / 26.88 / 3.191 | 8.5 / 8.7 |
| Stress / 100 / 1 | 300.30 / 300.08 / 0.240 | 311.70 / 308.68 / 3.074 | 468.9 / 472.6 |
| Stress / 100 / 2 | 13.51 / 13.16 / 0.243 | 17.31 / 13.75 / 3.189 | 3.6 / 3.8 |

The worker-CPU p99 is almost unchanged between the two-worker periods, whereas queue p99 halves at 100 ms. This strongly supports queue wait as the proximate measured contributor. It does not establish why the 100 ms configuration maintained the smaller queue.

At two-worker/10 ms stress, long elapsed execution p99 was 7.57 ms versus 3.19 ms thread CPU, consistent with descheduling/throttling during execution. At 100 ms it was 3.20 versus 3.19 ms. The 10 ms case also recorded roughly ten times more aggregate throttled time per wall second. The kernel's 5 ms bandwidth slice is plausibly relevant because it is half the 10 ms period, but no scheduler trace or phase-randomized period sweep exists to verify causation. P-core mean frequencies were similar (approximately 3.15 versus 3.07 GHz); recorded maxima and thermal values overlap, so frequency does not offer a clear alternative explanation.

## Provenance and reproducibility

- Frozen benchmark SHA-256 matches every accepted manifest.
- `dataset_provenance.json` hashes all files in 17 attempt directories (1,741,680,879 bytes).
- Every accepted manifest records clean source revision `b304aec39f697abcbd62611ea9a2df6ac1abec0f` and the frozen binary hash.
- `cpu.max`, `cpu.max.burst`, cgroup separation, and affinity checks passed for accepted attempts.
- Rustfmt, strict Clippy, 28 unit tests, and the Unix-socket end-to-end test had passed immediately before collection; Phase 6 did not rerun the benchmark.

## Unresolved limitations

Only two planned blocks and one machine are represented; one cell has one observation. Queue depth is sampled at request response/admission events, not traced continuously. `throttled_usec` is a cgroup/runqueue counter, not per-request stall attribution. Dynamic frequency, shared package power/cache, and interactive-host activity remain possible confounders. No scheduler trace establishes the 10/100 ms mechanism. Uniform, eight-worker, and anchor confirmatory evidence is absent. Completing the design requires 125 additional valid runs: 124 unstarted cells plus the missing initial cell.
