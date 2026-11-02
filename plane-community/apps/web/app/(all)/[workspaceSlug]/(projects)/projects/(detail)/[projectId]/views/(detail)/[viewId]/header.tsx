/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useRef } from "react";
import { Plus, SlidersHorizontal } from "lucide-react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";

// plane imports
import {
  EIssueFilterType,
  ISSUE_DISPLAY_FILTERS_BY_PAGE,
  EUserPermissions,
  EUserPermissionsLevel,
  WORK_ITEM_TRACKER_ELEMENTS,
} from "@plane/constants";
import { Button } from "@plane/propel/button";
import { LockIcon } from "@plane/propel/icons";
import { Tooltip } from "@plane/propel/tooltip";
import type { IIssueDisplayFilterOptions, IIssueDisplayProperties } from "@plane/types";
import { EIssuesStoreType, EViewAccess, EIssueLayoutTypes } from "@plane/types";
import { Header } from "@plane/ui";
// components
import { BoardTitle } from "@/components/common/board-title";
import { PropertiesButton } from "@/components/custom-fields/properties-button";
import {
  DisplayFiltersSelection,
  FiltersDropdown,
  LayoutSelection,
  MobileLayoutSelection,
} from "@/components/issues/issue-layouts/filters";
import { ViewQuickActions } from "@/components/views/quick-actions";
import { WorkItemFiltersToggle } from "@/components/work-item-filters/filters-toggle";
// hooks
import { useCommandPalette } from "@/hooks/store/use-command-palette";
import { useIssues } from "@/hooks/store/use-issues";
import { useProject } from "@/hooks/store/use-project";
import { useProjectView } from "@/hooks/store/use-project-view";
import { useUserPermissions } from "@/hooks/store/user";
// plane web imports

const VIEW_LAYOUTS = [
  EIssueLayoutTypes.LIST,
  EIssueLayoutTypes.KANBAN,
  EIssueLayoutTypes.CALENDAR,
  EIssueLayoutTypes.SPREADSHEET,
  EIssueLayoutTypes.GALLERY,
  EIssueLayoutTypes.GANTT,
];

