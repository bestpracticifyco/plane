/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

import { useEffect } from "react";
import { observer } from "mobx-react";
import { LabelPropertyIcon } from "@plane/propel/icons";
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
import { extStore } from "../../store/ext.store";
import { RecurrenceRow } from "../recurrence/recurrence-row";
import { ExtValueEditor } from "./ext-value-editor";

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled: boolean;
};

/** Bound custom properties, then the "Repeats" row, beneath the native ones in the work-item sidebar
 *  and peek view (FR-EXT-020). Patches 0001/0006 render this component; nothing else is injected. */
export const ExtPropertiesPanel = observer(function ExtPropertiesPanel(props: Props) {
  const { workspaceSlug, projectId, issueId, disabled } = props;

  useEffect(() => {
    if (!workspaceSlug || !projectId || !issueId) return;
    void extStore
      .loadProject(workspaceSlug, projectId)
      .then(() => extStore.loadIssueValues(workspaceSlug, projectId, issueId));
  }, [workspaceSlug, projectId, issueId]);

  const showProperties =
    extStore.isEnabled(workspaceSlug, "ext.properties") && extStore.isEnabled(workspaceSlug, "ext.sidebar");
  const definitions = showProperties ? extStore.boundDefinitions(workspaceSlug, projectId) : [];

  return (
    <>
      {definitions.map((d) => {
        const error = extStore.errors[`${issueId}:${d.id}`];
        return (
          <SidebarPropertyListItem
            key={d.id}
            icon={LabelPropertyIcon}
            label={d.is_required ? `${d.name} *` : d.name}
            appendElement={
              d.help_text ? (
                <span title={d.help_text} className="cursor-help">
                  ⓘ
                </span>
              ) : undefined
            }
          >
            <ExtValueEditor
              workspaceSlug={workspaceSlug}
              projectId={projectId}
              issueId={issueId}
              definition={d}
              disabled={disabled}
            />
            {error && <span className="w-full text-caption-sm-regular text-danger-primary">{error}</span>}
          </SidebarPropertyListItem>
        );
      })}
      <RecurrenceRow workspaceSlug={workspaceSlug} projectId={projectId} issueId={issueId} disabled={disabled} />
    </>
  );
});
