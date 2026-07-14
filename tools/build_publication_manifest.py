"""Build the hash-bound public tracked-file inventory without legal inference."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SELF_PATH = "docs/publication-manifest.json"
SELF_PLACEHOLDER = "0" * 64


def classification(path: str) -> tuple[str, bool, str]:
    if path.startswith("src/") or path.startswith("tools/"):
        return "source-code", False, "implementation or deterministic publication tooling"
    if path.startswith("tests/gold/"):
        return "synthetic-gold", False, "compact project-authored controlled annotation"
    if path.startswith("tests/"):
        return "test-code", False, "quality, contract, regression, or security test"
    if path.startswith("schemas/"):
        return "schema", False, "versioned structured-record contract"
    if path.startswith("configs/"):
        return "configuration", False, "reviewed versioned configuration"
    if path.startswith(".github/workflows/"):
        return "ci-configuration", False, "least-privilege public quality workflow"
    if path.startswith(".github/"):
        return "repository-governance", False, "public collaboration configuration"
    if path.startswith("docs/releases/"):
        return "sanitized-release-record", True, "hash-bound controlled-baseline record"
    if path == SELF_PATH:
        return "publication-manifest", True, "machine-readable disclosure inventory"
    if path.startswith("docs/") or path.endswith(".md"):
        return "documentation", False, "architecture, governance, research, or project contract"
    if path.endswith(".pdf"):
        return "research-document", False, "project concept paper approved for public inspection"
    if path == "uv.lock":
        return "dependency-lock", True, "reproducible Python dependency resolution"
    if path in {"pyproject.toml", "CITATION.cff"}:
        return "project-metadata", False, "package or citation metadata"
    return "repository-control", False, "public repository behavior or policy"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(root: Path, paths: list[str]) -> dict[str, object]:
    entries = []
    for relative in sorted(set(paths)):
        file_path = root / relative
        category, generated, reason = classification(relative)
        entries.append(
            {
                "path": relative,
                "sha256": SELF_PLACEHOLDER if relative == SELF_PATH else sha256(file_path),
                "size_bytes": 0 if relative == SELF_PATH else file_path.stat().st_size,
                "classification": category,
                "generated": generated,
                "reason_for_inclusion": reason,
                "redistribution_basis": "explicit operator authorization for public disclosure",
                "applicable_license": "unresolved; no project reuse license selected",
            }
        )
    manifest: dict[str, object] = {
        "schema_version": "1.0.0",
        "scope": "files tracked by the m2b-controlled-v1 public release",
        "self_hash_rule": (
            "The manifest entry uses SHA-256 of canonical JSON with its own sha256 value set to "
            "64 zeroes; the detached actual file SHA-256 is reported in release verification."
        ),
        "files": entries,
    }
    self_entry = next(entry for entry in entries if entry["path"] == SELF_PATH)
    self_entry["size_bytes"] = 0
    for _ in range(8):
        self_entry["sha256"] = SELF_PLACEHOLDER
        canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        normalized = hashlib.sha256(canonical.encode()).hexdigest()
        self_entry["sha256"] = normalized
        rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        size = len(rendered.encode())
        if self_entry["size_bytes"] == size:
            break
        self_entry["size_bytes"] = size
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--paths-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = [line for line in args.paths_file.read_text(encoding="utf-8").splitlines() if line]
    value = build(args.root, paths)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
