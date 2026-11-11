/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

import { useEffect } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import type { TIssue } from "@plane/types";
import { extStore } from "../../store/ext.store";
import type { TExtDefinition, TExtValue } from "../../types";
import { ExtValueEditor } from "./ext-value-editor";

/** Route params as plain strings ("" when absent). */
function useExtRoute(projectIdOverride?: string | null) {
  const params = useParams();
  const workspaceSlug = params.workspaceSlug?.toString() ?? "";
  const projectId = projectIdOverride ?? params.projectId?.toString() ?? "";
  return { workspaceSlug, projectId };
}

function useColumnsReady(workspaceSlug: string, projectId: string, withValues: boolean) {
  useEffect(() => {
    if (!workspaceSlug || !projectId) return;
    void extStore.loadProject(workspaceSlug, projectId).then(() => {
      void extStore.loadColumns(workspaceSlug, projectId);
      if (withValues) void extStore.loadProjectValues(workspaceSlug, projectId);
    });
  }, [workspaceSlug, projectId, withValues]);
}

function columnsEnabled(workspaceSlug: string) {
  return extStore.isEnabled(workspaceSlug, "ext.properties") && extStore.isEnabled(workspaceSlug, "ext.columns");
}

/** Toggle chips for bound properties in the Display-properties menu (FR-EXT-021). */
export const ExtDisplayPropertyToggles = observer(function ExtDisplayPropertyToggles() {
  const { workspaceSlug, projectId } = useExtRoute();
  useColumnsReady(workspaceSlug, projectId, false);
  if (!projectId || !columnsEnabled(workspaceSlug)) return null;
  const visible = new Set(extStore.columns[projectId] ?? []);
  return (
    <>
      {extStore.boundDefinitions(workspaceSlug, projectId).map((d) => (
        <button
          key={d.id}
          type="button"
          className={`rounded-sm border px-2 py-0.5 text-11 transition-all ${
            visible.has(d.id) ? "border-accent-strong bg-accent-primary text-on-color" : "border-subtle hover:bg-layer-1"
          }`}
          onClick={() => void extStore.toggleColumn(workspaceSlug, projectId, d.id)}
        >
          {d.name}
        </button>
      ))}
    </>
  );
});

/** Extra <th> cells for visible ext columns in the Spreadsheet header. */
export const ExtSpreadsheetHeaderColumns = observer(function ExtSpreadsheetHeaderColumns() {
  const { workspaceSlug, projectId } = useExtRoute();
  useColumnsReady(workspaceSlug, projectId, true);
  if (!projectId || !columnsEnabled(workspaceSlug)) return null;
  return (
    <>
      {extStore.visibleColumns(workspaceSlug, projectId).map((d) => (
        <th
          key={d.id}
          className="h-11 min-w-36 items-center border border-t-0 border-b-0 border-subtle bg-layer-1 px-4 py-1 text-left text-13 font-medium"
        >
          {d.name}
        </th>
      ))}
    </>
  );
});

/** Extra <td> cells for one Spreadsheet row, editable inline for Members and Admins. */
export const ExtSpreadsheetCells = observer(function ExtSpreadsheetCells(props: { issue: TIssue; disabled: boolean }) {
  const { issue, disabled } = props;
  const { workspaceSlug, projectId } = useExtRoute(issue.project_id);
  if (!projectId || !columnsEnabled(workspaceSlug)) return null;
  return (
    <>
      {extStore.visibleColumns(workspaceSlug, projectId).map((d) => (
        <td key={d.id} className="h-11 min-w-36 border-r-[1px] border-b-[0.5px] border-subtle text-13">
          <ExtValueEditor
            workspaceSlug={workspaceSlug}
            projectId={projectId}
            issueId={issue.id}
            definition={d}
            disabled={disabled}
            variant="cell"
          />
        </td>
      ))}
    </>
  );
});

function displayValue(d: TExtDefinition, value: TExtValue): string {
  const ids = Array.isArray(value) ? value : value ? [value] : [];
  if (d.type === "dropdown") return ids.map((id) => d.options.find((o) => o.id === id)?.name ?? "").filter(Boolean).join(", ");
  if (d.type === "member") return ids.length ? `${ids.length} member${ids.length > 1 ? "s" : ""}` : "";
  if (d.type === "datetime" && typeof value === "string") return new Date(value).toLocaleString();
  return typeof value === "string" ? value : "";
}

/** Read-only chips for visible ext columns in the List layout. */
export const ExtListProperties = observer(function ExtListProperties(props: { issue: TIssue }) {
  const { issue } = props;
  const { workspaceSlug, projectId } = useExtRoute(issue.project_id);
  useColumnsReady(workspaceSlug, projectId, true);
  if (!projectId || !columnsEnabled(workspaceSlug)) return null;
  return (
    <>
      {extStore.visibleColumns(workspaceSlug, projectId).map((d) => {
        const text = displayValue(d, extStore.values[issue.id]?.[d.id] ?? null);
        if (!text) return null;
        return (
          <div
            key={d.id}
            title={d.name}
            className="flex h-5 items-center rounded-sm border-[0.5px] border-strong px-2.5 text-caption-sm-regular text-secondary"
          >
            {text}
          </div>
        );
      })}
    </>
  );
});
