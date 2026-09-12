#!/usr/bin/env python3
"""Read-only checks for the CUMCM repository layout and evidence boundaries."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PROTECTED_ROOTS = (
    "CUMCM2026Problems",
    "data",
    "src",
    "analysis",
    "outputs",
    "paper",
)

MOVED_ARCHIVES = {
    "deliverables/review/packages/C_microgrid_review_v1.zip":
        "1898c3c6656f5aedf40670e8dff78eebcf9123c47d1fdaf26265a9290ed27a01",
    "deliverables/review/packages/C_microgrid_review_v2.zip":
        "7a43ed1c5845a314d3f6254910a41b8aae349716210af18d1629f7c81129b29b",
    "deliverables/review/packages/deliverables_snapshot_manifest.json":
        "aedb536cc7cc22b17330f0810a4bec9ef982daa1a950cfd405ce6c3830c9dbb8",
}

OLD_ARCHIVE_PATHS = (
    "deliverables/C_microgrid_review_v1.zip",
    "deliverables/C_microgrid_review_v2.zip",
    "deliverables/file_manifest.json",
)

TOP_LEVEL_ALLOWED = {
    ".git",
    ".gitignore",
    ".workbuddy-ai",
    "CUMCM2026Problems",
    "PROJECT_MAP.md",
    "README.md",
    "analysis",
    "data",
    "deliverables",
    "docs",
    "outputs",
    "paper",
    "requirements-core.txt",
    "requirements-excel.txt",
    "requirements-figures.txt",
    "scripts",
    "src",
    "tests",
}

TOP_LEVEL_REGENERABLE_CACHE = {".venv", "tmp", ".pytest_cache", "__pycache__"}

REQUIRED_DIRECTORIES = PROTECTED_ROOTS + (
    "scripts",
    "tests",
    "docs",
    "deliverables",
    "deliverables/candidate_figures",
    "deliverables/final_submission",
    "deliverables/legacy_excel",
    "deliverables/review",
    "deliverables/review/packages",
)

REQUIRED_FILES = (
    "README.md",
    "PROJECT_MAP.md",
    ".gitignore",
    "docs/README.md",
    "docs/REPOSITORY_GOVERNANCE.md",
    "docs/current_tasks.md",
    "docs/data/TIME_SEMANTICS.md",
    "docs/model/README.md",
    "docs/experiments/README.md",
    "deliverables/README.md",
    "deliverables/candidate_figures/README.md",
    "deliverables/candidate_figures/v4_advanced/README.md",
    "deliverables/candidate_figures/v4_advanced/manifest.json",
    "deliverables/review/packages/README.md",
    "deliverables/final_submission/README.md",
    "deliverables/final_submission/excel/manifest.json",
    "scripts/README.md",
    "scripts/verify_repository_layout.py",
    "scripts/verify_time_semantics.py",
    "scripts/paper/build_advanced_figures.py",
    "scripts/paper/verify_advanced_figures.py",
    "paper/latex/main.tex",
    "paper/pdf/C_microgrid.pdf",
)

PUBLIC_DOCS = (
    "README.md",
    "PROJECT_MAP.md",
    "docs/README.md",
    "deliverables/README.md",
    "scripts/README.md",
    "deliverables/candidate_figures/README.md",
)

CACHE_PARTS = {".venv", "tmp", ".pytest_cache", "__pycache__"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tracked_paths() -> list[str]:
    output = subprocess.check_output(
        ["git", "ls-files"], cwd=ROOT, text=True, stderr=subprocess.STDOUT
    )
    return [line for line in output.splitlines() if line]


def main() -> int:
    errors: list[str] = []

    actual_top_level = {path.name for path in ROOT.iterdir()}
    unexpected_top_level = sorted(
        actual_top_level - TOP_LEVEL_ALLOWED - TOP_LEVEL_REGENERABLE_CACHE
    )
    if unexpected_top_level:
        errors.append(
            "unexpected top-level entries: " + ", ".join(unexpected_top_level)
        )

    for relative in REQUIRED_DIRECTORIES:
        if not (ROOT / relative).is_dir():
            errors.append(f"missing required directory: {relative}")

    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"missing required file: {relative}")

    for relative, expected_hash in MOVED_ARCHIVES.items():
        path = ROOT / relative
        if not path.is_file():
            errors.append(f"missing moved historical package: {relative}")
        elif sha256(path) != expected_hash:
            errors.append(f"SHA-256 mismatch: {relative}")

    for relative in OLD_ARCHIVE_PATHS:
        if (ROOT / relative).exists():
            errors.append(f"old historical package path still exists: {relative}")

    candidate_root = ROOT / "deliverables/candidate_figures"
    for version in ("v1", "v2", "v3_3d", "v4_advanced"):
        version_dir = candidate_root / version
        if not (version_dir / "README.md").is_file() and not any(
            version_dir.glob("*manifest.json")
        ):
            errors.append(f"candidate version lacks README or manifest: {version}")

    v4_readme = (candidate_root / "v4_advanced/README.md").read_text(
        encoding="utf-8"
    ).lower()
    if "candidate" not in v4_readme and "候选" not in v4_readme:
        errors.append("v4_advanced is not marked as a candidate")
    if "paper/" not in v4_readme and "paper" not in v4_readme:
        errors.append("v4_advanced README does not state its paper boundary")

    paper_dir = ROOT / "paper"
    paper_v4_paths = [
        path for path in paper_dir.rglob("*") if "v4_advanced" in path.parts
    ]
    if paper_v4_paths:
        errors.append("v4_advanced appears inside paper/")

    for relative in PUBLIC_DOCS:
        text = (ROOT / relative).read_text(encoding="utf-8")
        for old_path in OLD_ARCHIVE_PATHS:
            if old_path in text:
                errors.append(f"old package link remains in {relative}: {old_path}")

    try:
        paths = tracked_paths()
    except subprocess.CalledProcessError as exc:
        errors.append(f"cannot inspect tracked paths: git ls-files exited {exc.returncode}")
        paths = []

    for relative in paths:
        parts = Path(relative).parts
        if CACHE_PARTS.intersection(parts):
            errors.append(f"tracked cache/temp path: {relative}")
        if relative.startswith("analysis/") and relative.endswith(".jsonl"):
            errors.append(f"tracked analysis JSONL evidence: {relative}")
        if relative.startswith("outputs/") and relative.endswith(".ndjson"):
            errors.append(f"tracked outputs NDJSON evidence: {relative}")

    if errors:
        print("repository layout: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("repository layout: PASS")
    print(f"checked {len(REQUIRED_DIRECTORIES)} directories and {len(REQUIRED_FILES)} files")
    print("protected roots, candidate boundary, archive relocation and tracked-cache rules: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
