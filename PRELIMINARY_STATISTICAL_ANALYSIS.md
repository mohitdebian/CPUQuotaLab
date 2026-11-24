# Preliminary Descriptive Statistical Analysis

## Scope and rules

The experimental unit is one complete benchmark run. This analysis contains two repetitions for most cells and one repetition for the valid 10 ms/two-worker/moderate cell. It shows individual observations, medians/ranges, and matched differences. It does not calculate confidence intervals, claim statistical significance, or treat requests as independent replicates. All latency percentiles are conditional on completion; outcome fractions are reported beside them. Drop fraction uses offered requests as its denominator; incomplete fraction uses admitted measurement requests, as frozen in the protocol. All valid runs have zero incomplete requests, so correcting the analysis denominator does not change a reported result.

## Run-level observations

| Load | Period | Workers | Valid n | Timely goodput/s | Overall p99 ms | Short p99 ms | Long p99 ms | Drop % | Quota use % | Throttled periods % |
|---|---:|---:|---:|---|---|---|---|---|---|---|
| Moderate | 10 | 1 | 2 | 1199.66–1199.67 | 28.99–29.29 | 28.19–28.48 | 32.03–32.41 | 0 | 41.80–41.94 | 0 |
| Moderate | 10 | 2 | 1 | 1200.00 | 4.43 | 2.24 | 7.01 | 0 | 42.87 | 5.11 |
| Moderate | 100 | 1 | 2 | 1199.67 | 29.04–29.17 | 28.17–28.32 | 32.11–32.38 | 0 | 41.88–42.01 | 0 |
| Moderate | 100 | 2 | 2 | 1200.00 | 3.66–3.67 | 1.70–1.71 | 4.76–4.77 | 0 | 42.89 | 0 |
| Stress | 10 | 1 | 2 | 2121.38–2134.67 | 290.73–302.59 | 290.19–301.37 | 294.57–314.04 | 2.77–3.36 | 68.36–68.82 | 0 |
| Stress | 10 | 2 | 2 | 2200.00 | 27.48–28.03 | 26.61–27.13 | 31.38–31.71 | 0 | 75.35–75.49 | 33.74–33.97 |
| Stress | 100 | 1 | 2 | 2113.06–2127.59 | 294.67–308.03 | 294.18–306.43 | 299.45–323.94 | 3.10–3.74 | 68.79–68.80 | 0 |
| Stress | 100 | 2 | 2 | 2200.00 | 14.36–14.42 | 13.42–13.59 | 17.11–17.50 | 0 | 75.60–75.64 | 11.33–11.67 |

## Matched worker-count effects

Seven of eight one-versus-two-worker pairs are available. Across those pairs:

- timely goodput changed by a median **+3.06%** (range +0.03% to +4.11%);
- overall conditional p99 changed by a median **−90.36%** (range −95.34% to −84.88%);
- short p99 changed by a median **−93.95%**;
- long p99 changed by a median **−89.24%**; and
- normalized quota utilization changed by a median **+9.48%**.

The pooled medians are descriptive only and combine distinct load regimes. At moderate load, median paired goodput changed +0.028% and p99 -87.41% across three available pairs. At stress, the corresponding medians were +3.55% and -93.01% across four pairs. The p99 changes exceed both latency materiality criteria (>10% and ≥1 ms) in all available pairs. Throughput changes do not exceed the >5% threshold. Under stress, however, two workers removed the observed 2.77–3.74% queue-drop fraction and reached the full 2,200/s offered rate.

One worker showed no quota throttling because it cannot execute on more than one CPU simultaneously. Two workers used more of the 1.5-CPU budget and were throttled. This is the predicted floor-versus-ceiling trade-off: greater resource use and throttling accompanied far lower queueing/tail latency.

## Period effects

Seven of eight 10-versus-100 ms matched pairs are available. Period effects depend on worker count and load:

