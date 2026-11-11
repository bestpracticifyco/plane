/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

import { action, makeObservable, observable, runInAction } from "mobx";
import { ExtService } from "../services/ext.service";
import type { TExtBinding, TExtDefinition, TExtFlags, TExtValue } from "../types";

/**
 * Module-level MobX store for plane_ext. apps/web has no global provider seam, so patched core
 * components and extended routes share this singleton instead of a React context.
 * Every load is de-duplicated per key and failures degrade to "nothing to render".
 */
export class ExtStore {
  flags: Record<string, TExtFlags> = {};
  definitions: Record<string, TExtDefinition[]> = {};
  bindings: Record<string, TExtBinding[]> = {};
  values: Record<string, Record<string, TExtValue>> = {};
  columns: Record<string, string[]> = {};
  errors: Record<string, string> = {};

  private service = new ExtService();
  private inflight = new Map<string, Promise<unknown>>();

  constructor() {
    makeObservable(this, {
      flags: observable,
      definitions: observable,
      bindings: observable,
      values: observable,
      columns: observable,
      errors: observable,
      setValue: action,
    });
  }

  private once<T>(key: string, fn: () => Promise<T>, force = false): Promise<T> {
    if (!force && this.inflight.has(key)) return this.inflight.get(key) as Promise<T>;
    const p = fn().finally(() => setTimeout(() => this.inflight.delete(key), 30_000));
    this.inflight.set(key, p);
    return p;
  }

  isEnabled(ws: string, flag: string): boolean {
    return this.flags[ws]?.[flag] ?? false;
  }

  /** Flags + definitions for a workspace and bindings for a project. */
  loadProject(ws: string, projectId: string, force = false) {
    return Promise.all([
      this.once(`flags:${ws}`, async () => {
        const f = await this.service.getFlags(ws);
        runInAction(() => (this.flags[ws] = f));
      }, force),
      this.once(`defs:${ws}`, async () => {
        const d = await this.service.getDefinitions(ws);
        runInAction(() => (this.definitions[ws] = d));
      }, force),
      this.once(`bind:${projectId}`, async () => {
        const b = await this.service.getBindings(ws, projectId);
        runInAction(() => (this.bindings[projectId] = b));
      }, force),
    ]).catch(() => undefined);
  }

  loadIssueValues(ws: string, projectId: string, issueId: string) {
    return this.once(`vals:${issueId}`, async () => {
      const v = await this.service.getIssueValues(ws, projectId, issueId);
      runInAction(() => (this.values[issueId] = v));
    }).catch(() => undefined);
  }

  loadProjectValues(ws: string, projectId: string) {
    return this.once(`pvals:${projectId}`, async () => {
      const all = await this.service.getProjectValues(ws, projectId);
      runInAction(() => {
        for (const [issueId, vals] of Object.entries(all)) this.values[issueId] = vals;
      });
    }).catch(() => undefined);
  }

  loadColumns(ws: string, projectId: string) {
    return this.once(`cols:${projectId}`, async () => {
      const c = await this.service.getColumns(ws, projectId);
      runInAction(() => (this.columns[projectId] = c.definition_ids));
    }).catch(() => undefined);
  }

  async toggleColumn(ws: string, projectId: string, definitionId: string) {
    const current = this.columns[projectId] ?? [];
    const next = current.includes(definitionId) ? current.filter((i) => i !== definitionId) : [...current, definitionId];
    runInAction(() => (this.columns[projectId] = next));
    try {
      const saved = await this.service.setColumns(ws, projectId, next);
      runInAction(() => (this.columns[projectId] = saved.definition_ids));
    } catch {
      runInAction(() => (this.columns[projectId] = current));
    }
  }

  /** Bound, non-archived definitions of a project in binding order. */
  boundDefinitions(ws: string, projectId: string): TExtDefinition[] {
    const defs = this.definitions[ws] ?? [];
    const byId = new Map(defs.map((d) => [d.id, d]));
    return (this.bindings[projectId] ?? [])
      .filter((b) => b.is_enabled)
      .map((b) => byId.get(b.definition_id))
      .filter((d): d is TExtDefinition => !!d && !d.is_archived);
  }

  visibleColumns(ws: string, projectId: string): TExtDefinition[] {
    const ids = new Set(this.columns[projectId] ?? []);
    return this.boundDefinitions(ws, projectId).filter((d) => ids.has(d.id));
  }

  /** Optimistic write; rolls back and records the error message on failure. */
  async setValue(ws: string, projectId: string, issueId: string, definitionId: string, value: TExtValue) {
    const before = this.values[issueId]?.[definitionId] ?? null;
    if (!this.values[issueId]) this.values[issueId] = {};
    this.values[issueId][definitionId] = value;
    delete this.errors[`${issueId}:${definitionId}`];
    try {
      const saved = await this.service.setValue(ws, projectId, issueId, definitionId, value);
      runInAction(() => (this.values[issueId][definitionId] = saved.value));
    } catch (e: unknown) {
      runInAction(() => {
        this.values[issueId][definitionId] = before;
        const detail = e as Record<string, unknown> | undefined;
        this.errors[`${issueId}:${definitionId}`] =
          typeof detail === "object" && detail ? JSON.stringify(detail) : "Could not save the value";
      });
    }
  }
}

export const extStore = new ExtStore();
