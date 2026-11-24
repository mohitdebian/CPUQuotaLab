# CPUQuotaLab Research Log

This diary records work when it occurs. Tool observations are separated from interpretations and decisions. Times use Asia/Kolkata (UTC+05:30).

## 2026-11-24 — Phase 1 environment discovery

**Timestamp note.** The environment metadata snapshot records `2026-11-24T15:20:51+05:30`. Exact activity start/end times were not recorded, so no range is asserted.

**Objective.** Establish whether a controlled CPU-bandwidth experiment is possible on the actual host before designing or implementing the benchmark.

**Commands executed.** Read-only discovery used `uname`, `/etc/os-release`, `lscpu`, `free`, `taskset`, `/proc/self/status`, `/proc/self/cgroup`, `findmnt`, cgroup v2 interface files, tool version commands, `systemd-detect-virt`, sysfs CPU topology/frequency/thermal files, and a `perf stat` smoke test. Quota application was tested in a short-lived user transient scope with `systemd-run --user --scope -p CPUQuota=200%` and the scope's `cpu.max` and `cpu.stat` were read.

**Tool observations.** The project directory contained no files and Git had no commits. The host is native Ubuntu 26.04.1 LTS, kernel 7.0.0-43-generic, on an Intel Core i5-12450HX with 8 physical cores (4 P + 4 E), 12 logical CPUs, SMT on P-cores, and unrestricted initial affinity `0-11`. Unified cgroup v2 is mounted and the CPU controller is available. The transient scope reported `cpu.max = 200000 100000`, independently confirming a two-CPU bandwidth limit. The current hierarchy has no inherited quota. Docker 29.1.3 is accessible and uses systemd with cgroup v2. Unprivileged `perf stat` failed because `kernel.perf_event_paranoid=4`. Procfs, `cpu.stat`, CPU pressure, sysfs frequency, and core temperature data are available. Rust/Cargo, Pandas, SciPy, and LaTeX were not found; Python 3.14.4, NumPy 2.5.4, and Matplotlib 3.11.2 are present.

**Unexpected behavior.** `cpu.max` and `cpuset.cpus.effective` were not present in the Codex/Chromium leaf scope even though the relevant controllers exist higher in the hierarchy. This confirms that resource detection cannot assume all interfaces exist at the leaf and must walk ancestors. The host is Ubuntu rather than the expected Fedora installation.

**Interpretation.** The primary experiment is feasible without privileged changes by placing only the server in a transient user scope. Hardware performance counters are not necessary for the minimum viable study. Hybrid cores, SMT, dynamic frequency, thermals, and interactive background load are important confounders.

**Decision.** Prefer a systemd user transient scope over Docker for the initial study: it makes server/generator separation and host cgroup counter inspection simpler while exercising the same kernel CPU bandwidth controller. Keep the 100 ms default quota period. Propose isolating the server to P-core logical CPUs `0-7` and the generator to E-core CPUs `8-11`; this decision must be reviewed in Phase 2 because it changes the visible/allowed-CPU baseline from 12 host CPUs to 8 allowed CPUs.

**Limitations.** This was a capability check, not a benchmark. No performance result was collected. The transient quota test did not run a sustained workload, so throttling-counter behavior still needs validation in the pilot.

**Next step.** Review the Phase 1 plan and make the scientific placement and material-effect decisions before implementation.

## 2026-11-24 — Phase 1 literature review and scope refinement

**Timestamp note.** Exact activity start/end times were not recorded.

**Objective.** Determine what prior work already establishes and identify a narrow contribution that can be completed honestly in three to four days.

**Sources examined.** Original papers or first-party pages were read for Jeffery, Jensen, and Mortier (arXiv:2407.11582); Iyer et al. (SOSP 2023, Concord); Turner, Rao, and Rao (Linux Symposium 2010); Ugedal and Kumar (SBAC-PAD 2022); Enberg, Rao, and Tarkoma (ANCS 2019); and Dean and Barroso (CACM 2013). The official Linux cgroup v2 and CFS bandwidth-control documentation, Docker CPU-resource documentation, Rust `available_parallelism()` documentation, Intel processor specifications, and EPFL RS3Lab/DSLab project pages were also inspected. The gRPC commit was verified; the pull-request page timed out during retrieval.

