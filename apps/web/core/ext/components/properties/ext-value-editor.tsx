/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { CustomSearchSelect } from "@plane/ui";
import { renderFormattedPayloadDate } from "@plane/utils";
import { DateDropdown } from "@/components/dropdowns/date";
import { MemberDropdown } from "@/components/dropdowns/member/dropdown";
import { extStore } from "../../store/ext.store";
import type { TExtDefinition, TExtValue } from "../../types";

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  definition: TExtDefinition;
  disabled: boolean;
  /** "sidebar" uses full-width buttons; "cell" is compact for spreadsheet rows. */
  variant?: "sidebar" | "cell";
};

const asArray = (v: TExtValue): string[] => (Array.isArray(v) ? v : v ? [v] : []);

/** Type-appropriate editor for one plane_ext property value (FR-EXT-020/022). */
export const ExtValueEditor = observer(function ExtValueEditor(props: Props) {
  const { workspaceSlug, projectId, issueId, definition: d, disabled, variant = "sidebar" } = props;
  const value = extStore.values[issueId]?.[d.id] ?? null;
  const save = (v: TExtValue) => extStore.setValue(workspaceSlug, projectId, issueId, d.id, v);
  const buttonClassName = variant === "sidebar" ? "w-full h-7.5 justify-start" : "h-full w-full px-2 justify-start";
  const [draft, setDraft] = useState<string | null>(null);

  if (d.type === "dropdown") {
    const options = d.options
      .filter((o) => !o.is_archived)
      .map((o) => ({
        value: o.id,
        query: o.name,
        content: (
          <span className="flex items-center gap-1.5">
            <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: o.color || "#9AA3AF" }} />
            {o.name}
          </span>
        ),
      }));
    const names = asArray(value)
      .map((id) => d.options.find((o) => o.id === id)?.name)
      .filter(Boolean)
      .join(", ");
    const label = <span className={names ? "" : "text-placeholder"}>{names || "Empty"}</span>;
    return d.is_multi ? (
      <CustomSearchSelect
        multiple
        value={asArray(value)}
        onChange={(v: string[]) => save(v)}
        options={options}
        label={label}
        disabled={disabled}
        buttonClassName={buttonClassName}
        className="w-full"
      />
    ) : (
      <CustomSearchSelect
        value={asArray(value)[0] ?? null}
        onChange={(v: string) => save(v === asArray(value)[0] ? null : v)}
        options={options}
        label={label}
        disabled={disabled}
        buttonClassName={buttonClassName}
        className="w-full"
      />
    );
  }

  if (d.type === "member") {
    return d.is_multi ? (
      <MemberDropdown
        multiple
        value={asArray(value)}
        onChange={(v: string[]) => save(v)}
        projectId={projectId}
        buttonVariant="transparent-with-text"
        buttonClassName={buttonClassName}
        className="w-full"
        disabled={disabled}
        placeholder="Empty"
      />
    ) : (
      <MemberDropdown
        multiple={false}
        value={asArray(value)[0] ?? null}
        onChange={(v: string | null) => save(v)}
        projectId={projectId}
        buttonVariant="transparent-with-text"
        buttonClassName={buttonClassName}
        className="w-full"
        disabled={disabled}
        placeholder="Empty"
      />
    );
  }

  if (d.type === "date") {
    return (
      <DateDropdown
        value={typeof value === "string" ? value : null}
        onChange={(v: Date | null) => save(v ? renderFormattedPayloadDate(v) ?? null : null)}
        buttonVariant="transparent-with-text"
        buttonClassName={buttonClassName}
        className="w-full"
        disabled={disabled}
        placeholder="Empty"
      />
    );
  }

  // text and datetime: plain inputs, saved on blur when changed.
  const isDateTime = d.type === "datetime";
  const shown = draft ?? (typeof value === "string" ? (isDateTime ? value.slice(0, 16) : value) : "");
  return (
    <input
      type={isDateTime ? "datetime-local" : "text"}
      className="h-7.5 w-full rounded-sm border-0 bg-transparent px-2 text-body-xs-regular text-primary outline-none placeholder:text-placeholder hover:bg-layer-transparent-hover focus:bg-layer-transparent-hover disabled:cursor-not-allowed"
      placeholder="Empty"
      value={shown}
      disabled={disabled}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={() => {
        if (draft === null) return;
        const next = draft.trim() === "" ? null : isDateTime ? new Date(draft).toISOString() : draft;
        setDraft(null);
        if (next !== value) void save(next);
      }}
    />
  );
});
