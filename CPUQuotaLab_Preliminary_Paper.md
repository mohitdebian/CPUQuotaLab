# Beyond Core Counts: Investigating Fractional CPU Quotas, Bandwidth Periods, and Thread Pool Sizing Under Mixed-Duration Workloads

Author: Mohit Singh

Status: Independent undergraduate research; preliminary and not peer reviewed.

## Abstract

Linux CPU quotas specify average CPU-time bandwidth, while native thread pools require an integer worker count. This creates a rounding choice under fractional limits. CPUQuotaLab studies one versus two native Rust workers under a 1.5-CPU cgroup-v2 quota, 10 and 100 ms bandwidth periods, and a 90/10 mixture of calibrated short and long CPU-bound requests. An external open-loop generator preserves overload and records intended arrival through completion. The predeclared initial subset contains 15 valid 90-second runs from 16 planned cells; two thermal-invalid attempts leave one cell missing. Across seven matched pairs, two workers changed timely goodput by a median +3.06 percent, below the predeclared 5 percent materiality threshold, but reduced completion-conditional end-to-end p99 by a median 90.36 percent. At stress, one worker dropped 2.77-3.74 percent; two workers dropped none. Separate percentile distributions show queue waiting, rather than computation CPU time, as the dominant measured contributor. Unexpectedly, two-worker stress p99 was lower at 100 ms than 10 ms. This contradicts H2's expected overall direction but does not by itself falsify the specific quota-exhaustion mechanism. The evidence is descriptive, single-machine, and does not establish statistical significance or the scheduler-level cause.

## 1. Introduction

Containerized services commonly receive CPU bandwidth limits expressed as fractional CPUs. Linux enforces these limits as CPU time per replenishment period rather than as dedicated physical cores [2, 3]. Application runtimes and native services must nevertheless choose an integer amount of parallelism. At 1.5 CPUs, flooring to one worker prevents simultaneous use of the fractional half CPU; rounding to two enables more parallel service but can exhaust the quota early and throttle runnable work.

The practical outcome depends on queueing as well as execution. A policy that avoids throttling can still produce poor request latency if work accumulates before execution. Conversely, a policy that triggers throttling may reduce total end-to-end latency by serving the queue concurrently. CPUQuotaLab evaluates this trade-off with request-level timestamps and explicit overload outcomes.

This is independent undergraduate research. The current results are an initial subset of a planned 140-valid-run study, collected on one hybrid Linux laptop. They are preliminary and have not been peer reviewed.

The work makes three limited contributions. First, it provides a small, inspectable Rust apparatus that separates intended arrival, transmission, admission, queueing, execution, and completion. Second, it evaluates the operational rounding choice at a fractional quota using overload-visible outcomes rather than completion latency alone. Third, it reports an unexpected period interaction and decomposes the observation without turning a post-hoc mechanism into a confirmed cause. The contribution is the evidence and artifact, not a universal sizing rule.

## 2. Background and Related Work

Linux CFS bandwidth control assigns a group a quota of CPU microseconds for each period. Runtime is transferred to per-CPU runqueues in slices. Once assigned quota is exhausted, runnable threads wait for replenishment [2]. Cgroup v2 exposes the configured maximum in `cpu.max` and accounting in `cpu.stat` [3]. On this host the bandwidth slice is 5 ms, half of the short experimental period.

Jeffery, Jensen, and Mortier evaluate OS-thread overcommitment with a Rust open-loop fib(30) workload and separately demonstrate quota-unaware runtime sizing with Go [1]. Their later quota analysis excludes queue latency. CPUQuotaLab targets a narrower combination: fractional rounding, 10/100 ms periods, mixed service durations, bounded admission, and intended-arrival-to-completion tails. This is a targeted empirical extension and candidate gap, not a claim that quota-aware sizing was invented here or that novelty is proven.

Runtime policy illustrates the unresolved trade-off. Go 1.25 rounds a fractional container limit upward so the runtime can use the full limit [4]. Rust's `available_parallelism` is an approximate portable hint that considers steady-state resource limits but documents important platform limitations [5]. Production and research systems also study quota control, throttling, and tail latency, but they do not make the present single-host experiment definitive.

