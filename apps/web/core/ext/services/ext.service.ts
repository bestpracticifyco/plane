/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";
import type { TExtBinding, TExtDefinition, TExtFlags, TExtValue, TExtValueMap } from "../types";

const BASE = "/api/ext/v1/workspaces";

export class ExtService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private async call<T>(promise: Promise<{ data: T }>): Promise<T> {
    try {
      return (await promise).data;
    } catch (error: unknown) {
      throw (error as { response?: { data?: unknown } })?.response?.data ?? error;
    }
  }

  getFlags(ws: string) {
    return this.call<TExtFlags>(this.get(`${BASE}/${ws}/flags/`));
  }
  getDefinitions(ws: string) {
    return this.call<TExtDefinition[]>(this.get(`${BASE}/${ws}/properties/`));
  }
  getBindings(ws: string, projectId: string) {
    return this.call<TExtBinding[]>(this.get(`${BASE}/${ws}/projects/${projectId}/bindings/`));
  }
  getIssueValues(ws: string, projectId: string, issueId: string) {
    return this.call<Record<string, TExtValue>>(
      this.get(`${BASE}/${ws}/projects/${projectId}/work-items/${issueId}/values/`)
    );
  }
  getProjectValues(ws: string, projectId: string) {
    return this.call<TExtValueMap>(this.get(`${BASE}/${ws}/projects/${projectId}/values/`));
  }
  setValue(ws: string, projectId: string, issueId: string, definitionId: string, value: TExtValue) {
    return this.call<{ definition_id: string; value: TExtValue }>(
      this.patch(`${BASE}/${ws}/projects/${projectId}/work-items/${issueId}/values/${definitionId}/`, { value })
    );
  }
  getColumns(ws: string, projectId: string) {
    return this.call<{ definition_ids: string[] }>(this.get(`${BASE}/${ws}/projects/${projectId}/columns/`));
  }
  setColumns(ws: string, projectId: string, definitionIds: string[]) {
    return this.call<{ definition_ids: string[] }>(
      this.put(`${BASE}/${ws}/projects/${projectId}/columns/`, { definition_ids: definitionIds })
    );
  }
  handoff(ws: string) {
    return this.call<{ token: string; expires_at: string; governor_url: string }>(
      this.post(`${BASE}/${ws}/handoff/`, {})
    );
  }
}
