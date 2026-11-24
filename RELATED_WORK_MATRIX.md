# CPUQuotaLab Focused Related-Work Matrix

**Search date:** 24 November 2026  
**Purpose:** Assess overlap with fractional quotas, quota periods, integer pool sizing, mixed-duration CPU work, and end-to-end class-specific latency.  
**Scope warning:** This is a focused, time-bounded review, not a systematic review. Absence here is not proof that no relevant work exists.

## Search scope

Sources included arXiv, USENIX proceedings, primary academic paper copies, official Linux kernel documentation and mailing-list patches, official runtime documentation, and upstream repositories. Queries combined `fractional CPU quota`, `CFS bandwidth period`, `thread pool`, `tail latency`, `mixed workload`, `floor ceil`, `end-to-end latency`, and `cgroup throttling`. Original/first-party sources were preferred. Runtime discussions and kernel patches are engineering evidence, not peer-reviewed findings.

## Comparison matrix

| Work/source | Research question | Configuration/workload | Metrics and policy | Relevant finding | Limitation relative to CPUQuotaLab | Retained extension |
|---|---|---|---|---|---|---|
| Jeffery, Jensen, Mortier, “Reducing Tail Latencies Through Environment- and Neighbour-aware Thread Management,” arXiv:2407.11582 (2024 preprint) | How do quota-unaware sizing/neighbours affect tails; can an adaptive pool help? | Rust/Go; open-loop uniform `fib(30)`; 16 logical CPUs; 5 s × 5 repeats | Queue/worker timing initially; later worker latency/throughput; manual/default/adaptive pools | Overcommitment raises worker latency; `friendlypool` reduces maximum worker latency up to 6.7× with throughput cost up to 1.4× | No fractional rounding × period; queue latency omitted later; uniform work; short runs | Integer reproduction plus fractional 1.5, 10/100 ms, end-to-end queueing, mixed classes |
| Turner, Rao, Rao, “CPU Bandwidth Control for CFS,” Linux Symposium (2010) | How can CFS enforce an upper bound beyond shares? | Kernel design and quota/period examples | Bandwidth behavior; CFS quota, period, per-CPU silos | Periodic replenishment supplies a hard upper bound; longer periods permit more burst | Mechanism paper, not request/thread-pool evaluation | Hold ratio constant while treating period as factor |
| Ugedal, Kumar, “Mitigating Unnecessary Throttling in Linux CFS Bandwidth Control,” SBAC-PAD (2022) | Why can bandwidth control throttle unnecessarily and incur overhead? | Kernel analysis/modification with multiple benchmarks | Throttling, performance, overhead; altered accounting/atomics | Nearly eliminated studied unnecessary throttling; up to 12% performance gain and 24× lower overhead | Kernel modification; no rounding, periods × pools, or request classes | Treat throttling as kernel/version dependent, not automatically caused by pool size |
| Wang et al., “Autothrottle,” NSDI (2024) | Can end-to-end SLOs guide per-service CPU allocation? | Three microservice apps and production-shaped traces; typical 100 ms period | End-to-end p99, CPU savings, throttle ratio; dynamic quota controller | Throttle ratio is useful/correlated with latency; reported CPU savings while maintaining SLOs | Dynamic distributed controller; does not isolate worker count, rounding, or period | Measure end-to-end p99 and throttled-period fraction in a static mechanism study |
| Iyer et al., “Achieving Microsecond-Scale Tail Latency Efficiently with Approximate Optimal Scheduling,” SOSP (2023) | Can approximate optimal scheduling improve throughput at tail SLOs? | Microbenchmarks and in-memory LevelDB; mixed service times | Throughput, p99.9 slowdown; cooperative preemption/JBSQ | Queue/scheduler design moves throughput–tail frontier; up to 83% LevelDB throughput gain at target | No cgroup quota/fraction/period; specialized runtime | Report trade-off curves and service classes, not one winner |
| Enberg, Rao, Tarkoma, “The Impact of Thread-Per-Core Architecture on Application Tail Latency,” ANCS (2019) | How does thread-per-core affect KV tails? | Sphinx vs Memcached; Linux; IRQ/steering variants | Tail latency/throughput; thread-per-core and placement | Up to 71% lower tail latency in studied comparison; interfaces/steering limit gains | Networked application architecture; no quota/period | Control CPU placement and separate multiplexing from queue/network effects |
| Dean, Barroso, “The Tail at Scale,” CACM (2013) | Why do rare delays dominate large fan-out services? | Production experience/conceptual techniques | High-percentile latency/utilization | Variability and utilization amplify distributed tails | Not a quota or pool-sizing experiment | Tail motivation only; no distributed generalization from CPUQuotaLab |
| Hall et al., “Harvesting Spare CPU Resources in Container Systems,” NSDI (2026) | Can spare cores be harvested while protecting container p99? | Kubernetes, latency-sensitive/co-located apps, interrupt-aware kernel module | p99 and harvested cores/utilization | Up to 75% unused cores harvested while keeping p99 within 4% of standalone | Core isolation at microsecond scale; not rounding or application pools | Reinforces placement/interference threats and limits of time partitioning |
| Linux cgroup v2/CFS bandwidth documentation | What are quota, period, and counter semantics? | `cpu.max`, `cpu.stat`, PSI, cpuset | Kernel interfaces | Exhaustion throttles until replenishment; smaller periods trade burst capacity for latency consistency; counters have hierarchy caveats | Documentation, not comparative evidence | Authoritative definitions and 10/100 ms rationale |
| Linux burstable-CFS patch series (Chang, 2021) | Can saved quota reduce burst-related tails? | Java workloads and `schbench`; quota/period/burst | p99/p99.9/RPS; CFS burst | Reports large tail reductions in studied burst cases; longer periods allow burst but longer wait | Patch evidence, burst enabled, no pool-rounding comparison | Keep burst zero, record it, interpret period as burst/stall control |
| Rust `available_parallelism()` implementation/docs | What portable parallelism hint should Rust return? | Linux cgroup/affinity discovery | Returned integer; quota rounded down, minimum 1 | Modern Rust is quota-aware when interfaces are readable and conservatively floors fractional quota | API policy, not performance evidence; version dependent | A real floor baseline to compare with explicit ceiling/fixed counts |
| Uber `automaxprocs` and PR #13 | How should Go parallelism follow container quota? | Production load-balancer example at 2 CPUs; fractional policy debate | RPS, p50, p99.9, throttling; library sets `GOMAXPROCS` | Integer overcommitment worsened reported p99.9/RPS; floor debate trades underuse for throttle avoidance | Production evidence lacks controlled fractional/period comparison | Direct motivation for controlled floor/ceiling study |
| Go 1.25 container-aware `GOMAXPROCS` | What default should Go use under CPU limits? | Runtime policy and conceptual burst examples | Operational rationale; ceiling and dynamic refresh | Rounds fractional limit up to use full quota; warns about burst/latency trade-offs | Engineering choice, not controlled study; GC/goroutines add mechanisms | Legitimate opposing policy; language-neutral native-thread comparison |
| Open-source cgroup/runtime probes | What counts do tools/runtimes expose under fractional limits? | Small Rust/Tokio/cgroup probes | Detected counts | Examples confirm Rust floor and quota awareness | Non-peer-reviewed; no rigorous performance evaluation | Implementation cross-check only, not result evidence |