This distinction matters because quota and affinity answer different questions. Affinity bounds where a thread may run; quota bounds average CPU time available to the group. A 1.5-CPU quota does not reserve one and a half cores, and two runnable workers do not necessarily receive smooth service. They can run simultaneously, spend bandwidth early, and then wait. Conversely, one worker may avoid quota exhaustion while leaving half of the nominal bandwidth unusable because a single sequential worker cannot execute on two CPUs at once.

The Tail at Scale motivates reporting high percentiles [6], but tail metrics alone are unsafe under overload. A system can improve completion-conditional latency by rejecting difficult work. Therefore, this study always places p99 beside timely goodput, drop fraction, and incomplete fraction. It also treats requests within a run as correlated observations, not as millions of independent experimental replicates.

## 3. Research Question and Pre-Data Hypotheses

The primary question is: at a 1.5-CPU quota, how do one versus two workers change end-to-end p99, timely throughput, CPU use, and throttling under 10 and 100 ms periods?

H1 - rounding trade-off: At 1.5 CPUs, two workers achieve higher throughput/utilization than one but may increase throttling and p99 under capacity stress.

H2 - period interaction: A quota-exhaustion latency penalty is larger at 100 ms than 10 ms. This may be contradicted by short-period overhead, runtime-slice granularity, or phase effects.

H3 - duration-class interaction: In mixed work, long requests amplify short-task queue tails. More workers may reduce queue wait while increasing execution variability; the net effect is unknown.

H4 - quota-unaware sizing: Eight workers do not materially improve throughput over the better of one/two workers at 1.5 CPUs and increase p99 and/or CPU time per completion.

H5 - reproduction: At two CPUs/100 ms with uniform work, two workers match or beat eight-worker throughput while reducing worker execution tails, consistent in direction with the Cambridge study.

Predeclared materiality required more than 5 percent relative throughput difference; p99 required more than 10 percent and at least 1 ms absolute difference. H4 and H5 are not evaluated by the current subset.

## 4. Experimental Architecture

The Rust server listens on a Unix socket. It records receive time, attempts nonblocking admission into a mutex-protected bounded VecDeque, and responds explicitly when the FIFO is full. One or two native workers pop from the front and execute deterministic wrapping-integer work with loop-carried dependencies and a returned checksum. Workers record CLOCK_THREAD_CPUTIME_ID around computation and CLOCK_MONOTONIC for elapsed execution.

The external generator schedules absolute intended arrivals and never waits for responses. Separate scheduler, busy-poll writer, and reader roles expose socket delay and prevent response feedback from silently changing open-loop demand. Raw records distinguish intended arrival, scheduler emission, socket-write start/end, server receive/admission, execution, completion, and final outcome.

The server ran inside the restricted cgroup on P-core logical CPUs 0-7. The generator remained outside the server scope on E-core CPUs 8-11; writer and reader were pinned to CPUs 9 and 10. Manifests sampled placement, cgroup membership, power, profile, frequency, temperature, and pressure. Every accepted attempt passed the frozen apparatus gates.

### 4.1 Experimental platform

Experiments ran on Ubuntu 26.04.1 LTS with Linux 7.0.0-43-generic and unified cgroup v2. The host was an Intel Core i5-12450HX with four SMT-enabled P-cores (logical CPUs 0-7, paired 0-1, 2-3, 4-5, and 6-7) and four single-threaded E-cores (CPUs 8-11), for eight physical cores and 12 logical CPUs. The server used CPUs 0-7; the generator used 8-11 and remained outside the restricted cgroup. Runs required AC power, the performance platform profile, and a starting package temperature no greater than 60 degrees Celsius. Rust 1.100.0 was pinned, and the release-binary hash was recorded in every manifest.

### 4.2 Admission and worker synchronization

The admission path locks the queue, checks its fixed capacity, pushes accepted requests at the back, and wakes a worker. A worker waits on a condition variable, removes exactly one request from the front, releases the queue lock, and performs the CPU work outside the critical section. This gives FIFO order at the application queue while allowing concurrent execution after dequeue. Queue-full requests receive an explicit response, so overload is observable rather than represented as a fabricated long latency or silently discarded network write.