**Tool observations.** Jeffery et al. directly study OS-thread overcommitment under quotas and use a Rust Fibonacci workload with open-loop demand, 5-second runs, and five repetitions; they do not retain queue latency in the quota analysis. Concord demonstrates that scheduler organization creates throughput/tail-latency trade-offs but targets microsecond-scale dispatch rather than cgroup sizing. Kernel documentation confirms that quota exhaustion throttles runnable threads until replenishment and that `cpu.stat` throttling counters are non-hierarchical. Rust documents `available_parallelism()` as a simplified, recomputed estimate that can account for steady-state limits but may overcount if cgroup or affinity queries fail.

**Interpretation.** A claim that quota-aware sizing itself is novel would be false. A useful small study can instead replicate the basic phenomenon while improving measurement discipline: intended-arrival latency, bounded admission, drop accounting, queue/execution decomposition, cgroup counter deltas, mixed-duration requests, fixed loads, and run-level uncertainty.

**Decision.** Treat CPUQuotaLab as an independent replication-and-extension on one modern hybrid Linux laptop. Do not implement adaptive scheduling in the initial study and do not generalize synthetic results to production gRPC services.

**Limitations.** The closest paper is an arXiv preprint rather than a verified peer-reviewed venue. Literature review was focused rather than systematic and may be expanded later. No citation was inferred from snippets alone where the original paper was available.

**Next step.** Researcher review of `RESEARCH_PLAN.md`, especially the placement policy, 5% material-throughput margin, offered-load selection rule, and runtime budget.

## 2026-11-24 — Research-direction refinement

**Timestamp note.** Exact activity start/end times were not recorded.

**Objective.** Test whether fractional quotas, period length, rounding policy, mixed-duration work, and end-to-end class-specific latency form a defensible targeted extension of arXiv:2407.11582.

**Sources and searches.** Focused searches covered arXiv, USENIX proceedings, primary paper copies, Linux kernel documentation/patches, Rust standard-library source/history, Go runtime documentation/proposals, and Uber's `automaxprocs`. Results are in `RELATED_WORK_MATRIX.md`. Particularly relevant additions were Autothrottle (NSDI 2024), Harvesting Spare CPU Resources (NSDI 2026), the CFS burst series, Rust's quota-aware `available_parallelism()`, Uber's floor change, and Go 1.25's opposing ceiling policy.

**Tool observations.** Runtime policies disagree: Rust documents floor; Uber adopted floor after debating underutilization versus throttling; Go 1.25 rounds up. Reviewed sources examine the component questions but not their complete interaction. Transient scopes for 1.5 CPUs produced `cpu.max = 15000 10000` at 10 ms and `150000 100000` at 100 ms; `cpu.max.burst = 0` in both. The host's `sched_cfs_bandwidth_slice_us` is 5000 µs, which is large relative to the 10 ms period and must be treated as a kernel-specific interaction.

**Interpretation.** Fractional floor versus ceiling is more defensible than a broad integer sweep and maps to an active runtime design disagreement. This shows relevance, not novelty.

**Decision.** Center the primary matrix on 1.5 CPUs, 10/100 ms, workers 1/2/8, equal-mean uniform/mixed work, two fixed loads, and five repeats (120 runs). Retain a 20-run integer reproduction anchor. Add four workers and integer boundary checks only if pilot evidence warrants them.

**Limitations.** The search was time-bounded and not systematic. Search failure cannot establish novelty. Runtime discussions are not peer-reviewed experiments. The revised matrix still requires Phase 2 review.

**Next step.** Review the five decisions at the end of revised `RESEARCH_PLAN.md`; implementation has not started.

## 2026-11-24 — Phase 2 protocol validation and refinement

**Timestamp note.** Exact activity start/end times were not recorded. This work completed before the recorded Rust-installation start at `2026-11-24T16:05:55+05:30`; the former `17:00–17:40` heading was inconsistent with recorded execution time and has been removed rather than replaced with an invented range.

**Objective.** Address the conditional-approval issues before protocol freeze: stress-load selection, generator timing, topology, class-tail sample size, interval/drain accounting, cgroup containment, sustained CPU accounting, reproduction language, language-runtime scope, and evidence labeling.

**Commands executed.** Re-read `lscpu`, `/sys/devices/system/cpu/cpu*/topology/{core_id,thread_siblings_list}`, per-CPU maximum frequencies, CPU online/SMT state, and affinity. Created short-lived user scopes at 1.5 CPUs with 10 ms and 100 ms periods, placed two Python CPU-burn processes at affinity `0-7`, inspected parent/child cgroup membership and affinity, and calculated pre/post `cpu.stat` deltas. Read official Rust and rustup installation/profile documentation. No compiler or package was installed.