## Overlap assessment

Substantial overlap exists: quota overcommitment and tail latency, period/burst semantics, mixed service-time scheduling, end-to-end throttle feedback, and fractional floor/ceiling are each already studied or debated. None should be claimed individually as novel.

No reviewed source crosses fractional floor/ceiling pool sizing with two periods at equal long-run quota, equal-mean uniform/mixed native CPU work, and intended-arrival end-to-end/queue/execution tails separately for short and long tasks.

The only defensible claim, if successfully executed, is:

> A controlled single-host empirical characterization of one unresolved rounding trade-off under two replenishment periods and two synthetic service-time distributions.

Do not claim the combination has never been studied, generalizes to GC/async runtimes, or establishes a universal policy.

## Feasible opportunity

Use two CPUs/100 ms only as a reproduction anchor. Focus confirmatory effort on 1.5 CPUs because floor and ceiling differ while both are meaningful. Compare 10/100 ms with burst disabled using one FIFO queue, and expose short/long end-to-end consequences. Treat quotas 1/2 and four workers as pilot-driven secondary work.

## Primary sources

- [Jeffery et al. preprint](https://arxiv.org/abs/2407.11582)
- [Concord, SOSP 2023](https://dslab.epfl.ch/pubs/concord.pdf)
- [CPU Bandwidth Control for CFS, 2010](https://kernel.org/doc/ols/2010/ols2010-pages-245-254.pdf)
- [Mitigating Unnecessary Throttling, SBAC-PAD 2022](https://rakeshk.folk.ntnu.no/pubs/SBACPAD22.pdf)
- [Autothrottle, NSDI 2024](https://www.usenix.org/system/files/nsdi24-wang-zibo.pdf)
- [Thread-Per-Core Tail Latency, ANCS 2019](https://penberg.org/papers/tpc-ancs19.pdf)
- [The Tail at Scale, CACM 2013](https://research.google/pubs/the-tail-at-scale/)
- [Harvesting Spare CPU Resources, NSDI 2026](https://www.usenix.org/system/files/nsdi26-hall.pdf)
- [Linux cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html) and [CFS bandwidth](https://docs.kernel.org/scheduler/sched-bwc.html) documentation
- [Linux burstable CFS patch discussion](https://lkml.iu.edu/2103.2/00036.html)
- [Rust `available_parallelism()` docs](https://doc.rust-lang.org/std/thread/fn.available_parallelism.html), [Unix source](https://doc.rust-lang.org/stable/src/std/sys/thread/unix.rs.html), and [cgroup PR](https://github.com/rust-lang/rust/pull/92697)
- [Uber `automaxprocs`](https://github.com/uber-go/automaxprocs) and [floor PR](https://github.com/uber-go/automaxprocs/pull/13)
- [Go container-aware `GOMAXPROCS`](https://go.dev/blog/container-aware-gomaxprocs)
