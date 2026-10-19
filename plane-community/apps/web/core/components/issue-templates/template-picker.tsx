/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { LayoutTemplate } from "lucide-react";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { CustomMenu } from "@plane/ui";
// local
import { useCreateFromTemplate, useIssueTemplates } from "./use-issue-templates";

type Props = {
  workspaceSlug: string;
  projectId: string;
  /** The title typed so far; used as the new card's title if not empty. */
  currentTitle?: string;
  /** Called after the card was made from a template (close the new-card window). */
  onCreated: () => void;
};

/** "Template: Blank ▾" in the new-card window. Picking a template makes the card right away. */
export const TemplatePicker = observer(function TemplatePicker(props: Props) {
  const { workspaceSlug, projectId, currentTitle, onCreated } = props;
  const { templates } = useIssueTemplates(workspaceSlug, projectId);
  const createFromTemplate = useCreateFromTemplate();
  const [busy, setBusy] = useState(false);

  if (!projectId || templates.length === 0) return null;

  const handlePick = async (templateId: string, templateName: string) => {
    setBusy(true);
    try {
      const result = await createFromTemplate(workspaceSlug, projectId, templateId, currentTitle?.trim() || undefined);
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: "Card created from template",
        message:
          result.created_count > 1
            ? `${templateName}: ${result.created_count} cards (with sub-cards).`
            : templateName,
      });
      onCreated();
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not use the template", message: "Try again." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <CustomMenu
      customButton={
        <span className="flex items-center gap-1.5 rounded-md border border-subtle px-2 py-1 text-body-xs-regular text-secondary hover:bg-layer-1">
          <LayoutTemplate className="size-3.5" />
          {busy ? "Creating…" : "Template: Blank"}
        </span>
      }
      placement="bottom-start"
      closeOnSelect
      disabled={busy}
    >
      <CustomMenu.MenuItem onClick={() => undefined}>
        <span className="text-secondary">Blank</span>
      </CustomMenu.MenuItem>
      {templates.map((template) => (
        <CustomMenu.MenuItem key={template.id} onClick={() => handlePick(template.id, template.name)}>
          <div className="flex flex-col">
            <span>{template.name}</span>
            {template.description && <span className="text-caption-md-regular text-tertiary">{template.description}</span>}
          </div>
        </CustomMenu.MenuItem>
      ))}
    </CustomMenu>
  );
});
