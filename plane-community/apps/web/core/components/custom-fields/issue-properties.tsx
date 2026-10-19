/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import type { TCustomField, TCustomFieldValues, TIssue } from "@plane/types";
// components
import { SidebarPropertyListItem } from "@/components/common/layout/sidebar/property-list-item";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local
import { AddCustomFieldButton } from "./add-field-button";
import { getFieldTypeDetails } from "./helpers";
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

  const fields = getProjectFields(projectId);
  const issue = getIssueById(issueId);
  if (!fields || !issue) return null;

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
      {fields.map((field) => (
        <SidebarPropertyListItem
          key={field.id}
          icon={getFieldTypeDetails(field.field_type).icon}
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
      <AddCustomFieldButton workspaceSlug={workspaceSlug} projectId={projectId} variant="row" />
    </>
  );
});
