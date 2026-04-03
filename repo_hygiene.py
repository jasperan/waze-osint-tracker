"""Git/repository hygiene helpers for generated artifacts."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ALLOWED_MARKDOWN_BASENAMES = {
    "README.md",
    "CHANGELOG.md",
    "LICENSE.md",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    "CLAUDE.md",
    "AGENTS.md",
}

SUSPICIOUS_BASENAME_PATTERNS = [
    re.compile(r"^IMPLEMENTATION(?:[-_ ].*)?\.md$", re.IGNORECASE),
    re.compile(r"^TESTING_REPORT(?:[-_ ].*)?\.md$", re.IGNORECASE),
    re.compile(r"^AGENT_HARNESS_ANNEX(?:[-_ ].*)?\.md$", re.IGNORECASE),
    re.compile(r"^SKILLS_EXECUTION_SUMMARY(?:[-_ ].*)?\.md$", re.IGNORECASE),
    re.compile(r"^PRD(?:[-_ ].*)?\.md$", re.IGNORECASE),
    re.compile(r"^TEST[-_ ]SPEC(?:[-_ ].*)?\.md$", re.IGNORECASE),
    re.compile(r"^AUTOPILOT[-_ ].*\.md$", re.IGNORECASE),
    re.compile(r"^RALPLAN[-_ ].*\.md$", re.IGNORECASE),
]

SUSPICIOUS_CONTENT_MARKERS = (
    "# Task Statement",
    "# Desired Outcome",
    "# Known Facts / Evidence",
    "# Likely Codebase Touchpoints",
    "# RALPLAN Implementation Plan",
    "# Autopilot Spec",
    "## RALPLAN-DR Summary",
    "Codex",
    "oh-my-codex",
)


def is_suspicious_generated_markdown_path(path: str | Path) -> bool:
    """Return True when *path* looks like a generated markdown artifact."""
    file_path = Path(path)
    if file_path.suffix.lower() != ".md":
        return False
    if file_path.name in ALLOWED_MARKDOWN_BASENAMES:
        return False
    return any(pattern.match(file_path.name) for pattern in SUSPICIOUS_BASENAME_PATTERNS)


def markdown_has_generated_markers(text: str) -> bool:
    """Heuristic content-based detection for generated planning/report artifacts."""
    hits = sum(1 for marker in SUSPICIOUS_CONTENT_MARKERS if marker in text)
    return hits >= 2


def inspect_markdown_path(path: str | Path) -> str | None:
    """Return a reason when the markdown file appears generated, else ``None``."""
    file_path = Path(path)
    if file_path.suffix.lower() != ".md":
        return None
    if is_suspicious_generated_markdown_path(file_path):
        return "suspicious generated markdown filename"
    try:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None
    if markdown_has_generated_markers(text):
        return "generated-planning/report content markers"
    return None


def scan_paths_for_generated_markdown(paths: Sequence[str | Path]) -> list[dict[str, str]]:
    """Inspect a list of paths and return any suspicious markdown findings."""
    findings: list[dict[str, str]] = []
    for path in paths:
        reason = inspect_markdown_path(path)
        if reason:
            findings.append({"path": str(path), "reason": reason})
    return findings


def _run_git(repo_root: str | Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def audit_git_generated_markdown(repo_root: str | Path) -> dict[str, Any]:
    """Audit tracked files and history for suspicious generated markdown paths."""
    root = Path(repo_root)
    git_dir = root / ".git"
    if not git_dir.exists():
        return {"available": False, "tracked": [], "history": []}

    try:
        tracked_paths = [line for line in _run_git(root, "ls-files").splitlines() if line.strip()]
        tracked_candidates = [root / path for path in tracked_paths]
        tracked_findings = []
        for finding in scan_paths_for_generated_markdown(tracked_candidates):
            relative_path = Path(finding["path"]).resolve().relative_to(root.resolve())
            tracked_findings.append(str(relative_path))

        history_output = _run_git(root, "log", "--all", "--name-only", "--pretty=format:")
        history_paths = [line for line in history_output.splitlines() if line.strip()]
        history_findings = sorted(
            {path for path in history_paths if is_suspicious_generated_markdown_path(path)}
        )
    except (subprocess.CalledProcessError, ValueError):
        return {"available": False, "tracked": [], "history": []}

    return {
        "available": True,
        "tracked": tracked_findings,
        "history": history_findings,
        "clean": not tracked_findings and not history_findings,
    }
