/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { EIssuesStoreType } from "@plane/types";
import type { TIssue } from "@plane/types";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useIssues } from "@/hooks/store/use-issues";
// services
import { IssueService } from "@/services/issue";
import { issueTemplateService } from "@/services/issue/issue_template.service";

const issueService = new IssueService();

export const issueTemplatesKey = (projectId: string | undefined) =>
  projectId ? `PROJECT_WORK_ITEM_TEMPLATES_${projectId}` : null;

/** The board's templates. Refetch with ``refresh()`` after a change. */
export const useIssueTemplates = (workspaceSlug: string | undefined, projectId: string | undefined) => {
  const key = workspaceSlug ? issueTemplatesKey(projectId) : null;
  const { data, isLoading, mutate } = useSWR(
    key,
    () => issueTemplateService.list(workspaceSlug as string, projectId as string),
    { revalidateOnFocus: false }
  );
  return { templates: data ?? [], isLoading, refresh: () => mutate() };
};

export const refreshIssueTemplates = (projectId: string) => globalMutate(issueTemplatesKey(projectId));

/**
 * Create a card from a template, put it on the board, and open it.
 * The card is made on the server through the normal create path.
 */
export const useCreateFromTemplate = () => {
  const {
    issues: { addIssue },
  } = useIssues(EIssuesStoreType.PROJECT) as unknown as {
    issues: { addIssue: (issue: TIssue, shouldUpdateList?: boolean) => void };
  };
  const { setPeekIssue } = useIssueDetail();

  return useCallback(
    async (workspaceSlug: string, projectId: string, templateId: string, name?: string) => {
      const result = await issueTemplateService.use(workspaceSlug, projectId, templateId, name);
      const [issue] = await issueService.retrieveIssues(workspaceSlug, projectId, [result.id]);
      if (issue) addIssue(issue, true);
      setPeekIssue({ workspaceSlug, projectId, issueId: result.id });
      return result;
    },
    [addIssue, setPeekIssue]
  );
};
