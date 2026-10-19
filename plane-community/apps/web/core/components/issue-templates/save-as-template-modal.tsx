/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TIssue } from "@plane/types";
import { Checkbox, EModalPosition, EModalWidth, Input, ModalCore } from "@plane/ui";
// services
import { issueTemplateService } from "@/services/issue/issue_template.service";
// local
import { refreshIssueTemplates } from "./use-issue-templates";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  workspaceSlug: string;
  issue: TIssue;
};

export const SaveAsTemplateModal = observer(function SaveAsTemplateModal(props: Props) {
  const { isOpen, onClose, workspaceSlug, issue } = props;
  const [name, setName] = useState("");
  const [includeSubItems, setIncludeSubItems] = useState(true);
  const [saving, setSaving] = useState(false);
  const hasSubItems = (issue.sub_issues_count ?? 0) > 0;

  useEffect(() => {
    if (isOpen) {
      setName(issue.name ?? "");
      setIncludeSubItems(true);
    }
  }, [isOpen, issue.name]);

  const handleSave = async () => {
    if (!issue.project_id) return;
    setSaving(true);
    try {
      const template = await issueTemplateService.saveFromIssue(workspaceSlug, issue.project_id, issue.id, {
        name: name.trim() || undefined,
        include_sub_items: hasSubItems && includeSubItems,
      });
      await refreshIssueTemplates(issue.project_id);
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Template saved", message: template.name });
      onClose();
    } catch (error) {
      const message =
        (error && typeof error === "object" && Object.values(error as Record<string, unknown>).flat().find(
          (v) => typeof v === "string"
        )) || "Try again.";
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not save the template", message: String(message) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.LG}>
      <div className="flex flex-col gap-4 p-5">
        <h3 className="text-h5-medium text-primary">Save as template</h3>
        <p className="text-body-xs-regular text-tertiary">
          The template copies this card&apos;s title, page, fields, labels, priority and state. Anyone on this board can
          use it from the new-card window.
        </p>
        <label className="flex flex-col gap-1">
          <span className="text-body-xs-medium text-secondary">Template name</span>
          <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={255} autoFocus />
        </label>
        {hasSubItems && (
          <label className="flex items-center gap-2 text-body-xs-regular text-secondary">
            <Checkbox checked={includeSubItems} onChange={(e) => setIncludeSubItems(e.target.checked)} />
            Include sub-cards ({issue.sub_issues_count})
          </label>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" size="lg" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="lg" loading={saving} onClick={handleSave}>
            Save template
          </Button>
        </div>
      </div>
    </ModalCore>
  );
});
