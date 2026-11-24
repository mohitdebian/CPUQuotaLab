# Beyond Core Counts: Investigating Fractional CPU Quotas, Bandwidth Periods, and Thread Pool Sizing Under Mixed-Duration Workloads

## Abstract

This independent undergraduate systems study examines how a 1.5-CPU Linux cgroup quota, 10/100 ms bandwidth periods, and one-versus-two native Rust workers affect an open-loop mixed-duration service. This preliminary confirmatory stage contains 15 valid runs from a predeclared 16-cell subset of a planned 140-run design; one cell is missing after two thermal-gate failures. At 1,200 requests/s, both worker counts sustained offered throughput, but two workers reduced conditional end-to-end p99 from about 29 ms to 3.7–4.4 ms. At 2,200/s, one worker dropped 2.77–3.74% of requests and had p99 near 291–308 ms; two workers completed every request and had p99 of 27.5–28.0 ms at 10 ms and 14.4 ms at 100 ms. Two workers used more quota and experienced throttling. These descriptive results show a latency/resource trade-off but do not establish statistical significance or generalize beyond one laptop and synthetic workload.

## 1. Motivation and candidate gap

Linux CPU quotas limit execution time within replenishment periods. A fractional quota such as 1.5 CPUs does not map cleanly to an integer native worker count: flooring to one worker can leave half a CPU budget unusable, while rounding up to two may consume the full budget and trigger periodic throttling. Tail latency also includes queue waiting, so a policy that avoids throttling may still be poor for requests waiting behind work.

Jeffery, Jensen, and Mortier study OS-thread overcommitment using a Rust open-loop `fib(30)` benchmark and separately show quota-unaware sizing in Go. They omit queue latency from their later quota analysis and do not jointly study fractional rounding, 10/100 ms periods, mixed durations, and end-to-end class-specific latency. CPUQuotaLab treats that combination as a **candidate** research gap, not proven novelty.

## 2. Research question and original hypotheses

The main question is how fractional quota, period, and pool size interact to affect timely throughput, end-to-end tails, and efficiency under 90/10 short/long CPU work. We expected one worker to underuse 1.5 CPUs; two workers to improve stress capacity but introduce throttling; and period effects to appear most strongly when multiple workers exhaust quota.

The pre-confirmatory hypotheses are retained verbatim:

- **H1 — rounding trade-off.** At 1.5 CPUs, two workers achieve higher throughput/utilization than one but may increase throttling and p99 under capacity stress.
- **H2 — period interaction.** A quota-exhaustion latency penalty is larger at 100 ms than 10 ms. This may be contradicted by short-period overhead, runtime-slice granularity, or phase effects.
- **H3 — duration-class interaction.** In mixed work, long requests amplify short-task queue tails. More workers may reduce queue wait while increasing execution variability; the net effect is unknown.
- **H4 — quota-unaware sizing.** Eight workers do not materially improve throughput over the better of one/two workers at 1.5 CPUs and increase p99 and/or CPU time per completion.
- **H5 — reproduction.** At two CPUs/100 ms with uniform work, two workers match or beat eight-worker throughput while reducing worker execution tails, consistent in direction with the Cambridge study.

## 3. System and methodology

The Rust server accepts requests over a Unix socket, timestamps receive/admission, and inserts them into a bounded nonblocking FIFO. One or two native worker threads execute deterministic wrapping-integer work and record elapsed and thread-CPU time. The external open-loop generator schedules absolute intended arrival times independently of responses, while separate writer/reader roles prevent response feedback from silently closing the loop. Every scheduled request has an auditable outcome.

The server ran on P-core logical CPUs 0–7 inside a cgroup v2 transient scope; the generator ran outside that scope on E-core CPUs 8–11. The writer used CPU 9 and reader CPU 10. Quota was 1.5 CPUs with 10 or 100 ms period and burst disabled. AC, performance profile, temperature, frequency, pressure, affinity, cgroup membership, timing, and accounting were recorded.

Short and long work used 76,000 and 1,140,000 iterations, calibrated to about 0.48 and 5.20 ms worker CPU. Mixed requests were deterministically 90/10. Loads were 1,200/s moderate and 2,200/s stress; FIFO capacity was 550. Runs used 5 seconds warm-up, 90 seconds measurement, and at most 10 seconds drain. Run-level observations—not requests—are replicates.

Before data collection, a complete 120-primary/20-anchor schedule was generated from master seed `2027112401`. This stage selected blocks 1–2, mixed workload, both periods/loads, and one/two workers. No confirmatory outcome influenced the schedule or parameters.

## 4. Preliminary results

Fifteen cells were valid; the missing block-2 10 ms/two-worker/moderate cell exhausted the two-attempt thermal retry limit. Valid runs offered 2,340,000 measurement requests, completing 2,314,313 and dropping 25,687. There were no incomplete requests or transport failures.