The computation uses fixed iteration counts, wrapping integer arithmetic, loop-carried state, `black_box`, and a checksum observed by the response path. These choices make wholesale elimination or closed-form replacement unlikely for the pinned build, and release-mode calibration confirmed nonzero CPU cost; they are not an absolute guarantee for every compiler or future implementation. Per-thread CPU time measures computation consumed by the worker; monotonic elapsed time includes descheduling and quota stalls. Their difference is diagnostically useful but is not a direct scheduler trace.

### 4.3 Open-loop generation and transmission audit

The scheduler assigns every request an absolute intended time and does not move later timestamps after a delay. It hands requests to an independent writer through an in-process channel, while a third role reads responses. Thus a slow socket can increase an explicit sender backlog but cannot make future arrivals wait for earlier responses. Each raw record contains intended time, scheduler emission, socket-write start and end, server receive/admission, execution boundaries, response receipt, and final outcome.

The frozen validity gate required median absolute scheduling lag no greater than 25 microseconds; scheduler and write-completion p99 no greater than the larger of 250 microseconds or one quarter of the inter-arrival interval; no more than one percent later than an entire interval; maximum sender backlog no greater than 32; zero transport failures; and exact reconciliation of intended requests. Failing an apparatus or environmental gate invalidates an attempt but does not delete it.

[FIGURE:figures/confirmatory/01_throughput.png|Figure 1. Timely goodput for individual valid runs. Horizontal marks show condition medians.]

## 5. Methodology

The quota was 1.5 CPUs: cpu.max was 15000/10000 at 10 ms and 150000/100000 at 100 ms, with burst zero. The mixed workload contained 90 percent short and 10 percent long tasks. Calibration selected 76,000 short iterations (about 0.48 ms worker CPU) and 1,140,000 long iterations (about 5.20 ms during pilot calibration). FIFO capacity was 550. Moderate and stress offered loads were 1,200 and 2,200 requests/s.

Each attempt used 5 seconds warm-up, 90 seconds measurement, and at most 10 seconds drain. The complete 140-cell schedule was randomized before confirmatory outcomes with matched seeds and phase offsets. The initial stage selected two blocks, two periods, two worker counts, and two loads for mixed work: 16 cells. One cell has no valid block-2 observation after two start-temperature failures. Both invalid directories are preserved and excluded.

The experimental unit is a complete run, not a request. Individual run values, median/range, and paired block effects are reported. Two repetitions do not support significance tests or reliable confidence intervals. Completion-only latency is always interpreted with drop and incomplete fractions.

### 5.1 Work calibration and server overhead

Release-mode calibration used a nonbinding two-CPU scope, one worker, 400 requests/s, and three 10,000-request mixed batches. Short work consumed 0.477-0.482 ms of worker CPU and long work 5.179-5.211 ms. The measured 90/10 expectation was 0.947-0.954 ms. A later uniform control was frozen at 141,000 iterations because measured CPU-cost matching was more defensible than assuming iteration cost scaled perfectly linearly.

Minimal-work tests estimated the cost of the service apparatus. Buffering responses reduced restricted-scope CPU from about 123 to 110 microseconds per response relative to flushing every response. That residual includes socket I/O, serialization, timestamping, synchronization, and support threads; it shares the quota and is intentionally part of end-to-end system cost. It must not be confused with request computation time. In confirmatory analysis, a cgroup-CPU minus completed-worker-CPU residual is retained only as a diagnostic because work can cross measurement boundaries.

### 5.2 Measurement interval and outcome accounting

Every run has setup, five seconds of warm-up, a contiguous 90-second measurement window, up to ten seconds of drain, forced close if necessary, and a final snapshot. Measurement membership is determined by intended arrival in the window, not by completion time. Warm-up work is not artificially flushed at the boundary, preserving steady-state conditions, but warm-up requests never enter measurement latency summaries.

Offered rate is intended measurement requests divided by 90 seconds. Timely goodput is measurement-tagged requests completed before the window end per second. Eventual completion includes requests that finish by the drain deadline. Drop fraction uses explicit queue-full responses divided by offered requests. Incomplete fraction is admitted work unresolved at the deadline divided by admitted work. Latency percentiles include admitted measurement requests completed by the deadline; they are explicitly conditional on completion whenever drops or incompletes exist.

CPU utilization is measurement-window cgroup usage divided by wall time times 1.5 CPUs. The analysis reports throttle events per second and aggregate throttled microseconds divided by wall microseconds. The latter may exceed one when multiple runqueues are throttled simultaneously and is not a per-request wait duration [2, 3]. Throttled-period fractions remain in raw metrics but are not used alone for 10-versus-100 ms severity because the shorter configuration has ten times as many periods.

