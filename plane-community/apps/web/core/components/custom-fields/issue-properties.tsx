/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

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
import { getFieldDetails, isEmptyValue } from "./helpers";
import type { TCustomFieldInputValue } from "./value-input";
import { CustomFieldValueInput } from "./value-input";

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
};

/** Custom field rows for the card side panel and the peek view. */
export const IssueCustomFieldProperties = observer(function IssueCustomFieldProperties(props: Props) {
  const { workspaceSlug, projectId, issueId, disabled, update } = props;
  const { getProjectFields, fetchProjectFields } = useCustomField();
  const {
    issue: { getIssueById },
    fetchIssue,
  } = useIssueDetail();

  const [showEmpty, setShowEmpty] = useState(false);
  const fields = getProjectFields(projectId);
  const issue = getIssueById(issueId);
  if (!fields || !issue) return null;

  // A property with no value is hidden; a quiet link below the list shows them so they can be filled in.
  const isBlank = (field: TCustomField) => {
    const value = issue.custom_fields?.[field.id];
    return isEmptyValue(value) || (field.field_type === "checkbox" && value === false);
  };
  const blankCount = fields.filter(isBlank).length;
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
        </SidebarPropertyListItem>
      ))}
      {blankCount > 0 && (
        <button
          type="button"
          onClick={() => setShowEmpty((value) => !value)}
          className="px-2 py-1 text-left text-11 text-tertiary hover:text-secondary"
        >
          {showEmpty ? "Hide empty properties" : `Show ${blankCount} empty ${blankCount === 1 ? "property" : "properties"}`}
        </button>
      )}
      <AddCustomFieldButton workspaceSlug={workspaceSlug} projectId={projectId} variant="row" />
    </>
  );
});
