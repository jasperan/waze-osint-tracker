#!/usr/bin/env bash
set -euo pipefail

blocked=()

for path in "$@"; do
  base="$(basename "$path")"
  case "$base" in
    .env|.env.*)
      blocked+=("$path")
      ;;
  esac
done

if ((${#blocked[@]} > 0)); then
  {
    echo "Refusing to commit environment files:"
    printf '  - %s\n' "${blocked[@]}"
  } >&2
  exit 1
fi