### 5.3 Repetition, pairing, and inference boundary

The frozen full design used five randomized blocks, but the time-bounded first stage collected two blocks for 16 mixed-work cells. Paired worker effects compare runs sharing block, period, and load. The missing block-2 moderate/10 ms/two-worker cell reduces the available pairs from eight to seven. Medians summarize direction and magnitude, while displayed points preserve between-run variation. No request-level significance test is used: doing so would pseudoreplicate correlated requests from the same machine state. With at most two run-level observations, the report deliberately makes no confidence-interval or statistical-significance claim.

Each non-overloaded mixed run was designed to yield at least 10,000 long completions. With approximately 10 percent long work, this places roughly 100 long observations in the upper one percent of a run. That supports a descriptive per-run p99 but not a highly precise population quantile. Stress tails are additionally conditioned on admission and completion, so their drop fractions are co-primary context.

## 6. Preliminary Results

Fifteen valid runs offered 2,340,000 measurement requests. Of these, 2,314,313 completed and 25,687 were dropped; none were incomplete or transport-failed. The dropped requests occur only in one-worker stress cells.

At moderate load, both policies sustained roughly 1,200 timely completions/s. One-worker end-to-end p99 was 28.99-29.29 ms. Two-worker p99 was 4.43 ms at 10 ms (one valid block) and 3.66-3.67 ms at 100 ms.

At stress, one worker achieved 2,113-2,135 timely completions/s, dropped 2.77-3.74 percent, and had p99 of 291-308 ms. Two workers completed all offered requests at 2,200/s. Their p99 was 27.48-28.03 ms at 10 ms and 14.36-14.42 ms at 100 ms.

[FIGURE:figures/confirmatory/02_end_to_end_p99.png|Figure 2. Completion-conditional end-to-end p99. Drops are shown separately in Figure 3.]

Across seven available worker-count pairs, median goodput change was +3.06 percent and median overall-p99 change was -90.36 percent. Splitting by load matters: moderate medians were +0.028 and -87.41 percent (three pairs); stress medians were +3.55 and -93.01 percent (four pairs). No goodput pair crossed 5 percent; every p99 pair crossed both latency thresholds.

### 6.1 Resource use and overload outcomes

One worker used about 41.9 percent of the 1.5-CPU allowance at moderate load and 68.6-68.8 percent at stress. Two workers used about 42.9 percent at moderate and 75.4-75.6 percent at stress. This is consistent with the floor policy's sequential capacity limit, but utilization alone is not efficiency: more CPU is useful here because it eliminates queue overflow and completes the offered stress load.

At moderate load, no condition dropped requests. At stress, all 25,687 drops came from one-worker conditions. The observed one-worker p99 therefore describes only completed requests and still reaches roughly 300 ms; including rejected work as a latency value would be methodologically false. Two workers completed every offered stress request in the available runs, so their conditional tails do not hide a drop-based latency improvement.

### 6.2 Class-specific latency

Short and long tasks show the same qualitative queue effect. At one-worker stress, short end-to-end p99 was 295.78/300.30 ms for 10/100 ms periods and long p99 was 304.31/311.70 ms. With two workers these values fell to 26.87/13.51 ms for short work and 31.55/17.31 ms for long work. Long computation remains more expensive, but the hundreds-of-milliseconds one-worker tail cannot be explained by its roughly 3 ms worker-CPU p99.

[FIGURE:figures/confirmatory/04_class_latency_outcomes.png|Figure 3. Short- and long-class completion-conditional latency with drop and incomplete fractions. Drop uses offered requests; incomplete uses admitted requests.]

### 6.3 Independent recomputation

The primary analysis generated run-level CSV data and figures. A separate audit program intentionally ignores that CSV and rereads request NDJSON, server summaries, manifests, and the predeclared matrix. It independently counted 15 valid runs, 2,340,000 offered requests, 2,314,313 completions, 25,687 drops, and zero incomplete or failed outcomes. It reproduced seven matched pairs and the +3.060587 percent goodput and -90.359088 percent p99 medians to displayed precision. Agreement reduces the risk of a single analysis-path bug, though it cannot correct a flaw shared by data collection itself.

