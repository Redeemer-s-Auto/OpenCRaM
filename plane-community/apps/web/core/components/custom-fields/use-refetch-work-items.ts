/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback } from "react";
import { useParams } from "next/navigation";
import { EIssuesStoreType } from "@plane/types";
// hooks
import { useIssues } from "@/hooks/store/use-issues";
import { useIssueStoreType } from "@/hooks/use-issue-layout-store";

/**
 * Reload the list the user is looking at, keeping its paging.
 *
 * A saved view filters on the server (for example "Completed" = done and Seen not ticked),
 * so a card whose Seen box was just ticked must leave the list at once. Stores other than a
 * board or a board view keep their optimistic update only.
 */
export const useRefetchWorkItems = () => {
  const { workspaceSlug, projectId, viewId } = useParams();
  const storeType = useIssueStoreType();
  const { issues: projectIssues } = useIssues(EIssuesStoreType.PROJECT);
  const { issues: viewIssues } = useIssues(EIssuesStoreType.PROJECT_VIEW);

  return useCallback(async () => {
    if (!workspaceSlug || !projectId) return;
    const slug = workspaceSlug.toString();
    const project = projectId.toString();
    if (storeType === EIssuesStoreType.PROJECT_VIEW && viewId) {
      await viewIssues.fetchIssuesWithExistingPagination(slug, project, viewId.toString(), "mutation");
    } else if (storeType === EIssuesStoreType.PROJECT) {
      await projectIssues.fetchIssuesWithExistingPagination(slug, project, "mutation");
    }
  }, [workspaceSlug, projectId, viewId, storeType, projectIssues, viewIssues]);
};
