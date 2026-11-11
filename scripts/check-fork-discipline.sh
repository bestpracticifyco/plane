#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
# Fork discipline gate (FR-EXT-090/091/092/095). Compares HEAD with the upstream tag in UPSTREAM_TAG.
#  1. No forbidden upstream path is modified directly (changes go through patches/).
#  2. No fork migration under apps/api/plane/db/migrations/.
#  3. Every new overlay file carries the SPDX AGPL header.
#  4. No licence / plan / paid-tier vocabulary in overlay code.
# Prints the ledger of upstream files touched (seams) for FORK.md.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
BASE="${BASE:-$(cat UPSTREAM_TAG)}"
git rev-parse -q --verify "$BASE^{commit}" >/dev/null || git fetch -q https://github.com/makeplane/plane.git "refs/tags/$BASE:refs/tags/$BASE" --no-tags
fail=0
changed=$(git diff --name-only --diff-filter=ACMRD "$BASE"...HEAD)
added=$(git diff --name-only --diff-filter=A "$BASE"...HEAD)
FORBIDDEN='^(apps/web/core/components/|apps/web/app/routes/core\.ts$|apps/api/plane/db/|apps/api/plane/settings/(common|production)\.py$|apps/api/plane/urls\.py$|apps/api/plane/utils/instance_config_variables/core\.py$|apps/[a-z]+/Dockerfile\.|apps/proxy/Dockerfile\.ce$|LICENSE\.txt$|COPYRIGHT\.txt$)'
bad=$(printf '%s\n' "$changed" | grep -E "$FORBIDDEN" || true)
if [ -n "$bad" ]; then echo "FAIL forbidden upstream paths modified directly (use patches/):"; echo "$bad"; fail=1; fi
mig=$(printf '%s\n' "$added" | grep -E '^apps/api/plane/db/migrations/' || true)
if [ -n "$mig" ]; then echo "FAIL fork migration outside plane/ext/migrations:"; echo "$mig"; fail=1; fi
OVERLAY='^(apps/api/plane/ext/|apps/api/plane/settings/bp\.py$|apps/web/core/ext/|apps/web/app/ext/|scripts/|patches/)'
for f in $(printf '%s\n' "$added" | grep -E "$OVERLAY" | grep -E '\.(py|ts|tsx|sh|patch)$' || true); do
  head -5 "$f" | grep -q 'SPDX-License-Identifier: AGPL-3.0-only' || { echo "FAIL missing SPDX header: $f"; fail=1; }
done
lic=$(printf '%s\n' "$added" | grep -E "$OVERLAY" | grep -vE '^scripts/check-fork-discipline\.sh$' | xargs -r grep -lniE 'prime\.plane|paid plan|workspace_license|license_key|plan_tier' 2>/dev/null || true)
if [ -n "$lic" ]; then echo "FAIL licence/plan vocabulary in overlay:"; echo "$lic"; fail=1; fi
echo "--- ledger: upstream files modified (non-overlay) ---"
printf '%s\n' "$changed" | grep -vE "$OVERLAY" | grep -vE '^(\.github/|\.claude/|docs/|NOTICE$|FORK\.md$|CLAUDE\.md$|UPSTREAM_TAG$|\.trivyignore$)' || echo "(none)"
[ "$fail" -eq 0 ] && echo "fork discipline: OK" || exit 1
