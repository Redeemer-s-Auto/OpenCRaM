/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { ArrowDownWideNarrow, ArrowUpNarrowWide, ChevronDownIcon, Eraser } from "lucide-react";
import type {
  IIssueDisplayFilterOptions,
  IIssueDisplayProperties,
  TCustomField,
  TIssue,
  TIssueOrderByOptions,
} from "@plane/types";
import { CustomMenu, Row } from "@plane/ui";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// local
import { AddCustomFieldButton } from "./add-field-button";
import { getFieldDetails, isLinkedField, isSeenField } from "./helpers";
import { buildCustomFieldsPayload } from "./issue-properties";
import { SeenCheck, useSeenField } from "./seen-check";
import { useRefetchWorkItems } from "./use-refetch-work-items";
import { CustomFieldValueInput } from "./value-input";

export const customFieldDisplayKey = (fieldId: string) => `customfield_${fieldId}` as const;

/** A custom field column shows unless the user turned it off in Display. */
export const isCustomFieldColumnShown = (displayProperties: IIssueDisplayProperties, fieldId: string) =>
  displayProperties[customFieldDisplayKey(fieldId)] !== false;

/**
 * Live custom fields of the board in the URL, as table columns. Empty outside a single board.
 * The Seen box is left out: it is the last column of the table (SeenHeaderColumn / SeenCell).
 */
export const useSpreadsheetCustomFields = (): TCustomField[] => {
  const { projectId } = useParams();
  const { getProjectFields } = useCustomField();
  return (getProjectFields(projectId?.toString()) ?? []).filter((field) => !isSeenField(field));
};

/** Header of the check-mark column at the right end of a task-style board's table. */
export const SeenHeaderColumn = observer(function SeenHeaderColumn() {
  const { projectId } = useParams();
  const field = useSeenField(projectId?.toString());
  if (!field) return null;
  return (
    <th
      className="h-11 w-14 min-w-14 border border-t-0 border-b-0 border-subtle bg-layer-1 px-2 text-center text-13 font-medium text-secondary"
      tabIndex={-1}
    >
      {field.name}
    </th>
  );
});

/** The check-mark cell at the right end of a task-style board's table row. */
export const SeenCell = observer(function SeenCell(props: Omit<TCellProps, "displayProperties">) {
  const { issueDetail, disableUserActions, updateIssue } = props;
  const { projectId } = useParams();
  const field = useSeenField(projectId?.toString());
  if (!field) return null;
  return (
    <td
      tabIndex={0}
      className="h-11 w-14 min-w-14 border-r-[1px] border-subtle text-13 after:absolute after:bottom-[-1px] after:w-full after:border after:border-subtle"
    >
      <div className="flex h-full w-full items-center justify-center">
        <SeenCheck issue={issueDetail} updateIssue={updateIssue} isReadOnly={disableUserActions} />
      </div>
    </td>
  );
});

type THeaderProps = {
  displayProperties: IIssueDisplayProperties;
  displayFilters: IIssueDisplayFilterOptions;
  handleDisplayFilterUpdate: (data: Partial<IIssueDisplayFilterOptions>) => void;
};