## 7. Mechanism Analysis

Separate marginal distributions identify queue waiting as the dominant measured contributor. At one-worker stress, median short queue p99 was 295.57 ms at 10 ms and 300.08 ms at 100 ms, while short worker-CPU p99 was 0.239-0.240 ms. With two workers, short queue p99 fell to 26.55 and 13.16 ms while CPU p99 remained about 0.243 ms. Long queue p99 fell from 301-309 ms to 26.88/13.75 ms; long CPU p99 remained 3.06-3.19 ms. These component p99 values are computed separately: a percentile of a sum is not generally the sum or difference of component percentiles, so no algebraic p99 decomposition is claimed.

Mean response-time queue-depth samples were roughly 458 to 471 and 469 to 473 across halves for one-worker stress. With two workers they were 8.5 to 8.7 at 10 ms and 3.6 to 3.8 at 100 ms. This supports queue wait as the proximate contributor, but not a complete scheduler-level cause.

Two-worker 10 ms stress recorded about 33.86 throttle events/s and 0.150 aggregate throttled seconds per wall second, versus 1.15 events/s and 0.015 seconds/s at 100 ms. Long elapsed-execution p99 at 10 ms was 7.57 ms versus 3.19 ms thread CPU; at 100 ms it was 3.20/3.19 ms. Period fractions alone are not directly comparable because period counts differ tenfold.

The decomposition separates a strong observation from a weak causal claim. The strong observation is that queue p99 changes by hundreds or tens of milliseconds while worker-CPU p99 changes by only microseconds. The weaker inference is that concurrency permits the service to consume fractional bandwidth that the single sequential worker cannot use. The unresolved scheduler question is why the 10 ms two-worker stress condition maintained a larger queue and accumulated more throttled runqueue time than the 100 ms condition, contrary to a simple longer-period-pause prediction.

Several mechanisms remain compatible with the records. The kernel distributes quota to per-CPU runqueues in slices [2]; the host's 5 ms slice is half the 10 ms period. Request phase relative to replenishment, migration among permitted P-core logical CPUs, and parallel depletion could therefore shape when threads stall. Short-period overhead could also matter. Recorded P-core mean frequencies and thermal ranges overlap, so frequency is not an obvious explanation, but those samples are not sufficiently controlled to exclude package-level effects. Scheduler tracing and independently randomized phase sweeps are needed before assigning cause.

[FIGURE:figures/confirmatory/03_cpu_utilization_throttling.png|Figure 4. Quota utilization and aggregate throttled time normalized by measurement wall time. The throttling counter is not direct per-request delay.]

## 8. Hypothesis Assessment and Discussion

H1 is partially supported. Two workers increased utilization and full completion, and they throttled, but p99 decreased rather than increasing. The measured overall end-to-end direction contradicts H2: 100 ms produced lower two-worker stress p99. It does not conclusively disprove the narrower quota-exhaustion mechanism because end-to-end latency also contains queueing and execution, and the study did not trace individual exhaustion intervals. A longer theoretical worst pause can coexist with lower observed overall latency if the queue and actual exhaustion pattern differ.

H3 is partially supported. Both classes have queue-dominated tails and improve with two workers, but no uniform confirmatory control exists to isolate amplification caused by long tasks. H4 and H5 are not yet evaluated.

The kernel's 5 ms slice [2], request/quota phase, and quota distribution across runqueues could plausibly contribute to the unexpected period result. Recorded P-core frequencies were similar in two-worker stress (about 3.15 versus 3.07 GHz) and thermal ranges overlap. Without scheduler tracing or additional randomized phase/period experiments, causal attribution would be speculation.

## 9. Threats to Validity

### 9.1 Internal validity

The study has only two planned blocks and one missing cell. Dynamic frequency, package power, background activity, and a thermal preflight race can affect a laptop experiment. Accepted runs passed frozen gates, while two attempts whose manifest start temperatures exceeded 60 degrees Celsius were preserved and excluded. Generator and server use different core classes and cgroups, but share cache, memory, interconnect, cooling, and package power. Affinity and membership were sampled rather than continuously traced. Queue depth is sampled at response/admission events, not measured as a time-weighted continuous process.

