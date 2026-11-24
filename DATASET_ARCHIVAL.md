# Dataset Archival and Citation

## Current status

The confirmatory raw data consist of 17 immutable attempt directories: 15 valid runs and two retained thermal-invalid attempts. `dataset_provenance.json` inventories 170 files totaling 1,741,680,879 bytes using SHA-256. The raw data are excluded from Git and have not been uploaded or assigned a DOI.

Do not upload `results/confirmatory/attempts/` directly. Original manifests contain local absolute paths. Preserve the originals unchanged and create a separate sanitized export.

## Prepare an archive after researcher approval

From the repository root:

```bash
python3 scripts/prepare_dataset_archive.py \
  --source results/confirmatory/attempts \
  --output /absolute/path/cpuquotalab-confirmatory-v1

tar --zstd -cf cpuquotalab-confirmatory-v1.tar.zst \
  -C /absolute/path cpuquotalab-confirmatory-v1

sha256sum cpuquotalab-confirmatory-v1.tar.zst \
  > cpuquotalab-confirmatory-v1.tar.zst.sha256
```

The exporter refuses to overwrite its destination, copies non-JSON evidence byte-for-byte, replaces local repository/home prefixes inside JSON strings with placeholders, and writes `ARCHIVE_PROVENANCE.json` plus `SANITIZATION.json`. Review both files and search the export before uploading:

```bash
rg -n '/home/|/Users/|BEGIN .*PRIVATE KEY|api[_-]?key|access[_-]?token' \
  /absolute/path/cpuquotalab-confirmatory-v1
sha256sum -c cpuquotalab-confirmatory-v1.tar.zst.sha256
```

## Deposit metadata

Use a general research-data repository that provides immutable versions and checksums, such as Zenodo or OSF, only after explicit approval. Suggested metadata:

- **Title:** CPUQuotaLab Preliminary Confirmatory Dataset, Version 1
- **Creator:** Mohit Singh
- **Resource type:** Dataset
- **Publication date:** the actual upload date
- **Version:** 1.0.0
- **License:** MIT, matching the repository; change only after personal review
- **Description:** raw and derived evidence for 15 valid confirmatory runs and two retained thermal-invalid attempts from an independent, preliminary, non-peer-reviewed study
- **Related identifier:** the immutable Git commit URL for the public artifact
- **Keywords:** Linux, cgroup v2, CPU quota, thread pool, tail latency

Do not enter a DOI in `CITATION.cff`, the paper, or README until the repository actually assigns one. After deposit, add the dataset DOI and exact archive SHA-256 in a new commit and cite that immutable record from the paper's artifact section.

## Recommended dataset citation before a DOI exists

Mohit Singh. *CPUQuotaLab Preliminary Confirmatory Dataset, Version 1*. Independent preliminary research dataset, 2026. Unpublished local archive; no DOI assigned.

This temporary wording must be replaced by the repository-generated citation after an approved deposit.