**Failed validation attempts.** The first Python 3.14 multiprocessing test failed before load because its default forkserver could not reload a program supplied as `<stdin>`. It was repeated with an explicit `fork` context; no output from the failed attempt was treated as evidence. The first topology-print command used an invalid `sort` separator and suppressed the listing; the sysfs read was repeated without sorting.

**Tool observations.** Topology confirms 12 online logical CPUs and eight physical cores. CPUs `0-7` form four SMT sibling pairs with 4.4 GHz reported maxima; CPUs `8-11` are four single-thread sibling sets with 3.1 GHz maxima. This matches the Intel 4P+4E specification, though the kernel does not expose `core_type`. In the successful sustained tests, all child processes inherited the transient server scope and affinity `0-7`; the outside controller remained in the Codex/Chromium application scope. At 10 ms, 4,511,664 µs CPU usage over 3.004648 s produced normalized quota utilization 1.001041 and 300/301 throttled periods. At 100 ms, 4,556,995 µs over 3.027988 s produced 1.003305 utilization and 30/31 throttled periods. These validate accounting and containment, not application performance.

**Scientific decisions.** Replace a generic “near saturation” rate with a discriminating capacity-stress condition: where pilot capacities permit, offered load must exceed one-worker stable capacity by at least 10% while remaining at or below 90% of two-worker capacity. Preserve overload, drops, and incomplete requests. Require at least 10,000 completed long requests per non-overloaded mixed cell (normally at least 100,000 total) for class p99. Define 5 s warm-up, 30–120 s frozen measurement, 10 s maximum drain, timely goodput as primary throughput, and conditional-on-completion percentile language under drops/incompletes. Add explicit per-run containment assertions and generator timing gates.

**Interpretation.** The counters track the configured bandwidth closely under sustained demand, and the different `nr_periods` deltas match the period lengths. High throttled-period fractions are expected for this deliberate two-process saturation check and do not predict benchmark outcomes. The 5 ms runtime slice is half the 10 ms period, so short-period results remain kernel-specific.

**Toolchain decision.** Official `rustup` is the preferred user-local installer. The proposed safe workflow downloads the official installer to a temporary file for inspection, installs stable Rust with the default profile (including Cargo, Rustfmt, and Clippy), and records exact versions. This mutates `~/.rustup`, `~/.cargo`, and possibly shell PATH configuration, so installation awaits explicit researcher approval.

**Dependencies.** Use existing Python 3.14.4, NumPy 2.5.4, and Matplotlib 3.11.2 initially. Do not add Pandas or SciPy without a demonstrated need.

**Limitations.** The CPU-burn harness used processes rather than the not-yet-built Rust workers and ran only three seconds. It validates the Linux control/measurement path, not the eventual benchmark implementation or hypotheses. Generator timing tolerances are protocol gates that still require pilot measurement.

**Next step.** Researcher review of `METHODOLOGY.md` and explicit approval or rejection of the user-local Rust installation. Implementation remains paused.

## 2026-11-24 16:05:55–16:07:55 — Approved Rust installation

**Authorization.** The researcher approved a non-root installation through the official `rustup` mechanism.

**Procedure and provenance.** At `16:05:55+05:30`, the installer was downloaded from `https://sh.rustup.rs` to a temporary file, not piped directly into a shell. Its SHA-256 was `d890e2fef6fa991b19cde2e608199bc1dca4e37f41f884edf8849ff693048de6`, and its opening section was inspected before execution. The official default profile installed stable Rust under the user account. The exact version capture occurred at `16:07:55+05:30`.

**Installed versions.** `rustup 1.29.3 (edbc831ce 2026-11-02)`; `rustc 1.100.0 (0ef1bc386 2026-11-09)`, LLVM 23.1.5; `cargo 1.100.0 (3acc79c0c 2026-11-05)`; `rustfmt 1.11.0-stable`; `clippy 0.1.100`. `rust-toolchain.toml` pins `1.100.0` with Rustfmt and Clippy.

**Failure and recovery.** The initial installer command exceeded the command runner's observation window while the installer continued in the background and completed. Later, the exact version pin caused `rustup` to install the versioned toolchain alongside the equivalent `stable` alias. Stale polling processes were terminated after inspection; the exact pinned compiler was then verified directly. No root privilege or system package manager was used.

