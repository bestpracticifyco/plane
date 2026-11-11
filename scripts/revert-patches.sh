#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
# Restore every upstream file touched by a patch (listed in patches/paths.txt) to its committed state.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
[ -s patches/paths.txt ] || { echo "revert: no patched paths"; exit 0; }
grep -vE '^\s*(#|$)' patches/paths.txt | xargs git checkout --
echo "revert: restored $(grep -cvE '^\s*(#|$)' patches/paths.txt) path(s)"
