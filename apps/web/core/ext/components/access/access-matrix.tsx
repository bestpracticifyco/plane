/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { ExtService } from "../../services/ext.service";
import type { TExtAccessCell, TExtAccessMatrix, TExtRole } from "../../types";

const service = new ExtService();

const ROLE_NAMES: Record<TExtRole, string> = { 20: "Admin", 15: "Member", 5: "Guest" };
/** Plane CE: workspace Admin -> project Admin only; workspace Guest -> Guest only; Member -> any. */
const allowedRoles = (workspaceRole: TExtRole): TExtRole[] =>
  workspaceRole === 20 ? [20] : workspaceRole === 5 ? [5] : [20, 15, 5];

const cellKey = (memberId: string, projectId: string) => `${memberId}:${projectId}`;

const errorText = (e: unknown) => {
  const cells = (e as { cells?: string[] })?.cells;
  return cells?.join("\n") ?? (e as { error?: string })?.error ?? "Could not save the changes.";
};

/** People x projects grid with the project role in each cell (workspace Admin only). */
export function AccessMatrix({ workspaceSlug }: { workspaceSlug: string }) {
  const [data, setData] = useState<TExtAccessMatrix | null>(null);
  const [denied, setDenied] = useState(false);
  const [edits, setEdits] = useState<Record<string, TExtAccessCell>>({});
  const [filter, setFilter] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await service.getAccess(workspaceSlug));
    } catch {
      setDenied(true);
    }
  }, [workspaceSlug]);

  useEffect(() => {
    void load();
  }, [load]);

  const projects = useMemo(
    () => (data?.projects ?? []).filter((p) => showArchived || !p.is_archived),
    [data, showArchived]
  );
  const people = useMemo(() => {
    const q = filter.trim().toLowerCase();
    return (data?.people ?? []).filter(
      (p) => !q || p.email.toLowerCase().includes(q) || p.display_name.toLowerCase().includes(q)
    );
  }, [data, filter]);

  if (denied)
    return <div className="p-8 text-13 text-secondary">Only workspace admins can manage project access.</div>;
  if (!data) return null;

  const current = (memberId: string, projectId: string): TExtRole | null => {
    const edit = edits[cellKey(memberId, projectId)];
    return edit ? edit.role : (data.cells[memberId]?.[projectId] ?? null);
  };

  const change = (memberId: string, projectId: string, value: string) => {
    const role = value ? (Number(value) as TExtRole) : null;
    const key = cellKey(memberId, projectId);
    const original = data.cells[memberId]?.[projectId] ?? null;
    setEdits((prev) => {
      const next = { ...prev };
      if (role === original) delete next[key];
      else next[key] = { member_id: memberId, project_id: projectId, role };
      return next;
    });
  };

  const save = async () => {
    setSaving(true);
    try {
      const res = await service.setAccess(workspaceSlug, Object.values(edits));
      setData(res);
      setEdits({});
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Access updated", message: `${res.changed} change(s) saved.` });
    } catch (e) {
      setToast({ type: TOAST_TYPE.ERROR, title: "Nothing was changed", message: errorText(e) });
    } finally {
      setSaving(false);
    }
  };

  const pendingCount = Object.keys(edits).length;
  const publicProjects = projects.filter((p) => !p.is_private);

  return (
    <div className="flex h-full w-full flex-col gap-4 overflow-hidden p-6">
      <div className="flex flex-wrap items-center gap-3">
        <input
          className="h-8 w-64 rounded-md border border-subtle bg-surface-1 px-2 text-13 text-primary"
          placeholder="Filter people"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <label className="flex items-center gap-1.5 text-13 text-secondary">
          <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
          Show archived projects
        </label>
        <div className="ml-auto flex items-center gap-2">
          {pendingCount > 0 && (
            <Button variant="secondary" onClick={() => setEdits({})} disabled={saving}>
              Discard
            </Button>
          )}
          <Button variant="primary" onClick={() => void save()} disabled={!pendingCount || saving}>
            {saving ? "Saving…" : pendingCount ? `Save ${pendingCount} change(s)` : "Saved"}
          </Button>
        </div>
      </div>

      {publicProjects.length > 0 && (
        <div className="rounded-md border border-subtle bg-layer-1 px-3 py-2 text-13 text-secondary">
          Public projects are visible to every workspace member, whatever this grid says:{" "}
          <span className="text-primary">{publicProjects.map((p) => p.identifier).join(", ")}</span>. Make them
          private in Project settings → General.
        </div>
      )}

      <div className="flex-1 overflow-auto rounded-md border border-subtle">
        <table className="min-w-full border-collapse text-13">
          <thead className="sticky top-0 z-10 bg-surface-2">
            <tr>
              <th className="sticky left-0 z-20 bg-surface-2 px-3 py-2 text-left font-medium text-secondary">Person</th>
              {projects.map((p) => (
                <th key={p.id} className="px-2 py-2 text-left font-medium text-secondary" title={p.name}>
                  {p.identifier}
                  {!p.is_private && <span className="ml-1 text-11 text-tertiary">(public)</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {people.map((person) => (
              <tr key={person.id} className="border-t border-subtle">
                <td className="sticky left-0 z-10 bg-surface-1 px-3 py-1.5">
                  <div className="text-primary">{person.display_name || person.email}</div>
                  <div className="text-11 text-tertiary">
                    {person.email} · workspace {ROLE_NAMES[person.workspace_role]}
                  </div>
                </td>
                {projects.map((p) => {
                  const role = current(person.id, p.id);
                  const edited = cellKey(person.id, p.id) in edits;
                  return (
                    <td key={p.id} className={`px-1 py-1 ${edited ? "bg-layer-3" : ""}`}>
                      <select
                        aria-label={`${person.email} in ${p.identifier}`}
                        className="h-7 rounded-sm border border-subtle bg-surface-1 px-1 text-12 text-primary"
                        value={role ?? ""}
                        onChange={(e) => change(person.id, p.id, e.target.value)}
                      >
                        <option value="">—</option>
                        {allowedRoles(person.workspace_role).map((r) => (
                          <option key={r} value={r}>
                            {ROLE_NAMES[r]}
                          </option>
                        ))}
                      </select>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <PendingGrants workspaceSlug={workspaceSlug} data={data} onSaved={setData} />
    </div>
  );
}

/** "When this email joins the workspace, add them to these projects." */
function PendingGrants(props: {
  workspaceSlug: string;
  data: TExtAccessMatrix;
  onSaved: (d: TExtAccessMatrix) => void;
}) {
  const { workspaceSlug, data, onSaved } = props;
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<TExtRole>(15);
  const [selected, setSelected] = useState<string[]>([]);
  const byEmail = useMemo(() => {
    const out: Record<string, string[]> = {};
    for (const g of data.pending) (out[g.email] ??= []).push(g.project_id);
    return out;
  }, [data.pending]);
  const name = (id: string) => data.projects.find((p) => p.id === id)?.identifier ?? id;

  const submit = async (target: string, projectIds: string[]) => {
    try {
      onSaved(
        await service.setGrants(
          workspaceSlug,
          target,
          projectIds.map((project_id) => ({ project_id, role }))
        )
      );
      setEmail("");
      setSelected([]);
    } catch (e) {
      setToast({ type: TOAST_TYPE.ERROR, title: "Not saved", message: errorText(e) });
    }
  };

  return (
    <details className="rounded-md border border-subtle bg-surface-1 p-3 text-13">
      <summary className="cursor-pointer text-primary">
        Pre-assign projects for an invitee ({Object.keys(byEmail).length} pending)
      </summary>
      <p className="mt-2 text-secondary">
        Invite the person from Workspace settings → Members as usual. Choose their projects here; they are added
        when they accept. A Guest invitee is always added as project Guest.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          className="h-8 w-64 rounded-md border border-subtle bg-surface-1 px-2 text-13 text-primary"
          placeholder="name@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <select
          className="h-8 rounded-md border border-subtle bg-surface-1 px-2 text-13 text-primary"
          value={role}
          onChange={(e) => setRole(Number(e.target.value) as TExtRole)}
        >
          {([20, 15, 5] as TExtRole[]).map((r) => (
            <option key={r} value={r}>
              Project {ROLE_NAMES[r]}
            </option>
          ))}
        </select>
        <Button
          variant="primary"
          disabled={!email.includes("@") || selected.length === 0}
          onClick={() => void submit(email, selected)}
        >
          Save
        </Button>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {data.projects
          .filter((p) => !p.is_archived)
          .map((p) => (
            <label key={p.id} className="flex items-center gap-1 rounded-sm bg-layer-1 px-2 py-1 text-12">
              <input
                type="checkbox"
                checked={selected.includes(p.id)}
                onChange={(e) =>
                  setSelected((s) => (e.target.checked ? [...s, p.id] : s.filter((x) => x !== p.id)))
                }
              />
              {p.identifier}
            </label>
          ))}
      </div>
      {Object.entries(byEmail).map(([who, ids]) => (
        <div key={who} className="mt-2 flex items-center gap-2 text-secondary">
          <span className="text-primary">{who}</span> → {ids.map(name).join(", ")}
          <button type="button" className="text-danger-primary" onClick={() => void submit(who, [])}>
            Remove
          </button>
        </div>
      ))}
    </details>
  );
}