## 2026-11-24 — Phase 3 implementation and correctness checks

**Timestamp note.** Exact implementation start/end bounds were not captured. The release build and tests completed before the first recorded smoke attempt at `16:20:56+05:30`.

**Implementation.** Added one Rust binary with `server`, `generator`, and `detect` modes. The server contains a bounded nonblocking FIFO admission path, explicit drop responses, configurable native OS-thread workers, deterministic integer work, response serialization, cgroup snapshots, and a ten-second configurable drain deadline that converts leftover admitted requests to explicit incomplete outcomes. The external generator uses absolute intended-arrival times, a scheduling thread independent of socket writing, a response reader, backlog accounting/abort threshold, and immutable NDJSON request records. Cross-process timestamps use checked `CLOCK_MONOTONIC` calls.

**Orchestration.** Added a Python standard-library runner that creates unique attempts, puts only the server in a transient user scope, applies P-core/E-core affinity, repeatedly enumerates all threads to validate affinity, verifies server/generator cgroup separation, checks `cpu.max`, and retains failed attempts. Added a NumPy-only summarizer with the documented `linear` quantile method and class-specific timing/outcome summaries.

**Correctness checks.** The final validation ran from `16:26:56` to `16:27:03+05:30`. `cargo fmt -- --check` passed. `cargo clippy --all-targets --all-features -- -D warnings` passed. `cargo test --all-targets --all-features` passed 26 unit tests and one end-to-end test (27 total, zero failed). The end-to-end test starts the real Unix-socket server and generator and reconciles generator/server counts. A release build and `detect` command passed. Python scripts passed bytecode compilation.

**Linting adjustment.** An initial Clippy run with the project's opt-in `pedantic` lint group plus `-D warnings` produced 51 style/documentation diagnostics. No correctness failure was hidden. The project now enables the standard `clippy::all` group; all of those warnings are fixed or excluded by removing the optional pedantic group, and the final requested strict Clippy command passes with zero warnings.

## 2026-11-24 16:20:56–16:21:49 — Functional smoke validation

**First attempts at 16:20:56.** Both were invalidated immediately because the monitor inspected the generator process in the short interval after `Popen` but before the `taskset` launcher had executed. It observed inherited affinity `0-11`, stopped the attempts, and retained both manifests as failed. No performance inference was made. The runner was corrected to allow at most one second for initial launcher affinity to stabilize, while retaining strict repeated checks thereafter.

**Normal smoke at 16:21:26.** A 1.5-CPU/10 ms, two-worker, mixed-workload attempt scheduled and sent 2,400 total requests (2,000 measurement); all completed, with no drops or incompletes. Sender backlog was at most one. All nine recorded affinity checks passed, every server thread shared the restricted scope, and `cpu.max` was `15000 10000`. Measurement counter deltas were 618,386 µs usage, 100 periods, one throttled period, and 710 µs aggregate throttled time.

**Second orchestration failure at 16:21:26.** The overloaded server completed and exited normally after closing the response stream while the generator was still serializing its summary. The monitor treated any server exit before generator process exit as failure and terminated the generator, so no generator summary was produced. The attempt remains labeled failed. The runner was corrected to allow a zero-status server exit during generator post-processing, while still rejecting nonzero exits and continuing generator affinity checks.

**Overload smoke at 16:21:48.** A 1.5-CPU/100 ms, one-worker, mixed-workload attempt scheduled and sent 30,000 total requests (25,000 measurement). It completed successfully as an apparatus test: measurement outcomes were 2,002 completions and 22,998 explicit queue-full drops; no request was silently omitted or left incomplete. Maximum sender backlog was 45 and the generator did not abort. All seven recorded affinity checks passed and `cpu.max` was `150000 100000`. The server accounted for all 30,000 total requests as 2,342 completed and 27,658 queue-full drops.

**Generator timing observations.** The normal smoke had median absolute scheduler lag 0.091 µs, p99 0.476 µs, and no measurement request later than one interval. The overload smoke had median 0.054 µs, p99 0.074 µs, and 0.02% later than one interval. Both pass the provisional arithmetic gate, but these very short smoke runs do not establish the Phase 4 timing tolerance or scientific capacity.