export const ProjectViewIssuesHeader = observer(function ProjectViewIssuesHeader() {
  // refs
  const parentRef = useRef(null);
  const { workspaceSlug, projectId, viewId: routerViewId } = useParams();
  const viewId = routerViewId ? routerViewId.toString() : undefined;
  // store hooks
  const {
    issuesFilter: { issueFilters, updateFilters },
  } = useIssues(EIssuesStoreType.PROJECT_VIEW);
  const { toggleCreateIssueModal } = useCommandPalette();
  const { allowPermissions } = useUserPermissions();

  const { currentProjectDetails } = useProject();
  const { getViewById } = useProjectView();

  const activeLayout = issueFilters?.displayFilters?.layout;

  const handleLayoutChange = useCallback(
    (layout: EIssueLayoutTypes) => {
      if (!workspaceSlug || !projectId || !viewId) return;
      updateFilters(
        workspaceSlug.toString(),
        projectId.toString(),
        EIssueFilterType.DISPLAY_FILTERS,
        { layout: layout },
        viewId.toString()
      );
    },
    [workspaceSlug, projectId, viewId, updateFilters]
  );

  const handleDisplayFilters = useCallback(
    (updatedDisplayFilter: Partial<IIssueDisplayFilterOptions>) => {
      if (!workspaceSlug || !projectId || !viewId) return;
      updateFilters(
        workspaceSlug.toString(),
        projectId.toString(),
        EIssueFilterType.DISPLAY_FILTERS,
        updatedDisplayFilter,
        viewId.toString()
      );
    },
    [workspaceSlug, projectId, viewId, updateFilters]
  );

  const handleDisplayProperties = useCallback(
    (property: Partial<IIssueDisplayProperties>) => {
      if (!workspaceSlug || !projectId || !viewId) return;
      updateFilters(
        workspaceSlug.toString(),
        projectId.toString(),
        EIssueFilterType.DISPLAY_PROPERTIES,
        property,
        viewId.toString()
      );
    },
    [workspaceSlug, projectId, viewId, updateFilters]
  );

  const viewDetails = viewId ? getViewById(viewId.toString()) : null;

  const canUserCreateIssue = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.PROJECT
  );

  if (!viewDetails) return;

  return (
    // The board name is the heading; the buttons wrap under it only when both do not fit on one line.
    <Header className="flex-wrap gap-y-1 py-1.5">
      <Header.LeftItem className="max-w-full min-w-0 flex-grow-0 flex-nowrap">
        <BoardTitle projectId={projectId?.toString()}>
          {viewDetails?.access === EViewAccess.PRIVATE && (
            <div className="flex-shrink-0 cursor-default text-tertiary">
              <Tooltip tooltipContent={"Private"}>
                <LockIcon className="h-4 w-4" />
              </Tooltip>
            </div>
          )}
        </BoardTitle>
      </Header.LeftItem>
      <Header.RightItem className="ml-auto flex-shrink-0 items-center">
        <>
          {/* Narrow header (phone, half screen): a one-button menu stands in for the six layout icons. */}
          {!viewDetails.is_locked && (
            <>
              <div className="hidden @4xl:flex">
                <LayoutSelection
                  layouts={VIEW_LAYOUTS}
                  onChange={(layout) => handleLayoutChange(layout)}
                  selectedLayout={activeLayout}
                />
              </div>
              <div className="flex @4xl:hidden">
                <MobileLayoutSelection
                  layouts={VIEW_LAYOUTS}
                  onChange={(layout) => handleLayoutChange(layout)}
                  activeLayout={activeLayout}
                />
              </div>
            </>
          )}
          {viewId && <WorkItemFiltersToggle entityType={EIssuesStoreType.PROJECT_VIEW} entityId={viewId} />}
          {!viewDetails.is_locked && (
            <FiltersDropdown
              title="Display"
              placement="bottom-end"
              miniIcon={<SlidersHorizontal className="size-3.5" />}
            >
              <DisplayFiltersSelection
                layoutDisplayFiltersOptions={
                  activeLayout ? ISSUE_DISPLAY_FILTERS_BY_PAGE.issues.layoutOptions[activeLayout] : undefined
                }
                displayFilters={issueFilters?.displayFilters ?? {}}
                handleDisplayFiltersUpdate={handleDisplayFilters}
                displayProperties={issueFilters?.displayProperties ?? {}}
                handleDisplayPropertiesUpdate={handleDisplayProperties}
                cycleViewDisabled={!currentProjectDetails?.cycle_view}
                moduleViewDisabled={!currentProjectDetails?.module_view}
              />
            </FiltersDropdown>
          )}
          {!viewDetails.is_locked && (
            <PropertiesButton
              workspaceSlug={workspaceSlug?.toString() ?? ""}
              projectId={projectId?.toString() ?? ""}
              layout={activeLayout}
              displayProperties={issueFilters?.displayProperties ?? {}}
              displayPropertiesToRender={
                activeLayout
                  ? ISSUE_DISPLAY_FILTERS_BY_PAGE.issues.layoutOptions[activeLayout]?.display_properties
                  : undefined
              }
              handleUpdate={handleDisplayProperties}
              cycleViewDisabled={!currentProjectDetails?.cycle_view}
              moduleViewDisabled={!currentProjectDetails?.module_view}
            />
          )}
        </>
        {canUserCreateIssue && (
          <Button
            variant="primary"
            size="lg"
            onClick={() => {
              toggleCreateIssueModal(true, EIssuesStoreType.PROJECT_VIEW);
            }}
            data-ph-element={WORK_ITEM_TRACKER_ELEMENTS.HEADER_ADD_BUTTON.PROJECT_VIEW}
            aria-label="Add work item"
            title="Add work item"
          >
            {/* Narrow header: a "+" alone, so the button always fits. */}
            <Plus className="size-4 @4xl:hidden" />
            <span className="hidden @4xl:inline">Add work item</span>
          </Button>
        )}
        <div className="hidden md:block">
          <ViewQuickActions
            parentRef={parentRef}
            customClassName="flex-shrink-0 flex items-center justify-center size-[26px] bg-layer-1/70 rounded-sm"
            projectId={projectId.toString()}
            view={viewDetails}
            workspaceSlug={workspaceSlug.toString()}
          />
        </div>
      </Header.RightItem>
    </Header>
  );
});