- one-worker p99 values were similar across periods at both loads, with repetition-to-repetition changes of only a few percent;
- two-worker stress p99 fell from 27.48–28.03 ms at 10 ms to 14.36–14.42 ms at 100 ms, a large and repeat-consistent reduction;
- two-worker stress recorded about 33.86 versus 1.15 throttle events/s and 0.150 versus 0.015 aggregate throttled seconds per wall second at 10 versus 100 ms;
- two-worker moderate p99 was modestly lower at 100 ms, but the absolute difference was below 1 ms, so it does not pass the combined materiality rule; and
- throughput was essentially invariant to period after conditioning on worker count.

Throttled-period fractions are not directly comparable as severity across unequal period lengths; 90 seconds contains about ten times as many 10 ms enforcement periods. The normalized counters above are also not direct per-request stall measurements. The counterintuitive stress result does not prove that longer periods are generally better. It may reflect how this kernel's 5 ms bandwidth slice, quota-use phase, queue dynamics, and workload costs interact. Only two blocks on one machine are available.

## Mechanism decomposition

At stress with one worker, median short-task queue p99 was 295.57 ms at 10 ms and 300.08 ms at 100 ms, while thread-CPU p99 was only about 0.239–0.240 ms. With two workers, short queue p99 fell to 26.55 and 13.16 ms; thread-CPU p99 remained about 0.243 ms. The same pattern holds for long tasks: queue p99 was 301–309 ms with one worker and 26.88/13.75 ms with two, while long thread-CPU p99 stayed near 3.06–3.19 ms.

The separate percentile distributions therefore identify queue waiting, rather than faster computation, as the dominant measured contributor. Individual component p99 values are not added or subtracted: the percentile of a sum is not generally the sum of its component percentiles. At two-worker/10 ms stress, long elapsed-execution p99 (7.57 ms) exceeded thread CPU p99 (3.19 ms), whereas at 100 ms they were nearly equal (3.20/3.19 ms). This is consistent with more execution interruption at 10 ms but does not identify a kernel-level cause. Mean completed/drop-inclusive queue depth was roughly 458→471 and 469→473 for one-worker stress, versus 8.5→8.7 and 3.6→3.8 for two workers at 10/100 ms.

## Original hypotheses (unchanged from the pre-confirmatory plan)

- **H1 — rounding trade-off.** “At 1.5 CPUs, two workers achieve higher throughput/utilization than one but may increase throttling and p99 under capacity stress.” **Assessment: partially supported.** Utilization, completion, and throttling increased, but p99 decreased sharply rather than increasing.
- **H2 — period interaction.** “A quota-exhaustion latency penalty is larger at 100 ms than 10 ms. This may be contradicted by short-period overhead, runtime-slice granularity, or phase effects.” **Assessment: the measured overall end-to-end direction is contradicted; the specific quota-exhaustion mechanism is inconclusive.** The 100 ms end-to-end p99 was lower, but total latency also includes queueing and execution, and individual exhaustion intervals were not traced.
- **H3 — duration-class interaction.** “In mixed work, long requests amplify short-task queue tails. More workers may reduce queue wait while increasing execution variability; the net effect is unknown.” **Assessment: partially supported.** Both classes show queue-dominated tails and strong queue reduction with two workers; the absence of a uniform confirmatory control prevents isolating amplification caused specifically by long requests.
- **H4 — quota-unaware sizing.** “Eight workers do not materially improve throughput over the better of one/two workers at 1.5 CPUs and increase p99 and/or CPU time per completion.” **Assessment: not yet evaluated.**
- **H5 — reproduction.** “At two CPUs/100 ms with uniform work, two workers match or beat eight-worker throughput while reducing worker execution tails, consistent in direction with the Cambridge study.” **Assessment: not yet evaluated.**

## Reproduction

Run `python3 scripts/analyze_confirmatory.py` for primary outputs and `python3 scripts/audit_confirmatory.py` for the independent raw-record audit. The latter does not consume the run-level metrics CSV.
