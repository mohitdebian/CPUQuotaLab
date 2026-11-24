# Phase 5 Initial Confirmatory Collection Report

## Collection outcome

Collection ran from 24 November 2026 19:51:50 to 20:20:56 IST. The frozen initial stage contained 16 cells. Fifteen cells produced valid data. One cell—block 2, mixed moderate, 10 ms, two workers—had two attempts rejected because immutable manifest start snapshots recorded package temperatures of 63°C and 64°C, above the 60°C gate. The finite retry policy then stopped further collection. Both attempts remain preserved; neither contributes to results.

| Item | Result |
|---|---:|
| Valid cells | 15/16 |
| Invalid attempts | 2 |
| Total attempt directories | 17 |
| Valid-run offered requests | 2,340,000 |
| Valid-run completed requests | 2,314,313 |
| Valid-run dropped requests | 25,687 |
| Valid-run incomplete/transport-failed requests | 0/0 |
| All-attempt measurement requests | 2,556,000 |
| Dataset bytes | 1,741,680,879 |

## Configuration

All attempts used the predeclared mixed 90/10 workload, 76,000/1,140,000 short/long iterations, 1.5 CPUs, 10 or 100 ms periods, one or two native workers, FIFO 550, 1,200/s moderate or 2,200/s stress load, 5-second warm-up, 90-second measurement, and at most 10 seconds drain. Server CPUs were 0–7; generator CPUs were 8–11, with writer CPU 9 and reader CPU 10.

The complete 140-cell schedule was generated before confirmatory outcomes using master seed `2027112401`. The initial cells are blocks 1–2 and remain usable in the eventual full design. No eight-worker, uniform, anchor, or remaining-block experiment was collected.

## Validity and failures

Every valid attempt passed exact accounting, binary hash, cgroup quota/burst, generator timing/backpressure, AC/profile, placement, and moderate-run long-class sample-size gates. No validity decision used latency, throughput, throttling, drops, or hypothesis direction.

The two invalid attempts were scientifically neutral environmental failures. The pre-run sensor reads were below 60°C, but the later manifest start snapshots were 63°C and 64°C. This race suggests that a future continuation should require a short below-threshold stability interval before launch, but changing preflight behavior requires a protocol amendment. No third attempt was made.

## Provenance

- Activation checkpoint: `b304aec39f697abcbd62611ea9a2df6ac1abec0f`.
- Preliminary analysis checkpoint: `9623adca150ca48bcf81a5cae41a90c550fcae1d`.
- Binary SHA-256: `560be7281c580a4fc0e4bc521269f75d50ac54f3940e300d68042637b889e095`.
- Matrix SHA-256 at activation: `8e3790e2f7725a97e32bf51ea8c632f22be596aa1d0f56e43d0c4bed0cfa03a9`.
- Raw attempt directories: `results/confirmatory/attempts/` (excluded from ordinary Git history).
- Per-file sizes and SHA-256 hashes: `dataset_provenance.json`.
- Cell/attempt status: `run_index.csv`, `invalid_attempts.csv`, and `experiment_progress.json`.

Pilot directories are separate and were not read by the confirmatory analysis script.
