/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

import { useParams } from "next/navigation";
import { GovernorFrame } from "@/ext/components/embeds/governor-frame";

export default function GovernorPage() {
  const { workspaceSlug } = useParams();
  if (!workspaceSlug) return null;
  return (
    <div className="h-full w-full overflow-hidden">
      <GovernorFrame workspaceSlug={workspaceSlug.toString()} page="console" />
    </div>
  );
}
