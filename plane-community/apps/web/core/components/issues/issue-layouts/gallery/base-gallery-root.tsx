/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { FC } from "react";
import { useCallback, useEffect } from "react";
import { observer } from "mobx-react";
// plane imports
import { ALL_ISSUES, EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { Button } from "@plane/propel/button";
import type { EIssuesStoreType } from "@plane/types";
import { EIssueLayoutTypes } from "@plane/types";
// hooks
import { useIssues } from "@/hooks/store/use-issues";
import { useUserPermissions } from "@/hooks/store/user";
import { useIssueStoreType } from "@/hooks/use-issue-layout-store";
import { useIssuesActions } from "@/hooks/use-issues-actions";
// local imports
import { IssueLayoutHOC } from "../issue-layout-HOC";
import type { IQuickActionProps, TRenderQuickActions } from "../list/list-view-types";
import { GalleryCard } from "./gallery-card";

export type GalleryStoreType =
  | EIssuesStoreType.PROJECT
  | EIssuesStoreType.MODULE
  | EIssuesStoreType.CYCLE
  | EIssuesStoreType.PROJECT_VIEW;

interface IBaseGalleryRoot {
  QuickActions: FC<IQuickActionProps>;
  canEditPropertiesBasedOnProject?: (projectId: string) => boolean;
  isCompletedCycle?: boolean;
  viewId?: string | undefined;
}

/** Gallery layout (Notion-style): cards as tiles with a cover image. Flat, not grouped. */
export const BaseGalleryRoot = observer(function BaseGalleryRoot(props: IBaseGalleryRoot) {
  const { QuickActions, canEditPropertiesBasedOnProject, isCompletedCycle = false, viewId } = props;
  // store hooks
  const storeType = useIssueStoreType() as GalleryStoreType;
  const { allowPermissions } = useUserPermissions();
  const { issues, issuesFilter, issueMap } = useIssues(storeType);
  const { fetchIssues, fetchNextIssues, updateIssue, removeIssue, removeIssueFromView, archiveIssue, restoreIssue } =
    useIssuesActions(storeType);
  // derived values
  const { enableInlineEditing } = issues?.viewFlags || {};
  const isEditingAllowed = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.PROJECT
  );

  useEffect(() => {
    fetchIssues("init-loader", { canGroup: false, perPageCount: 60 }, viewId);
  }, [fetchIssues, storeType, viewId]);

  const canEditProperties = useCallback(
    (projectId: string | undefined) => {
      const allowedForProject =
        canEditPropertiesBasedOnProject && projectId ? canEditPropertiesBasedOnProject(projectId) : isEditingAllowed;
      return !!enableInlineEditing && allowedForProject && !isCompletedCycle;
    },
    [canEditPropertiesBasedOnProject, enableInlineEditing, isEditingAllowed, isCompletedCycle]
  );

  const renderQuickActions: TRenderQuickActions = useCallback(
    ({ issue, parentRef, customActionButton, placement, portalElement }) => (
      <QuickActions
        parentRef={parentRef}
        customActionButton={customActionButton}
        issue={issue}
        handleDelete={async () => removeIssue(issue.project_id, issue.id)}
        handleUpdate={async (data) => updateIssue && updateIssue(issue.project_id, issue.id, data)}
        handleRemoveFromView={async () => removeIssueFromView && removeIssueFromView(issue.project_id, issue.id)}
        handleArchive={async () => archiveIssue && archiveIssue(issue.project_id, issue.id)}
        handleRestore={async () => restoreIssue && restoreIssue(issue.project_id, issue.id)}
        portalElement={portalElement}
        readOnly={!canEditProperties(issue.project_id ?? undefined)}
        placements={placement}
      />
    ),
    [canEditProperties, removeIssue, updateIssue, removeIssueFromView, archiveIssue, restoreIssue]
  );

  const issueIds = issues.groupedIssueIds?.[ALL_ISSUES] ?? [];
  const nextPageResults = issues.getPaginationData(ALL_ISSUES, undefined)?.nextPageResults;
  const isLoadingMore = issues.getIssueLoader() === "pagination";

  if (!Array.isArray(issueIds)) return null;

  const displayProperties = issuesFilter.issueFilters?.displayProperties ?? {};

  return (
    <IssueLayoutHOC layout={EIssueLayoutTypes.GALLERY}>
      <div className="vertical-scrollbar scrollbar-lg h-full w-full overflow-y-auto px-page-x py-4">
        <div className="grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-4">
          {issueIds.map((issueId) => {
            const issue = issueMap[issueId];
            if (!issue) return null;
            return (
              <GalleryCard
                key={issueId}
                issue={issue}
                displayProperties={displayProperties}
                quickActions={renderQuickActions}
                updateIssue={updateIssue}
                isReadOnly={!canEditProperties(issue.project_id ?? undefined)}
              />
            );
          })}
        </div>
        {nextPageResults && (
          <div className="flex justify-center py-4">
            <Button variant="secondary" size="lg" loading={isLoadingMore} onClick={() => fetchNextIssues()}>
              Load more
            </Button>
          </div>
        )}
      </div>
    </IssueLayoutHOC>
  );
});
