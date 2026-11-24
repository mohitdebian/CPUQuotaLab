#!/usr/bin/env python3
"""Create a privacy-sanitized copy of immutable confirmatory evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any


ROOT = Path(__file__).resolve().parent.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sanitize(value: Any, replacements: dict[str, str]) -> tuple[Any, int]:
    if isinstance(value, str):
        count = 0
        for source, target in replacements.items():
            occurrences = value.count(source)
            value = value.replace(source, target)
            count += occurrences
        return value, count
    if isinstance(value, list):
        output = []
        count = 0
        for item in value:
            clean, replacements_made = sanitize(item, replacements)
            output.append(clean)
            count += replacements_made
        return output, count
    if isinstance(value, dict):
        output = {}
        count = 0
        for key, item in value.items():
            clean, replacements_made = sanitize(item, replacements)
            output[key] = clean
            count += replacements_made
        return output, count
    return value, 0


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    source = args.source.resolve()
    output = args.output.resolve()
    if not source.is_dir():
        raise SystemExit(f"source is not a directory: {source}")
    if output.exists():
        raise SystemExit(f"refusing to overwrite existing output: {output}")

    replacements = {
        str(ROOT): "${REPOSITORY_ROOT}",
        str(Path.home()): "${USER_HOME}",
    }
    output.mkdir(parents=True)
    sanitization = []
    provenance = []

    for path in sorted(source.rglob("*")):
        if path.is_symlink():
            raise SystemExit(f"refusing symbolic link in evidence: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        replacement_count = 0
        if path.suffix == ".json":
            try:
                value = json.loads(path.read_text())
            except (UnicodeDecodeError, json.JSONDecodeError):
                shutil.copy2(path, target)
            else:
                clean, replacement_count = sanitize(value, replacements)
                target.write_text(json.dumps(clean, indent=2) + "\n")
        else:
            shutil.copy2(path, target)
        if replacement_count:
            sanitization.append(
                {"path": str(relative), "string_replacements": replacement_count}
            )
        provenance.append(
            {
                "path": str(relative),
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
        )

    (output / "ARCHIVE_PROVENANCE.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "hash": "SHA-256",
                "file_count": len(provenance),
                "files": provenance,
            },
            indent=2,
        )
        + "\n"
    )
    (output / "SANITIZATION.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "source_was_modified": False,
                "replacement_categories": ["repository_root", "user_home"],
                "changed_json_files": sanitization,
            },
            indent=2,
        )
        + "\n"
    )
    shutil.copy2(ROOT / "dataset_provenance.json", output / "ORIGINAL_PROVENANCE.json")
    print(f"exported {len(provenance)} evidence files to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
