/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { layout, route } from "@react-router/dev/routes";
import type { RouteConfigEntry } from "@react-router/dev/routes";

// Best Practicify fork (see FORK.md): embedded Governor pages. Layout file keys match routes/core.ts
// character for character so upstream's mergeRoutes deep-merges them into the workspace layout.
export const extendedRoutes: RouteConfigEntry[] = [
  layout("./(all)/layout.tsx", [
    layout("./(all)/[workspaceSlug]/layout.tsx", [
      layout("./(all)/[workspaceSlug]/(projects)/layout.tsx", [
        route(":workspaceSlug/governor", "./ext/governor/page.tsx"),
      ]),
    ]),
  ]),
];