**Final post-change smoke at 16:27:12–16:27:13.** After adding process CPU clocks and explicit generator scheduling controls, a 1.5-CPU/10 ms, two-worker mixed check scheduled 1,400 requests (1,000 measurement) and reconciled all 1,400 as completed with no drops or incompletes. Seven affinity checks passed; sender backlog was at most one; detected effective quota was 1.5; Rust reported one available parallel unit inside the scope; and both process CPU-time fields were populated. This confirms the final output schema works, not that the measured policy is superior.

**Evidence label.** These are capability and failure-path observations only. Durations, rates, and workload costs were not pilot-calibrated; no Phase 3 number is evidence for the research hypotheses.

**AI assistance.** Codex drafted and edited code and documentation, ran the recorded commands, and summarized outputs under researcher-approved scope. Details and responsibility boundaries are in `AI_ASSISTANCE.md`.

**Next step.** Researcher reviews Phase 3 architecture and limitations. If approved, Phase 4 calibrates service costs, generator timing, capacities, queue sizes, and measurement duration, then freezes a versioned protocol addendum before confirmatory data collection.

## 2026-11-24 16:46:44–18:32:46 — Phase 4 pilot and audit

**Timestamp basis.** The start is the recorded author time of Git checkpoint `ae4ea0a`; `18:32:46+05:30` is the actual report-stage clock capture. Individual attempts retain nanosecond wall start/end times in their manifests.

**Source audit.** Reviewed the worker pool, bounded queue, clock placement, workload, open-loop generator, socket handling, accounting, drain, and cgroup code. Repaired three scientific defects before pilot inference: admission time now occurs inside the queue critical section; emitted requests survive partial transport failures in the audit ledger; and the drain deadline starts at measurement-end control rather than delayed EOF. Added current-thread CPU time per completed computation and explicit planned/unissued/failed accounting. Final audit tests passed.

**Checkpoints.** Committed audited instrument `ae4ea0aef1945789bb4f3c4f929f40d26138fc1a` at `16:46:44+05:30`. Minimal-work measurement then showed approximately 123 µs restricted-scope CPU/request with per-response flushing. Removed the per-response flush, reran validation, and committed `d7e2679e41700f3c016cae3fdbec1cde8ced2175` at `16:52:55+05:30`. The repeated minimal-work run measured about 110 µs restricted CPU/request. These are overhead estimates, not corrections applied to results.

**Workload calibration.** Three 10,000-request mixed batches with 76,000 short and 1,140,000 long iterations measured short mean worker CPU time 0.477–0.482 ms and long mean 5.179–5.211 ms. Their 90/10 weighted measured mean was 0.947–0.954 ms. Exact weighted iterations (182,400) measured 1.067–1.106 ms in uniform runs. Candidate uniform runs at 160,000, 145,000, 141,000, and 137,000 iterations were retained; 141,000 measured 0.973 ms and is the proposed measured-cost control.

**Generator finding.** Low scheduler-emission lag did not guarantee low transmission delay. Every record now retains intended, emission, socket-write start/end, server receive, and admission times. Ninety-second feasibility runs had p99 write-completion lag 145–198 µs, maximum backlog 5–6, and no transport failures, but the late-write fraction reached 0.145%, narrowly exceeding the provisional 0.1% rule. Proposed transport calibration is p99 ≤`max(250 µs, 25% interval)`, late fraction ≤0.5%, backlog ≤32, and zero failures, while retaining the stricter scheduler gate.

**Mixed capacity.** AC-powered 15-second refinements bracketed one-worker stable capacity at 1,800–<1,900 requests/s and two-worker capacity at 2,600–<2,700 for both 10 and 100 ms. Proposed common mixed rates are 1,200 moderate and 2,000 stress, with queue capacity 500.

**Sample size.** Two 90-second/1,200 requests/s mixed runs and an eight-worker cross-check each completed all 108,000 measurement requests, including 10,829 long requests. The per-run 10,000-long target is feasible at a common 90-second duration.

**Environmental failure retained.** During the final calibrated-uniform capacity sequence, AC changed from online to offline. The 10 ms attempts recorded AC power; the 100 ms attempts recorded battery discharge, `low-power` platform profile, and reduced frequencies. The latter are invalid for period/capacity inference and were not discarded. AC remained offline at the `18:29` analysis stage, so replacements were not manufactured under inconsistent power.

**Anchor limitation.** Old-control anchor validation at common 1,800/2,300 requests/s completed every request for two and eight workers, but it used 182,400 uniform iterations. It must be repeated with the proposed 141,000-iteration control on AC before freeze.

