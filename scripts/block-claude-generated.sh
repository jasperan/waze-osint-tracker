#!/usr/bin/env bash
set -euo pipefail

blocked=()

for path in "$@"; do
  case "$path" in
    .claude/*|.codex|.codex/*|.omc/*|.omx/*|.agents/*|.crush/*|.openhands/*|.pi/*|.serena/*|.playwright-mcp/*)
      blocked+=("$path")
      ;;
  esac
done

if ((${#blocked[@]} > 0)); then
  {
    echo "Refusing to commit agent-generated directories/artifacts:"
    printf '  - %s\n' "${blocked[@]}"
  } >&2
  exit 1
fi
