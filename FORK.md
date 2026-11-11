# FORK.md — how this fork is maintained

## Branch model
- `main` — release line: upstream tag + our overlay. Release tags `vX.Y.Z-bp.N`.
- `bp/vX.Y.Z` — work branch for upstream tag `vX.Y.Z`. Changes land on `main` by pull request.
- `upstream` remote = makeplane/plane (push disabled locally). We track **release tags only**,
  never `preview`, and never use GitHub's "Sync fork" button (it merges `preview`).

## Fork discipline
- Overlay code lives only in: `apps/api/plane/ext/`, `apps/api/plane/settings/bp.py`,
  `apps/web/core/ext/`, `apps/web/app/ext/`, and upstream's `extended.*` seam files.
- Any other upstream file changes only through `patches/NNNN-*.patch`, applied at build time.
  Owner-approved ceiling (gate H6, 11 Nov 2026): 4 files, 9 hunks, 90 added lines, 0 deleted lines.
- `scripts/check-fork-discipline.sh` (CI job `discipline`) enforces forbidden paths, migration
  location, SPDX headers and the no-licence-code rule, and prints the ledger below.
- A fork migration, once applied to production, is never edited again.

## Patch / upstream-file ledger
| # | Patch | Upstream file(s) | Hunks | +Lines | FR | Status |
|---|---|---|---|---|---|---|
| — | (none yet) | | | | | |

## Images and registry
- CI (`release.yml`) builds six generic images to `ghcr.io/bestpracticifyco/plane-*`
  (no hostname or secret baked in), Trivy-scans, signs with Cosign keyless, and publishes
  a digest manifest. Production pins images **by digest**.
- GHCR packages are **private**. The VPS pulls with one read-only fine-grained token.
- Packages do not move automatically if this repository is transferred: re-link each package
  to the new repository in its package settings after any transfer.

## Repository settings (record changes here)
- Organisation `bestpracticifyco`, default branch `main`, default `GITHUB_TOKEN` read-only.
- Required: rulesets on `main` and `bp/*` (PR + `ci` checks, including admins); 2FA required
  for members; secret scanning + push protection; actions allowed only when pinned by SHA.

## Rebase log
| Date | From | To | Conflicts | Patch retargets | By |
|---|---|---|---|---|---|
| 2026-11-11 | — | v1.4.3 | fork created | — | bestdev1000X |
