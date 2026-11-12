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
  Owner-approved ceiling (gate H6, re-opened and approved 11 Nov 2026): 5 patch files, 14 hunks,
  21 added lines; 0 deleted upstream lines except the one-line dependency pin replaced by patch 0005.
  Exceeding any figure re-opens the gate. Patch 0005 is dropped when upstream pins PyJWT >= 2.14.0.
- `scripts/check-fork-discipline.sh` (CI job `discipline`) enforces forbidden paths, migration
  location, SPDX headers and the no-licence-code rule, and prints the ledger below.
- A fork migration, once applied to production, is never edited again.

## Patch / upstream-file ledger
| # | Patch | Upstream file(s) | Hunks | +Lines | FR | Status |
|---|---|---|---|---|---|---|
| 0001 | sidebar ext panel | apps/web/core/components/issues/issue-detail/sidebar.tsx | 2 | 2 | FR-EXT-020/022 | approved |
| 0002 | layout columns | issue-layouts: display-properties, spreadsheet-header, issue-row, all-properties | 8 | 8 | FR-EXT-021 | approved |
| 0003 | source offer | apps/web/app/root.tsx | 2 | 2 | FR-EXT-070 | approved |
| 0004 | Governor nav | packages/constants/src/workspace.ts | 1 | 8 | FR-EXT-063 | approved |
| 0005 | PyJWT 2.14.0 (CVE-2026-102268) | apps/api/requirements/base.txt | 1 | 1 (replaces 1) | FR-EXT-112 | approved, temporary |
| seam | extended routes | apps/web/app/routes/extended.ts (seam, edited directly) | — | — | FR-EXT-060 | n/a |

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