**Raw evidence.** 183 completed pilot attempt directories occupied approximately 2.0 GB at analysis time. All commands, manifests, raw NDJSON, failures, environment samples, and summaries remain under `results/pilot`. Pilot results are excluded from confirmatory directories.

**Outputs.** Generated `PILOT_REPORT.md`, proposed inactive `FROZEN_PROTOCOL.md`, processed capacity rows, and three exploratory figures using NumPy and Matplotlib. Phase 5 remains prohibited. The proposal explicitly leaves uniform and anchor rates TBD pending AC-powered reruns.

## 2026-11-24 18:37:13–19:16:32 — AC-powered Phase 4 completion block

**Timestamp basis.** The start is the recorded Git author time of environment-capture revision `413428b`; the end is the final mixed-boundary manifest end time. Individual attempts retain nanosecond start/end values. No activity time was invented.

**Power and environment.** After the researcher connected the charger, AC was verified online. The platform profile automatically changed from `low-power` to `performance`; no host power setting was modified. Final evidence cited for capacity selection began and ended with AC online and the performance profile. Earlier battery attempts remain preserved and excluded.

**Generator refinement.** Dedicated generator roles were added (`cb095c4`), the socket writer was changed to busy polling on E-core CPU 9 (`583f56b`), and the scheduler was allowed to migrate only within E-core CPUs 8–11 (`5a3d0aa`). The reader remained on CPU 10. A final 90-second run completed all 108,000 requests, including 10,829 long requests, with scheduler/write p99 of 112.252/125.709 µs, late fractions of 0.504%/0.512%, backlog 5, and no transport failure. The calibrated validity gate was documented and committed with regenerated figures at `0e1b0b1`.

**Final capacities.** Mixed one-worker capacity was sustainable at 2,000/s and overloaded at 2,100/s under both periods; two workers were sustainable at 2,600/s. Proposed shared mixed rates are 1,200/2,200 with FIFO 550. Calibrated-uniform capacity was sustainable at 2,600/s for one worker and 3,800/s for two, with the next 2,700/4,000 points showing queue growth or drops. Proposed uniform rates are 1,800/3,200 with FIFO 800. The two-CPU conceptual anchor was sustainable at 4,800/s and unstable at 5,200/s for the common worker comparison; proposed rates are 3,200/4,300 with FIFO 1,075.

**Evidence volume and proposal.** Before the final selected-rate check, Phase 4 retained 316 pilot attempt directories totaling approximately 5.17 GB, including failures and superseded attempts. The proposed 140-run matrix uses 90-second measurements, has a 4.08-hour timed upper envelope, an operational estimate of 5–7 hours, and a 30 GB free-space reservation. `PILOT_REPORT.md` and proposed `FROZEN_PROTOCOL.md` v0.2 now contain the completed evidence. Phase 5 was not started and awaits explicit researcher approval.

## 2026-11-24 19:31:05–19:31:25 — Final selected-rate timing validation

Ran the proposed mixed stress setting at 2,200/s with two workers, a 100 ms period, FIFO 550, AC online, and performance profile. All 33,000 measurement requests completed within the window. Scheduler/write p99 was 0.180/8.312 µs, maximum sender backlog was 1, and no request failed. The attempt passed the calibrated generator gate and is retained as `final-validate-mixed-stress-p100-w2-r2200`. Its clean manifest records source revision `e83ab8323a53665ecd68bb82c79a74420e7e866b`. This was a pilot apparatus validation, not a Phase 5 confirmatory run. Final pilot evidence comprises 317 attempt directories.

## 2026-11-24 — Phase 5 protocol audit and staged activation

**Authorization.** The researcher authorized an initial 16-run mixed-workload subset while preserving the complete 140-run design. The time target was reduced to 40–45 minutes without changing 90-second measurements, workloads, rates, validity gates, or outcome reporting. Detailed application/interview material and nonessential repository expansion were postponed.

**Paper correction.** Direct re-reading of Jeffery, Jensen, and Mortier (arXiv:2407.11582v1) confirmed that their main open-loop `fib(30)` overcommitment benchmark uses Rust native OS threads, while Figure 5 separately uses Go to demonstrate quota-unaware runtime sizing. Earlier prose that characterized the overall study as a Go-runtime experiment was corrected. The anchor remains conceptual because hardware, kernel, workload, load regime, and duration differ.

