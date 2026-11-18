/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { AccessMatrix } from "@/ext/components/access/access-matrix";
import { GovernorFrame } from "@/ext/components/embeds/governor-frame";
import { RecurringOverview } from "@/ext/components/recurrence/recurring-overview";

const TABS = [
  { key: "console", label: "Governor" },
  { key: "recurring", label: "Recurring" },
  { key: "access", label: "Project access" },
] as const;

export default function GovernorPage() {
  const { workspaceSlug } = useParams();
  const tab = useSearchParams().get("tab") ?? "console";
  if (!workspaceSlug) return null;
  const ws = workspaceSlug.toString();
  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      <nav className="flex shrink-0 gap-4 border-b border-subtle px-6 text-13">
        {TABS.map((t) => (
          <Link
            key={t.key}
            href={`/${ws}/governor${t.key === "console" ? "" : `?tab=${t.key}`}`}
            className={`border-b-2 py-2.5 ${tab === t.key ? "border-accent-strong text-primary" : "border-transparent text-secondary"}`}
          >
            {t.label}
          </Link>
        ))}
      </nav>
      <div className="min-h-0 flex-1">
        {tab === "access" && <AccessMatrix workspaceSlug={ws} />}
        {tab === "recurring" && <RecurringOverview workspaceSlug={ws} />}
        {tab !== "access" && tab !== "recurring" && <GovernorFrame workspaceSlug={ws} page="console" />}
      </div>
    </div>
  );
}
