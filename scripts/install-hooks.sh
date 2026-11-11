#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
ln -sf ../../scripts/hooks/pre-commit .git/hooks/pre-commit && echo "hooks: pre-commit installed"
