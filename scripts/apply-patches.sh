#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
# Apply patches/NNNN-*.patch to the working tree in order. `--check` only verifies they apply.
# A patch that does not apply cleanly fails loudly (non-zero exit) and names the file.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
MODE="${1:-apply}"
shopt -s nullglob
n=0
for p in patches/[0-9][0-9][0-9][0-9]-*.patch; do
  if [ "$MODE" = "--check" ]; then
    git apply --check "$p" || { echo "patches: FAILED to apply $p" >&2; exit 1; }
  else
    git apply "$p" || { echo "patches: FAILED to apply $p" >&2; exit 1; }
  fi
  n=$((n + 1))
done
echo "patches: $n $([ "$MODE" = "--check" ] && echo checked || echo applied)"
