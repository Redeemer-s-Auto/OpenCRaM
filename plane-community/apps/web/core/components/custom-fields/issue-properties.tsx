/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { useState } from "react";
import { observer } from "mobx-react";
import type { TCustomField, TCustomFieldValues, TIssue } from "@plane/types";
// components
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local
import { AddCustomFieldButton } from "./add-field-button";
import { bumpBodyVersion } from "./body-version";
import { getFieldDetails, isEmptyValue } from "./helpers";
import type { TCustomFieldInputValue } from "./value-input";
import { CustomFieldValueInput } from "./value-input";

/**
 * Hides a built-in property row while it has no value; the "N empty properties" link (in
 * IssueCustomFieldProperties) shows them again.
 */
export function HideWhenBlank(props: { hide: boolean; children: ReactNode }) {
  return props.hide ? null : <>{props.children}</>;
}

type TUpdate = (workspaceSlug: string, projectId: string, issueId: string, data: Partial<TIssue>) => Promise<void>;

/**
 * Build the custom_fields payload for one change. The whole map goes to the
 * server (it skips unchanged keys) so the local copy stays complete.
 */
export const buildCustomFieldsPayload = (
  current: TCustomFieldValues | undefined,
  fieldId: string,
  value: TCustomFieldInputValue
): Partial<TIssue> => ({
  custom_fields: { ...(current ?? {}), [fieldId]: value } as TCustomFieldValues,
});

const hasNewLabels = (value: TCustomFieldInputValue) =>
  Array.isArray(value) && value.some((item) => typeof item === "object" && item !== null);

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled: boolean;
  update: TUpdate;
  /** Built-in rows hidden because they are blank (the parent decides), counted in the same link. */
  hiddenBuiltIns?: number;
  /** The show/hide state is owned by the parent so built-in and custom rows toggle together. */
  showEmpty?: boolean;
  onToggleEmpty?: () => void;
};

/** Custom field rows for the card side panel and the peek view. */
export const IssueCustomFieldProperties = observer(function IssueCustomFieldProperties(props: Props) {
  const { workspaceSlug, projectId, issueId, disabled, update, hiddenBuiltIns = 0 } = props;
  const { getProjectFields, fetchProjectFields } = useCustomField();
  const {
    issue: { getIssueById },
    fetchIssue,
  } = useIssueDetail();

  const [ownShowEmpty, setOwnShowEmpty] = useState(false);
  const showEmpty = props.showEmpty ?? ownShowEmpty;
  const toggleEmpty = props.onToggleEmpty ?? (() => setOwnShowEmpty((value) => !value));
  const fields = getProjectFields(projectId);
  const issue = getIssueById(issueId);
  if (!fields || !issue) return null;

  // A property with no value is hidden; a quiet link below the list shows them so they can be filled in.
  const isBlank = (field: TCustomField) => {
    const value = issue.custom_fields?.[field.id];
    return isEmptyValue(value) || (field.field_type === "checkbox" && value === false);
  };
  const blankCount = fields.filter(isBlank).length + hiddenBuiltIns;
  const shownFields = showEmpty ? fields : fields.filter((field) => !isBlank(field));

  const handleChange = async (field: TCustomField, value: TCustomFieldInputValue) => {
    await update(workspaceSlug, projectId, issueId, buildCustomFieldsPayload(issue.custom_fields, field.id, value));
    if (hasNewLabels(value)) {
      // New tags became options on the server; load their ids.
      await Promise.all([fetchProjectFields(workspaceSlug, projectId), fetchIssue(workspaceSlug, projectId, issueId)]);
    } else if (field.field_type === "relation") {
      // Rollups on this card follow the new links; the server works them out.
      await fetchIssue(workspaceSlug, projectId, issueId);
    }
  };

  const escapeHtml = (text: string) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  // Moves text typed into a long-text property (like "Description") into the page body editor.
  const moveToBody = async (field: TCustomField) => {
    const text = String(issue.custom_fields?.[field.id] ?? "").trim();
    if (!text) return;
    const paragraphs = text
      .split(/\n+/)
      .map((line) => `<p>${escapeHtml(line)}</p>`)
      .join("");
    await update(workspaceSlug, projectId, issueId, {
      description_html: `${issue.description_html ?? ""}${paragraphs}`,
      ...buildCustomFieldsPayload(issue.custom_fields, field.id, ""),
    });
    await fetchIssue(workspaceSlug, projectId, issueId);
    bumpBodyVersion(issueId);
  };

  return (
    <>
      {shownFields.map((field) => (
        <SidebarPropertyListItem
          key={field.id}
          icon={getFieldDetails(field).icon}
          label={field.name}
          childrenClassName="min-w-0"
        >
          <CustomFieldValueInput
            field={field}
            value={issue.custom_fields?.[field.id]}
            onChange={(value) => handleChange(field, value)}
            projectId={projectId}
            disabled={disabled}
          />
          {field.field_type === "long_text" && !disabled && !isBlank(field) && (
            <button
              type="button"
              onClick={() => void moveToBody(field)}
              className="mt-1 text-11 text-tertiary hover:text-secondary"
            >
              Move to page body
            </button>
          )}
        </SidebarPropertyListItem>
      ))}
      {blankCount > 0 && (
        <button
          type="button"
          onClick={toggleEmpty}
          className="px-2 py-1 text-left text-11 text-tertiary hover:text-secondary"
        >
          {showEmpty ? "Hide empty properties" : `${blankCount} empty ${blankCount === 1 ? "property" : "properties"}`}
        </button>
      )}
      <AddCustomFieldButton workspaceSlug={workspaceSlug} projectId={projectId} variant="row" />
    </>
  );
});
