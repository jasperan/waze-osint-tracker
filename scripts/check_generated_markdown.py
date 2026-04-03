#!/usr/bin/env python3
"""Block suspicious generated markdown artifacts from commits."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from repo_hygiene import scan_paths_for_generated_markdown


def main(argv: list[str]) -> int:
    findings = scan_paths_for_generated_markdown(argv)
    if not findings:
        return 0

    print("Blocked suspicious generated markdown artifacts:", file=sys.stderr)
    for finding in findings:
        print(f"- {finding['path']}: {finding['reason']}", file=sys.stderr)
    print(
        (
            "Commit the substantive code/docs changes instead, and keep "
            "agent-generated planning/report files local."
        ),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
