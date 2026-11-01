/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRouter } from "next/navigation";
// types
import type { TIssue } from "@plane/types";
import { EIssueServiceType } from "@plane/types";
// helpers
import { generateWorkItemLink } from "@plane/utils";
// one-unit screens: a card opens as a full page unless the person chose the side peek
import { getCardOpenMode } from "@/components/one-unit/card-open-mode";
// card shortcuts: opening a shortcut card opens the card it points to
import { getShortcutTarget, linkedCardHref } from "@/components/card-links/store";
// hooks
import { useIssueDetail } from "./store/use-issue-detail";
import { useProject } from "./store/use-project";

const useIssuePeekOverviewRedirection = (isEpic: boolean = false) => {
  // router
  const router = useRouter();
  //   store hooks
  const { getIsIssuePeeked, setPeekIssue } = useIssueDetail(
    isEpic ? EIssueServiceType.EPICS : EIssueServiceType.ISSUES
  );
  const { getProjectIdentifierById } = useProject();

  const handleRedirection = (
    workspaceSlug: string | undefined,
    issue: TIssue | undefined,
    isMobile = false,
    nestingLevel?: number,
    // a page inside a parent page always opens in the side panel on a plain click
    forceMode?: "peek"
  ) => {
    if (!issue) return;
    const { project_id, id, archived_at, tempId } = issue;
    const projectIdentifier = getProjectIdentifierById(issue?.project_id);

    const workItemLink = generateWorkItemLink({
      workspaceSlug,
      projectId: project_id,
      issueId: id,
      projectIdentifier,
      sequenceId: issue?.sequence_id,
      isEpic,
      isArchived: !!archived_at,
    });
    if (workspaceSlug && project_id && id && !getIsIssuePeeked(id) && !tempId) {
      const shortcut = getShortcutTarget(id);
      if (shortcut) {
        // Visible target: go there. Hidden or removed: the shortcut's own page says so.
        router.push(shortcut.status === "visible" ? linkedCardHref(workspaceSlug, shortcut.card) : workItemLink);
        return;
      }
      // a phone-width screen always gets the full page, never the half-width panel
      const isNarrow = typeof window !== "undefined" && window.matchMedia("(max-width: 767px)").matches;
      if (isMobile || isNarrow || (forceMode !== "peek" && getCardOpenMode() === "page")) {
        router.push(workItemLink);
      } else {
        setPeekIssue({ workspaceSlug, projectId: project_id, issueId: id, nestingLevel, isArchived: !!archived_at });
      }
    }
  };

  return { handleRedirection };
};

export default useIssuePeekOverviewRedirection;
