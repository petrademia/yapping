"""Reproducibility metadata for search and generated reports."""

import hashlib
import subprocess
from pathlib import Path


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision(path: str | Path = ".") -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(Path(path).resolve()), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def report_provenance(*, database: str | Path, scripts: str | Path,
                      max_nodes: int | None, max_depth: int | None, complete: bool,
                      revision_root: str | Path = ".") -> dict[str, object]:
    return {
        "database_sha256": sha256(database),
        "scripts_revision": git_revision(scripts),
        "yapping_revision": git_revision(revision_root),
        "search_limits": {"max_nodes": max_nodes, "max_depth": max_depth},
        "complete": complete,
    }