export const CustomFieldHeaderColumns = observer(function CustomFieldHeaderColumns(props: THeaderProps) {
  const { displayProperties, displayFilters, handleDisplayFilterUpdate } = props;
  const { workspaceSlug, projectId } = useParams();
  const fields = useSpreadsheetCustomFields();

  return (
    <>
      {fields
        .filter((field) => isCustomFieldColumnShown(displayProperties, field.id))
        .map((field) => {
          const ascending = `custom_field__${field.id}` as TIssueOrderByOptions;
          const descending = `-custom_field__${field.id}` as TIssueOrderByOptions;
          const active = displayFilters.order_by === ascending || displayFilters.order_by === descending;
          const Icon = getFieldDetails(field).icon;
          return (
            <th
              key={field.id}
              className="h-11 min-w-36 items-center border border-t-0 border-b-0 border-subtle bg-layer-1 py-1 text-13 font-medium"
              tabIndex={0}
            >
              <CustomMenu
                customButtonClassName="clickable !w-full"
                customButtonTabIndex={-1}
                className="!w-full"
                customButton={
                  <Row className="flex w-full cursor-pointer items-center justify-between gap-1.5 py-2 text-13 text-secondary hover:text-primary">
                    <div className="flex min-w-0 items-center gap-1.5">
                      <Icon className="h-4 w-4 shrink-0 text-placeholder" />
                      <span className="truncate">{field.name}</span>
                    </div>
                    <div className="ml-3 flex">
                      {active &&
                        (displayFilters.order_by === ascending ? (
                          <ArrowDownWideNarrow className="h-3 w-3" />
                        ) : (
                          <ArrowUpNarrowWide className="h-3 w-3" />
                        ))}
                      <ChevronDownIcon className="h-3 w-3" aria-hidden="true" />
                    </div>
                  </Row>
                }
                placement="bottom-start"
                closeOnSelect
              >
                {isLinkedField(field) && (
                  <CustomMenu.MenuItem disabled>
                    <span className="px-1 text-tertiary">Linked values cannot be sorted</span>
                  </CustomMenu.MenuItem>
                )}
                {!isLinkedField(field) && (
                  <>
                <CustomMenu.MenuItem onClick={() => handleDisplayFilterUpdate({ order_by: ascending })}>
                  <div className="flex items-center gap-2 px-1">
                    <ArrowDownWideNarrow className="h-3 w-3 stroke-[1.5]" />
                    <span>Sort ascending</span>
                  </div>
                </CustomMenu.MenuItem>
                <CustomMenu.MenuItem onClick={() => handleDisplayFilterUpdate({ order_by: descending })}>
                  <div className="flex items-center gap-2 px-1">
                    <ArrowUpNarrowWide className="h-3 w-3 stroke-[1.5]" />
                    <span>Sort descending</span>
                  </div>
                </CustomMenu.MenuItem>
                  </>
                )}
                {active && (
                  <CustomMenu.MenuItem onClick={() => handleDisplayFilterUpdate({ order_by: "-created_at" })}>
                    <div className="flex items-center gap-2 px-1">
                      <Eraser className="h-3 w-3" />
                      <span>Clear sorting</span>
                    </div>
                  </CustomMenu.MenuItem>
                )}
              </CustomMenu>
            </th>
          );
        })}
      {projectId && (
        <th className="h-11 w-12 border border-t-0 border-b-0 border-subtle bg-layer-1 text-13" tabIndex={-1}>
          <AddCustomFieldButton
            workspaceSlug={workspaceSlug?.toString() ?? ""}
            projectId={projectId.toString()}
            variant="header"
          />
        </th>
      )}
    </>
  );
});

type TCellProps = {
  displayProperties: IIssueDisplayProperties;
  issueDetail: TIssue;
  disableUserActions: boolean;
  updateIssue: ((projectId: string | null, issueId: string, data: Partial<TIssue>) => Promise<void>) | undefined;
};

export const CustomFieldCells = observer(function CustomFieldCells(props: TCellProps) {
  const { displayProperties, issueDetail, disableUserActions, updateIssue } = props;
  const { workspaceSlug, projectId } = useParams();
  const fields = useSpreadsheetCustomFields();
  const { fetchIssue } = useIssueDetail();
  const refetch = useRefetchWorkItems();

  return (
    <>
      {fields
        .filter((field) => isCustomFieldColumnShown(displayProperties, field.id))
        .map((field) => (
          <td
            key={field.id}
            tabIndex={0}
            className="h-11 min-w-36 max-w-72 border-r-[1px] border-subtle text-13 after:absolute after:bottom-[-1px] after:w-full after:border after:border-subtle"
          >
            <div className="flex h-full w-full items-center px-1">
              <CustomFieldValueInput
                field={field}
                value={issueDetail.custom_fields?.[field.id]}
                projectId={issueDetail.project_id ?? ""}
                disabled={disableUserActions || !updateIssue}
                variant="cell"
                onChange={async (value) => {
                  await updateIssue?.(
                    issueDetail.project_id,
                    issueDetail.id,
                    buildCustomFieldsPayload(issueDetail.custom_fields, field.id, value)
                  );
                  // New links change this card's rollups; the server works them out.
                  if (field.field_type === "relation" && workspaceSlug && issueDetail.project_id)
                    await fetchIssue(workspaceSlug.toString(), issueDetail.project_id, issueDetail.id);
                  // A ticked box can move the card out of a filtered view (Completed -> Checked).
                  if (field.field_type === "checkbox") await refetch();
                }}
              />
            </div>
          </td>
        ))}
      {/* empty cell under the "+" header column */}
      {projectId && <td className="h-11 w-12 border-r-[1px] border-subtle" />}
    </>
  );
});