**Audit.** The frozen benchmark binary still hashes to `560be7281c580a4fc0e4bc521269f75d50ac54f3940e300d68042637b889e095`; `Cargo.lock` hashes to `fbca3fa74a1f84842dae29cd1e91b5e3ce31cdaf58133e8597462466e9f61cf9`. Rust 1.100.0 remained pinned. Rustfmt, strict Clippy, 28 unit tests, one end-to-end test, release build, and Python bytecode validation passed. No benchmark implementation or frozen parameter changed. The audit clarified that environment is sampled every second while affinity/cgroup placement is checked approximately every 200 ms.

**Schedule and retry policy.** Generated `experiment_matrix.json` before confirmatory outcomes using master seed `2027112401`: 120 primary plus 20 conceptual-anchor cells. The initial stage is blocks 1–2 of the mixed workload with 1/2 workers, both periods, and both loads. Matched cells share request seeds and lead-in phase offsets. The resumable runner refuses duplicate directories, retains every attempt, permits at most one replacement per cell, and stops after a second invalid attempt.

**Initial preflight.** AC was online, the platform profile was `performance`, no conflicting benchmark process was found, and 16 GiB free storage exceeded the 4 GiB initial-stage safety floor. Package temperature was 66°C, above the frozen 60°C start gate, so collection did not start until passive cooling satisfied the gate. No system setting was changed.

## 2026-11-24 19:51:50–20:20:56 — Phase 5 initial confirmatory collection

**Collection.** Executed the predeclared initial subset in `stage_order` using activation checkpoint `b304aec39f697abcbd62611ea9a2df6ac1abec0f`. Fifteen of sixteen cells produced valid data. Valid runs offered 2,340,000 measurement requests: 2,314,313 completed, 25,687 dropped, none incomplete, and none transport-failed. All valid attempts passed quota, burst, accounting, generator, power/profile, affinity/cgroup, and applicable long-class sample-size gates.

**Invalid attempts and stop.** The block-2, 10 ms, two-worker moderate cell recorded start-package temperatures of 63°C and 64°C on its original and replacement attempts. Both raw directories were retained and indexed. After the second invalid attempt, the runner stopped according to the predeclared maximum-two-attempt policy. A third attempt was not made. Performance outcomes played no role in invalidation.

**Timing.** Collection/progress timestamps record 29 minutes 5 seconds from initial start to the final progress update, including passive cooling pauses and the replacement. No measurement was shortened. The 40–45 minute target was treated as subordinate to validity.

**Preliminary analysis.** Analyzed 15 valid run-level observations only. Across seven available one-versus-two-worker pairs, median timely-goodput change was +3.06% (below the 5% threshold), while median conditional p99 change was −90.36% (all available pairs passed the combined latency materiality rule). One-worker stress dropped 2.77–3.74%; two-worker stress dropped none. Two-worker stress p99 was 27.48–28.03 ms at 10 ms and 14.36–14.42 ms at 100 ms. These are descriptive preliminary observations, not significance claims.

**Artifacts.** Generated run/effect CSVs, four priority figures in PNG/PDF, collection/statistical/research reports, and `dataset_provenance.json` with SHA-256 for 17 immutable attempt directories totaling 1,741,680,879 bytes. Pilot data were excluded. Detailed interview/application guides, expanded README work, and peer-review simulation were postponed as directed. The remaining 124 runs were not started.

## 2026-11-24 — Phase 6 scientific audit and artifact finalization

**Timestamp basis.** An exact Phase 6 start time was not recorded and is not inferred. Filesystem records show `SCIENTIFIC_AUDIT.md` written at `21:24:26+05:30`, the final five-page PDF generated at `21:35:00+05:30`, and the independent audit output regenerated at `21:36:29+05:30`. The completion checkpoint time is recorded by Git. No benchmark attempt was executed in this phase.

**Independent audit.** Reviewed the protocol, Rust request path, queue/workload/timestamp behavior, experiment manifests, attempt index, raw request records, analysis, figures, provenance, and related-work descriptions. Added `scripts/audit_confirmatory.py`, which ignores the derived run CSV and independently reads raw records and metadata. It reproduced 15 valid runs, 2,340,000 offered, 2,314,313 completed, 25,687 dropped, zero incomplete/failed, seven matched pairs, +3.060587% median goodput change, and -90.359088% median p99 change.