The audit corrected two reporting problems. The first Phase 5 analysis had replaced original hypothesis labels with outcome-shaped wording; the paper restores the verbatim pre-data H1-H5. It also compared throttled-period percentages across unequal periods without adequate warning; the corrected analysis emphasizes rates and normalized aggregate time. These corrections change interpretation and presentation, not the raw records.

### 9.2 Construct and statistical validity

The synthetic integer loop approximates CPU-bound service, not real application code with caches, allocation, I/O, or dependencies. Unix sockets remove network variability. Thread CPU clocks measure worker computation but not all server support work. Cgroup throttling counters aggregate runqueue effects and do not attribute delay to requests. Completion-conditional p99 is selection-sensitive under overload, although explicit outcome fractions reduce the risk of a misleading latency-only conclusion.

Two blocks cannot establish stable variance, confidence intervals, or significance. A missing paired cell makes the design unbalanced. Materiality thresholds communicate practical magnitude but are not probability tests. The current stage lacks uniform, eight-worker, fixed-four-worker, integer-quota, and conceptual-reproduction cells, so H4 and H5 remain untested and H3 cannot isolate the causal effect of mixed durations.

### 9.3 External validity

All observations come from one hybrid Intel laptop, one Linux/kernel configuration, one Rust implementation, and one workload calibration. They cannot be generalized directly to Kubernetes, virtual machines, cloud noisy neighbours, gRPC, different kernel versions, other cgroup hierarchies, or services whose bottleneck is memory or I/O. The Cambridge comparison is conceptual, not a faithful reproduction of its hardware, kernel, fib(30) demand, duration, or load regime [1].

## 10. Artifact and Future Work

The repository pins Rust 1.100.0 and dependencies, preserves the full schedule, attempt index, analysis, figures, and SHA-256 provenance for 1.74 GB of local raw data. `analyze_confirmatory.py` regenerates primary outputs; `audit_confirmatory.py` independently recomputes headline results from raw records. Completing the design requires 125 valid runs: 124 unstarted cells plus the missing initial cell. Mechanism follow-up should add scheduler tracing and cross-machine/kernel replication under a separately approved protocol.

Every accepted manifest records the clean source revision, frozen release-binary hash, exact command, `cpu.max`, affinity, cgroup membership, timing diagnostics, power state, temperatures, frequencies, and CPU counters. The provenance inventory hashes all files in 17 attempt directories. Invalid attempts are retained rather than overwritten. The editable paper source and deterministic builder make the PDF itself reproducible with the documented Python/reporting environment.

The immediate next scientific step is not to reinterpret these 15 runs as a completed study. It is to review this audit, decide whether to amend the thermal gate, then collect the remaining frozen cells without data-dependent tuning. A separate mechanism study could trace scheduler events, vary phase offsets more densely, and repeat across machines or kernels. Such follow-up should be versioned separately so confirmatory and exploratory evidence remain distinguishable.

## 11. AI Assistance Disclosure

OpenAI Codex assisted with literature checking, implementation, debugging, orchestration, analysis, visualization, audit, and drafting. Mohit Singh selected and approved the research direction, protocol, staged scope, and integrity requirements. The paper is subject to his personal technical review and approval before external use.

## References

[1] A. Jeffery, C. Jensen, and R. Mortier. Reducing Tail Latencies Through Environment- and Neighbour-aware Thread Management. arXiv:2407.11582v1, 16 July 2024. https://arxiv.org/abs/2407.11582.

[2] Linux Kernel Documentation. CFS Bandwidth Control. https://docs.kernel.org/scheduler/sched-bwc.html. Accessed 24 November 2026.

[3] T. Heo. Control Group v2. Linux Kernel Documentation. https://docs.kernel.org/admin-guide/cgroup-v2.html. Accessed 24 November 2026.

[4] M. Pratt and C. Amedee. Container-aware GOMAXPROCS. The Go Blog, 20 August 2025. https://go.dev/blog/container-aware-gomaxprocs.

[5] Rust Project. std::thread::available_parallelism documentation, Rust 1.100.0. https://doc.rust-lang.org/std/thread/fn.available_parallelism.html. Accessed 24 November 2026.

[6] J. Dean and L. A. Barroso. The Tail at Scale. Communications of the ACM 56(2), February 2013, pages 74-80. https://research.google/pubs/the-tail-at-scale/.
