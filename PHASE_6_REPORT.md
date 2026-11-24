# CPUQuotaLab Phase 6 Completion Report

## Status

Phase 6 is complete as a scientific-audit and artifact-finalization stage. No additional benchmark experiment was executed. The raw pilot and confirmatory directories were not modified. The study remains preliminary, single-machine, non-peer-reviewed, and incomplete.

## Scientific audit findings

No critical defect was found that invalidates the 15 accepted confirmatory runs. The accepted manifests support source/binary provenance, exact request reconciliation, cgroup settings, generator validity gates, affinity separation, power/profile gates, and environmental classification.

Major findings and corrections were:

1. The Phase 5 statistical document had replaced the original pre-data H1-H3 labels with outcome-shaped wording. The exact H1-H5 definitions from `RESEARCH_PLAN.md` are restored and assessed without redefinition.
2. Throttled-period percentages had been compared too directly across 10 and 100 ms periods. The corrected analysis emphasizes throttle events per measurement second and aggregate throttled microseconds per wall microsecond, while retaining the warning that neither counter is per-request stall time.
3. A pooled headline effect concealed different moderate and stress regimes. The report now presents load-specific paired medians.
4. The block-2/moderate/10 ms/two-worker cell is missing after two retained thermal-invalid attempts. The design is unbalanced and no inference requiring that observation is made.

Minor corrections renamed an imprecise “support overhead” residual, included drops in queue-depth diagnostics, and documented the thermal preflight race. Full severity-ranked evidence is in `SCIENTIFIC_AUDIT.md`.

## Independently verified results

`scripts/audit_confirmatory.py` ignores `run_level_metrics.csv` and recomputes from request NDJSON, server snapshots, manifests, and the predeclared matrix. It verified:

- 15 valid runs;
- 2,340,000 offered measurement requests;
- 2,314,313 completed;
- 25,687 queue-full drops;
- zero incomplete and zero transport-failed outcomes;
- seven valid matched worker-count pairs;
- median paired timely-goodput change of +3.060587%; and
- median paired completion-conditional end-to-end p99 change of -90.359088%.

At moderate load, the paired medians were +0.028% goodput and -87.41% p99 across three available pairs. At stress they were +3.55% and -93.01% across four pairs. No matched goodput effect exceeded the predeclared 5% threshold; every available p99 effect exceeded both the 10% relative and 1 ms absolute thresholds. These are practical-magnitude descriptions, not significance tests.

## Mechanism evidence

Queue waiting is the main measured contributor to the latency difference. At one-worker stress, short queue p99 was approximately 296-300 ms while worker CPU p99 was 0.239-0.240 ms. With two workers, short queue p99 fell to 26.55 ms at 10 ms and 13.16 ms at 100 ms while CPU p99 stayed near 0.243 ms. Long-task results show the same pattern.

The two-worker 10 ms stress configuration also accumulated more normalized throttled runqueue time and had a larger elapsed-versus-thread-CPU gap for long work than the 100 ms configuration. The host's 5 ms CFS bandwidth slice, quota/request phase, and quota distribution across runqueues are plausible explanations, not verified causes. Frequency and thermal samples overlap and provide no clear alternative explanation. Scheduler tracing and controlled phase/period follow-up would be needed for causality.

## Corrected hypothesis assessment

- **H1 — rounding trade-off:** partially supported. Two workers increased utilization and full completion and did throttle, but observed p99 decreased rather than increasing.
- **H2 — period interaction:** the measured overall end-to-end direction is contradicted, while the specific quota-exhaustion mechanism remains inconclusive. Two-worker stress p99 was lower at 100 ms, but individual exhaustion intervals were not traced and total latency also contains queueing and execution.
- **H3 — duration-class interaction:** partially supported. Both classes have queue-dominated tails and improve with two workers, but the absent uniform confirmatory control prevents isolating amplification caused specifically by long tasks.
- **H4 — quota-unaware sizing:** not yet evaluated because no eight-worker confirmatory cell was collected.
- **H5 — conceptual reproduction:** not yet evaluated because no two-CPU anchor confirmatory cell was collected.

## Unresolved limitations

The evidence has only two planned blocks, one missing cell, one hybrid laptop, dynamic frequency/package power, a synthetic CPU loop, Unix-socket transport, and no scheduler trace. Affinity and cgroup membership are sampled rather than continuously traced. Queue depth is event sampled. Throttling counters aggregate runqueue effects. Completion-only latency under overload is selection-sensitive, although drop and incomplete outcomes are reported. The current stage has no uniform, eight-worker, fixed-four-worker, integer-quota, or conceptual-anchor evidence and cannot establish statistical significance, a universal sizing rule, production applicability, or scheduler-level causation.

## Final deliverables

- `SCIENTIFIC_AUDIT.md` and independent `audit_recomputation.json`;
- corrected `PRELIMINARY_STATISTICAL_ANALYSIS.md` and `PRELIMINARY_RESEARCH_REPORT.md`;
- corrected reproducible analysis and audit scripts;
- four regenerated priority figures;
- five-page two-column `CPUQuotaLab_Preliminary_Paper.pdf` plus editable Markdown and builder;
- research-focused `README.md`;
- `EPFL_RESEARCH_SUMMARY.md`;
- `RESEARCH_UNDERSTANDING_GUIDE.md` with 20 interview questions;
- updated `AI_ASSISTANCE.md`; and
- this completion report and research-log entry.

## Repository and paper readiness

The repository is ready for private technical review. Raw confirmatory data remain local and are excluded from Git, with SHA-256 provenance recorded in `dataset_provenance.json`. Temporary render files are ignored. The repository scan found no tracked private key, token, password assignment, local home path, or oversized raw attempt dataset. Nothing was pushed or published.

The paper is formatted, text-extractable, and visually inspected on all five pages. Its figures, title, authorship, preliminary status, invalid attempts, missing cell, planned total, limitations, artifact status, and AI disclosure are present. “Ready” means ready for the researcher's review, not approved for submission.

Final non-experimental checks passed: Rustfmt, strict Clippy, 28 unit tests, the Unix-socket end-to-end test, Python syntax compilation, independent raw recomputation, source/binary provenance comparison, and PDF text extraction. A full SHA-256 verification matched all 170 files and 1,741,680,879 bytes listed in the 17-attempt provenance inventory. The accepted manifests all identify clean source revision `b304aec39f697abcbd62611ea9a2df6ac1abec0f`; their binary hash matches the retained release binary.

## Researcher tasks before external submission

1. Read the Rust server, generator, queue, timestamp, and cgroup paths and confirm that the implementation description matches personal understanding.
2. Reproduce the headline audit locally and inspect representative raw records and both thermal-invalid manifests.
3. Read the original Cambridge paper and Linux/Go/Rust primary documentation; verify every related-work statement and reference style.
4. Review every sentence of the paper, README, EPFL summary, and AI disclosure; rewrite any sentence that cannot be personally defended.
5. Decide how and where the 1.74 GB raw confirmatory dataset will be archived and cited before making a reproducibility claim to external reviewers.
6. Obtain any required human review, authorship guidance, and institutional/application disclosure advice. Do not imply EPFL affiliation or supervision.
7. Do not present descriptive medians as statistical significance or claim the scheduler mechanism is proven.

## Remaining experiments

Completing the original 140-valid-run design requires **125 additional valid experiments**: 124 unstarted scheduled cells plus the missing initial cell. Any thermal-gate amendment or scheduler-tracing mechanism study must be separately versioned and approved before collection. Phase 6 did not authorize or begin those experiments.