**Corrections.** Restored the exact original H1-H5 wording after finding that Phase 5 had relabeled hypotheses after outcomes. Replaced cross-period emphasis on throttled-period percentages with throttle events/s and aggregate throttled time per wall time. Split paired effects by moderate/stress load, changed the support-CPU field to a diagnostic residual, included dropped responses in queue-depth diagnostics, and documented the missing-cell/thermal-preflight limitation. Raw data were not changed.

**Mechanism assessment.** Queue waiting, not worker computation CPU time, explains most of the observed p99 difference. The 10 ms two-worker stress case also shows more normalized aggregate throttling and a larger elapsed/CPU execution gap than 100 ms. The kernel's 5 ms slice and quota/request phase are plausible explanations, but no scheduler trace establishes causation. Frequency and thermal samples do not clearly explain the difference.

**Artifacts.** Created the severity-ranked scientific audit, corrected reports, research-focused README, EPFL summary, understanding/interview guide, AI disclosure update, Phase 6 report, and editable paper source/builder. Generated and visually inspected a five-page two-column PDF. Regenerated the primary analysis/figures and independent audit output. The complete design still requires 125 additional valid runs; none were started.

**Final validation.** Rustfmt and strict Clippy passed. Cargo passed 28 unit tests and one Unix-socket end-to-end test; this was a correctness test, not a benchmark experiment. Python scripts compiled. PDF extraction found all required status statements across five pages. The tracked-file scan found no credential-like filenames, credential assignments, private home paths, or oversized raw datasets. All 15 accepted manifests record clean revision `b304aec39f697abcbd62611ea9a2df6ac1abec0f` and binary SHA-256 `560be7281c580a4fc0e4bc521269f75d50ac54f3940e300d68042637b889e095`, which matches the retained release binary. SHA-256 verification matched all 170 files and 1,741,680,879 bytes in the 17-attempt provenance inventory.

**Failures during finalization.** The first paper rendering used manual page breaks that left sparse pages; the breaks were removed and the five-page result was re-rendered and inspected. The optional ImageMagick `montage` command was unavailable, so pages were inspected individually. The first provenance-verification command incorrectly prefixed paths that were already repository-relative and failed before hashing; the corrected read-only command verified every file with zero mismatches. None of these failures changed experimental evidence.

## 2026-11-24 — Phase 7 publication-readiness preparation

**Scope.** Performed focused publication corrections only. No benchmark experiment, remaining-matrix collection, external publication, data upload, remote push, or DOI creation occurred.

**Scientific corrections.** Added numbered paper citations and verified six primary/original sources. Clarified that the measured end-to-end direction contradicts H2 without conclusively disproving the narrower quota-exhaustion mechanism. Added the non-additivity warning for separately computed percentile components. Corrected `incomplete_fraction` to use admitted measurement requests, matching the frozen protocol; all valid values remain zero. Replaced absolute compiler-elimination claims with evidence-bounded wording.

**Publication preparation.** Added host/OS/kernel/topology details, regenerated the paper, and redesigned the class/outcome figure for paper-column readability. Added MIT licensing, third-party license metadata, citation metadata without a DOI, privacy-aware dataset archival instructions/export tooling, finalized EPFL application text, and created `PUBLICATION_READINESS.md`. Raw attempt data remained immutable and excluded from Git.

## 2026-11-24 22:41:03+05:30 — Phase 7 final verification

**Consistency and artifact checks.** Recomputed the publication analysis and independent audit without running experiments. Both retained the same 15 valid runs, 2,340,000 offered requests, 2,314,313 completions, 25,687 drops, zero incomplete or failed requests, seven matched pairs, +3.060587% median timely-goodput change, and -90.359088% median completion-conditional p99 change. Verified that every derived run uses `admitted = completed + incomplete`, the application summary contains exactly 150 whitespace-delimited words, and `CITATION.cff` contains neither a DOI nor an invented release date. Rustfmt, strict Clippy, 28 unit tests, the Unix-socket end-to-end test, and Python bytecode checks passed during this phase; these were implementation validations, not benchmark experiments.

**Paper and publication boundary.** The five-page PDF was regenerated and its rendered pages inspected after the citation, wording, figure, and platform-detail corrections. The sole tracked machine-local repository path in the historical environment metadata was replaced with `${REPOSITORY_ROOT}`; no measurement field changed. The resulting public-file scan found no credentials, private absolute paths, or raw attempt data. Original manifests still contain local paths and remain excluded from Git; the documented sanitizer must be used and personally reviewed before any data deposit. No remote was configured, no file was uploaded, no DOI was created, and no remaining experiment was executed.
