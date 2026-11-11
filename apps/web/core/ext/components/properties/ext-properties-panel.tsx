/**
 * SPDX-License-Identifier: AGPL-3.0-only
 * Copyright (c) 2026 Best Practicify LLC. This file is part of a fork of Plane (https://github.com/makeplane/plane).
 */

import { useEffect } from "react";
import { observer } from "mobx-react";
import { LabelPropertyIcon } from "@plane/propel/icons";
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
import { extStore } from "../../store/ext.store";
import { ExtValueEditor } from "./ext-value-editor";

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled: boolean;
};

/** Bound custom properties rendered beneath the native ones in the work-item sidebar (FR-EXT-020). */
export const ExtPropertiesPanel = observer(function ExtPropertiesPanel(props: Props) {
  const { workspaceSlug, projectId, issueId, disabled } = props;

  useEffect(() => {
    if (!workspaceSlug || !projectId || !issueId) return;
    void extStore.loadProject(workspaceSlug, projectId).then(() => extStore.loadIssueValues(workspaceSlug, projectId, issueId));
  }, [workspaceSlug, projectId, issueId]);

  if (!extStore.isEnabled(workspaceSlug, "ext.properties") || !extStore.isEnabled(workspaceSlug, "ext.sidebar")) return null;
  const definitions = extStore.boundDefinitions(workspaceSlug, projectId);
  if (definitions.length === 0) return null;

  return (
    <>
      {definitions.map((d) => {
        const error = extStore.errors[`${issueId}:${d.id}`];
        return (
          <SidebarPropertyListItem
            key={d.id}
            icon={LabelPropertyIcon}
            label={d.is_required ? `${d.name} *` : d.name}
            appendElement={d.help_text ? <span title={d.help_text} className="cursor-help">ⓘ</span> : undefined}
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
    </>
  );
});
