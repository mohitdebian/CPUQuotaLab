# Public Release Provenance

## Scope

This repository is a sanitized, history-free public snapshot of CPUQuotaLab. The original private research repository, its Git history, checkpoints, internal tool references, ignored datasets, and raw experimental evidence were not copied or rewritten.

No experiment was executed to create this release snapshot. Scientific results and conclusions are unchanged.

## Snapshot mapping

| Item | Identifier |
|---|---|
| Original private publication-preparation checkpoint | `068170beb7f9d57c548a68606f7d9d12bbd113f7` |
| Original frozen confirmatory source revision | `b304aec39f697abcbd62611ea9a2df6ac1abec0f` |
| Frozen release binary SHA-256 | `560be7281c580a4fc0e4bc521269f75d50ac54f3940e300d68042637b889e095` |
| `Cargo.lock` SHA-256 | `fbca3fa74a1f84842dae29cd1e91b5e3ce31cdaf58133e8597462466e9f61cf9` |
| Frozen and exported `src/` Git tree object | `289f96be77ef3cff331d7226641e329314411b33` |
| Pinned Rust toolchain | `1.100.0` |

The benchmark implementation in `src/`, `Cargo.toml`, `Cargo.lock`, `rust-toolchain.toml`, and `tests/` is byte-for-byte unchanged between the frozen confirmatory revision and the publication-preparation snapshot. Analysis, reporting, and publication files were subsequently corrected and finalized without modifying the benchmark implementation or collected raw evidence.

The frozen binary is not committed because generated executables are platform-specific build artifacts. Its retained private copy was verified against the SHA-256 value above. The dependency-lock hash was recomputed from both the frozen revision and this public snapshot and matched exactly.

## Excluded material

The export deliberately excludes:

- the original `.git` directory, commit history, reflogs, and internal `refs/codex/` objects;
- raw pilot, smoke, and confirmatory request records;
- ignored build products, virtual environments, caches, and temporary render files;
- machine-local environment captures containing a hostname, UID, transient process scope, or private repository path;
- application-specific EPFL text, the interview/understanding guide, and the internal publication-readiness checklist; and
- any unpublished dataset archive.

The committed derived tables, figures, audit recomputation, experiment matrix, attempt indices, and raw-file checksum inventory remain available. Raw-data regeneration requires the separately reviewed dataset described in `DATASET_ARCHIVAL.md`.

## Public-history boundary

The first commit in this repository should be treated as the beginning of the public artifact history. Original private commit identifiers are recorded only to preserve the audit trail between the experiment manifests and this sanitized snapshot. They do not imply that the private history has been published.
