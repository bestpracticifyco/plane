/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Repeat } from "lucide-react";
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { extStore } from "../../store/ext.store";
import { RecurrenceEditor } from "./recurrence-editor";

type Props = { workspaceSlug: string; projectId: string; issueId: string; disabled: boolean };

/** "Repeats" row in the work-item sidebar and peek view (rendered by ExtPropertiesPanel). */
export const RecurrenceRow = observer(function RecurrenceRow(props: Props) {
  const { workspaceSlug, projectId, issueId, disabled } = props;
  const [open, setOpen] = useState(false);
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  const issue = getIssueById(issueId);
  const enabled = extStore.isEnabled(workspaceSlug, "ext.recurrence");

  useEffect(() => {
    if (enabled) void extStore.loadRecurrence(workspaceSlug, projectId, issueId);
  }, [enabled, workspaceSlug, projectId, issueId]);

  if (!enabled) return null;
  const rule = extStore.recurrence[issueId];
  const label = rule ? `${rule.paused ? "Paused · " : ""}${rule.summary}` : "Does not repeat";

  return (
    <SidebarPropertyListItem icon={Repeat} label="Repeats">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(true)}
        className="flex h-7.5 w-full items-center justify-start rounded-sm px-2 text-left text-13 hover:bg-layer-1 disabled:cursor-not-allowed"
        title={rule?.next_due ? `Next due ${rule.next_due}` : undefined}
      >
        <span className={rule ? "text-primary" : "text-placeholder"}>{label}</span>
      </button>
      {open && (
        <RecurrenceEditor
          workspaceSlug={workspaceSlug}
          projectId={projectId}
          issueId={issueId}
          dueDate={issue?.target_date ?? null}
          onClose={() => setOpen(false)}
        />
      )}
    </SidebarPropertyListItem>
  );
});
