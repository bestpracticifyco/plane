# CLAUDE.md — bestpracticifyco/plane (public AGPL fork of Plane Community Edition)

Read `AGENTS.md` (upstream conventions), `FORK.md` (branching, ledger) and `NOTICE` first.

## What this repository is
A narrow fork of makeplane/plane at the tag in `UPSTREAM_TAG`. We add `plane_ext`
(workspace-scoped custom properties, feature flags, embedded Governor pages, source-offer link)
through upstream's `extended.*` seams, one satellite Django app at `apps/api/plane/ext/`
(Django label `plane_ext`), frontend code under `apps/web/core/ext/` and `apps/web/app/ext/`,
and a counted set of build-time patches under `patches/`.
Never add licence, plan, Prime or paid-tier code. Never consult Plane Commercial Edition.

## Hard rules — refuse the task and say why if a request breaks one
1. Do not edit directly: `apps/web/core/components/**`, `apps/web/app/routes/core.ts`,
   `apps/api/plane/db/**`, `apps/api/plane/settings/common.py`, `apps/api/plane/settings/production.py`,
   `apps/api/plane/urls.py`, `apps/api/plane/utils/instance_config_variables/core.py`,
   any upstream `Dockerfile.*`, `LICENSE.txt`, `COPYRIGHT.txt`.
   The only way to change an upstream file outside a seam is a patch in `patches/`.
   Patch ceiling (owner gate H6, re-approved): 4 patch files, 13 hunks, 20 added lines, 0 deleted upstream lines.
2. Seams you may edit: `apps/web/app/routes/extended.ts`, `apps/web/app/routes/redirects/extended/index.ts`,
   `apps/admin/providers/extended.tsx`, `apps/web/core/hooks/oauth/extended.tsx`,
   `apps/api/plane/utils/instance_config_variables/extended.py`, `apps/web/core/store/pages/extended-base-page.ts`,
   `apps/admin/components/common/header/extended.ts`.
3. Backend code only under `apps/api/plane/ext/`; migrations only under `apps/api/plane/ext/migrations/`.
   `apps/api/plane/settings/bp.py` selects the overlay via `DJANGO_SETTINGS_MODULE`.
4. Frontend code only under `apps/web/core/ext/` and `apps/web/app/ext/`. The ext MobX store is a
   module-level singleton (apps/web has no global provider seam) so patched core components can read it.
5. Every new file starts with:
   `SPDX-License-Identifier: AGPL-3.0-only` and
   `Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).`
6. No secrets, tokens, credentialed URLs or webhook URLs in any file. Use env var names.
7. Never `git push --force`, never rebase `main`, never `docker compose down -v`.
8. Do not invent upstream APIs. Grep first; if a hook/store/component does not exist, say so.

## Roles (Community Edition reality)
Plane CE roles are Admin=20, Member=15, Guest=5 (`plane/app/permissions/base.py`). There is no
Commenter role. Guests cannot create work items (except intake), cannot edit others' items, cannot
be assignees. Reuse `plane.app.permissions.*`; do not re-implement role checks.

## Commands
- Install: `pnpm install --frozen-lockfile`        Lint/format: `pnpm check` / `pnpm fix` (oxlint + oxfmt)
- Types: `pnpm turbo run check:types --filter=web`
- API tests: `docker compose -f docker-compose-test.yml up --build --abort-on-container-exit --exit-code-from api-tests`
- Patches: `scripts/apply-patches.sh [--check]`, `scripts/revert-patches.sh`
- Discipline gate: `scripts/check-fork-discipline.sh`

## Definition of done
Discipline gate green; patches apply; `pnpm check` and type checks pass; `plane_ext` tests pass;
`git diff --name-only $(cat UPSTREAM_TAG)...HEAD` shows no forbidden path.