At moderate load, one-worker conditional p99 was 28.99–29.29 ms, while two-worker p99 was 4.43 ms at 10 ms (one valid block) and 3.66–3.67 ms at 100 ms. Both achieved approximately 1,200 timely completions/s and no drops.

At stress, one worker achieved 2,113–2,135 timely completions/s, dropped 2.77–3.74%, and produced conditional p99 of 291–308 ms. Two workers completed all requests at 2,200/s. Its p99 was 27.48–28.03 ms with the 10 ms period and 14.36–14.42 ms with 100 ms.

Across seven matched worker-count pairs, median timely-goodput change was +3.06%, below the predeclared 5% materiality threshold. Median p99 change was −90.36%, and every available pair exceeded the latency threshold (>10% and ≥1 ms). Short- and long-class p99 fell by median 93.95% and 89.24%. These percentiles are conditional on completed requests; drop fractions remain visible in Figure 4 and the run table.

Two workers increased quota utilization by a median 9.48%. One-worker runs did not throttle. Under two-worker stress, 10 ms recorded about 33.86 throttle events/s and 0.150 aggregate throttled seconds per wall second, versus 1.15 events/s and 0.015 seconds/s at 100 ms. The longer period's substantially lower p99 was repeat-consistent, contrary to H2's predicted direction. Throttled-period percentages are not treated as directly comparable severity because period counts differ by roughly tenfold.

## 5. Interpretation

The one-worker floor policy avoids throttling but cannot use the fractional half CPU concurrently. Requests accumulate in the FIFO, especially at stress. Direct raw-data analysis supports queue wait as the proximate contributor: at stress, short queue p99 was about 296–300 ms with one worker but 26.55/13.16 ms with two workers at 10/100 ms, while short thread-CPU p99 stayed near 0.24 ms. Long queue p99 similarly fell from 301–309 ms to 26.88/13.75 ms while CPU p99 stayed near 3.1 ms. These are separately computed percentile distributions and are not added or subtracted as an algebraic decomposition. Two workers therefore expose enough parallelism to reduce the queue, even though Linux sometimes pauses the cgroup after budget exhaustion.

The period interaction is workload- and policy-dependent. The 100 ms period improved the two-worker stress tail on this host, while one-worker results barely changed. At 10 ms, long elapsed-execution p99 was 7.57 ms versus 3.19 ms CPU; at 100 ms it was 3.20/3.19 ms. This is consistent with more interruption at 10 ms. The kernel's 5 ms bandwidth slice, request/quota phase, and replenishment behavior are plausible explanations, but no scheduler trace establishes causality. Recorded P-core frequencies and thermal ranges overlap and do not clearly explain the effect.

H1 is partially supported: two workers increased use/completion and throttling, but reduced rather than increased p99. The measured overall direction contradicts H2, but the narrower quota-exhaustion mechanism remains inconclusive because individual exhaustion intervals were not traced and end-to-end latency includes queueing and execution. H3 is partially supported but requires a uniform control to isolate long-task amplification. H4 and H5 are not yet evaluated.

## 6. Threats and limitations

Only two blocks were planned, and one cell has one valid observation. No significance or confidence claim is warranted. The host is one hybrid Intel laptop with dynamic frequency and thermal behavior. Affinity separates generator E-cores from server P-cores, but shared cache, memory, and package power remain possible interference channels. The workload is synthetic, transport is a Unix socket, and results cannot be generalized directly to Kubernetes, gRPC, or cloud services. Completion-only latency under overload is selection-sensitive, so drops are reported jointly. Eight-worker, uniform, and conceptual-anchor questions remain unevaluated.

## 7. Reproducibility

The exact Rust toolchain is pinned in `rust-toolchain.toml`; dependencies are locked. Protocol, full schedule, attempt index, run metrics, effects, analysis code, figures, and per-file SHA-256 hashes are included. Multi-gigabyte raw data are stored locally under `results/confirmatory/attempts` and intentionally excluded from Git. Run `python3 scripts/analyze_confirmatory.py` to reproduce outputs and `python3 scripts/audit_confirmatory.py` for an independent raw-record recomputation. Completing the original design requires 125 valid runs: 124 unstarted cells plus the missing initial cell.

## 8. Research status and disclosure

This is independent undergraduate research conducted on one machine. Results are a preliminary subset, separate from 317 exploratory pilot attempts, have only two planned repetitions, and have not been peer reviewed. The candidate gap is not a novelty claim.

OpenAI Codex assisted with literature checking, methodology/code refinement, orchestration, analysis, visualization, and drafting. Mohit Singh selected and approved the research direction, design, staged matrix, and integrity requirements. All generated code, claims, and figures require the researcher's technical review before external use.

## References

1. A. Jeffery, C. Jensen, and R. Mortier. “Reducing Tail Latencies Through Environment- and Neighbour-aware Thread Management.” arXiv:2407.11582v1, 2024.
2. Linux kernel documentation. “CFS Bandwidth Control” and “Control Group v2.”
3. J. Dean and L. A. Barroso. “The Tail at Scale.” Communications of the ACM, 2013.
