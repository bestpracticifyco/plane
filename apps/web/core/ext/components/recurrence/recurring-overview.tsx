/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { ExtService } from "../../services/ext.service";
import type { TExtRecurrenceRule } from "../../types";

const service = new ExtService();
const TRIGGER: Record<TExtRecurrenceRule["trigger"], string> = {
  completed: "When completed",
  state: "At a state",
  schedule: "On schedule",
};

/** Every live series in the projects the viewer belongs to (Admins: all), like ClickUp's
 *  Recurring Task Overview. Pause, skip the next period, or stop from here. */
export function RecurringOverview({ workspaceSlug }: { workspaceSlug: string }) {
  const [rows, setRows] = useState<TExtRecurrenceRule[] | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  const load = useCallback(async () => {
    try {
      setRows(await service.listRecurrence(workspaceSlug));
    } catch {
      setUnavailable(true);
    }
  }, [workspaceSlug]);

  useEffect(() => {
    void load();
  }, [load]);

  const act = async (rule: TExtRecurrenceRule, action: "pause" | "resume" | "skip" | "stop") => {
    try {
      await service.recurrenceAction(workspaceSlug, rule.id, action);
      await load();
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Not changed", message: "You need to be a member of that project." });
    }
  };

  if (unavailable) return <div className="p-8 text-13 text-secondary">Recurring work items are not enabled here.</div>;
  if (!rows) return null;
  if (rows.length === 0)
    return (
      <div className="p-8 text-13 text-secondary">
        Nothing repeats yet. Open a work item and set <span className="text-primary">Repeats</span> in its properties.
      </div>
    );

  const cell = "px-3 py-2 text-left";
  return (
    <div className="h-full overflow-auto p-6">
      <table className="min-w-full border-collapse text-13">
        <thead className="bg-surface-2 text-secondary">
          <tr>
            <th className={cell}>Work item</th>
            <th className={cell}>Repeats</th>
            <th className={cell}>Creates next</th>
            <th className={cell}>Current due</th>
            <th className={cell}>Next due</th>
            <th className={cell}>Done so far</th>
            <th className={cell} />
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-subtle">
              <td className={cell}>
                {r.issue_id ? (
                  <Link
                    className="text-primary hover:underline"
                    href={`/${workspaceSlug}/browse/${r.project_identifier}-${r.issue_sequence_id}/`}
                  >
                    {r.project_identifier}-{r.issue_sequence_id} {r.issue_name}
                  </Link>
                ) : (
                  <span className="text-tertiary">(deleted)</span>
                )}
              </td>
              <td className={cell}>
                {r.paused && <span className="mr-1 text-warning-primary">Paused ·</span>}
                {r.summary}
              </td>
              <td className={cell}>
                {TRIGGER[r.trigger]}
                {r.trigger === "schedule" ? ` · ${r.run_time}` : ""}
              </td>
              <td className={cell}>{r.due ?? "—"}</td>
              <td className={cell}>{r.next_due ?? "—"}</td>
              <td className={cell}>
                {r.occurrences}
                {r.end_count ? ` of ${r.end_count}` : ""}
              </td>
              <td className={`${cell} whitespace-nowrap`}>
                <button
                  type="button"
                  className="mr-3 text-accent-primary"
                  onClick={() => void act(r, r.paused ? "resume" : "pause")}
                >
                  {r.paused ? "Resume" : "Pause"}
                </button>
                {r.next_due && (
                  <button type="button" className="mr-3 text-accent-primary" onClick={() => void act(r, "skip")}>
                    Skip next
                  </button>
                )}
                <button type="button" className="text-danger-primary" onClick={() => void act(r, "stop")}>
                  Stop
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
