/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

export type TExtPropertyType = "dropdown" | "text" | "date" | "member" | "datetime";

export type TExtOption = { id: string; name: string; color: string; sort_order: number; is_archived: boolean };

export type TExtDefinition = {
  id: string;
  key: string;
  name: string;
  description: string;
  help_text: string;
  type: TExtPropertyType;
  is_multi: boolean;
  is_required: boolean;
  default_value: unknown;
  sort_order: number;
  is_archived: boolean;
  options: TExtOption[];
};

export type TExtBinding = {
  definition_id: string;
  key: string;
  sort_order: number;
  is_enabled: boolean;
  show_on_card: boolean;
};

/** A stored value: option/member id(s), ISO date/date-time, or text. */
export type TExtValue = string | string[] | null;

/** issueId -> definitionId -> value */
export type TExtValueMap = Record<string, Record<string, TExtValue>>;

export type TExtFlags = Record<string, boolean>;
