/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { MutableRefObject } from "react";
import { useCallback, useRef } from "react";
// components
import type { TIssue, IIssueDisplayProperties, TIssueMap, TGroupedIssues } from "@plane/types";
// hooks
import type { TSelectionHelper } from "@/hooks/use-multiple-select";
// types
import { IssueBlockRoot } from "./block-root";
import { DividerJumpBar } from "./divider-jump-bar";
import type { TRenderQuickActions } from "./list-view-types";

interface Props {
  issueIds: TGroupedIssues | any;
  issuesMap: TIssueMap;
  groupId: string;
  canEditProperties: (projectId: string | undefined) => boolean;
  updateIssue: ((projectId: string | null, issueId: string, data: Partial<TIssue>) => Promise<void>) | undefined;
  quickActions: TRenderQuickActions;
  displayProperties: IIssueDisplayProperties | undefined;
  containerRef: MutableRefObject<HTMLDivElement | null>;
  isDragAllowed: boolean;
  canDropOverIssue: boolean;
  selectionHelpers: TSelectionHelper;
  isEpic?: boolean;
  /** When set, every row gets a + that adds a card right above or below it. */
  quickAddCallback?: (projectId: string | null | undefined, data: TIssue) => Promise<TIssue | undefined>;
  groupQuickAddData?: Partial<TIssue>;
}

export function IssueBlocksList(props: Props) {
  const {
    issueIds,
    issuesMap,
    groupId,
    updateIssue,
    quickActions,
    displayProperties,
    canEditProperties,
    containerRef,
    selectionHelpers,
    isDragAllowed,
    canDropOverIssue,
    isEpic = false,
    quickAddCallback,
    groupQuickAddData,
  } = props;
  // Rows read the current ids on click; the getter never changes, so a new ids array re-renders no row.
  const issueIdsRef = useRef(issueIds);
  issueIdsRef.current = issueIds;
  const getSiblingIds = useCallback(() => issueIdsRef.current ?? [], []);

  return (
    <div className="relative h-full w-full">
      {/* bookmarks: one chip per named divider, tap to jump there */}
      {Array.isArray(issueIds) && issueIds.length > 0 && (
        <DividerJumpBar issueIds={issueIds} issuesMap={issuesMap} groupId={groupId} />
      )}
      {issueIds &&
        issueIds.length > 0 &&
        issueIds.map((issueId: string, index: number) => (
          <IssueBlockRoot
            key={issueId}
            issueId={issueId}
            issuesMap={issuesMap}
            updateIssue={updateIssue}
            quickActions={quickActions}
            canEditProperties={canEditProperties}
            displayProperties={displayProperties}
            nestingLevel={0}
            spacingLeft={0}
            containerRef={containerRef}
            selectionHelpers={selectionHelpers}
            groupId={groupId}
            isLastChild={index === issueIds.length - 1}
            isDragAllowed={isDragAllowed}
            canDropOverIssue={canDropOverIssue}
            isEpic={isEpic}
            quickAddCallback={quickAddCallback}
            groupQuickAddData={groupQuickAddData}
            getSiblingIds={getSiblingIds}
          />
        ))}
    </div>
  );
}
