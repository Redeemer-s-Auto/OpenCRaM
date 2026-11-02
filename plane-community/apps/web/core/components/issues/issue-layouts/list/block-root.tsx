/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { MutableRefObject } from "react";
import React, { useEffect, useRef, useState } from "react";
import { combine } from "@atlaskit/pragmatic-drag-and-drop/combine";
import { dropTargetForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { attachInstruction } from "@atlaskit/pragmatic-drag-and-drop-hitbox/tree-item";
import { attachClosestEdge, extractClosestEdge } from "@atlaskit/pragmatic-drag-and-drop-hitbox/closest-edge";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// plane helpers
import { useOutsideClickDetector } from "@plane/hooks";
// types
import type { IIssueDisplayProperties, TIssue, TIssueMap } from "@plane/types";
import { EIssueServiceType } from "@plane/types";
// components
import { DropIndicator } from "@plane/ui";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { createIssuePayload } from "@plane/utils";
import RenderIfVisible from "@/components/core/render-if-visible-HOC";
import { ListLoaderItemRow } from "@/components/ui/loader/layouts/list-layout-loader";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import type { TSelectionHelper } from "@/hooks/use-multiple-select";
import { usePlatformOS } from "@/hooks/use-platform-os";
// types
import { buildInlineAddData, spreadSortOrderTies } from "../quick-add/inline-row";
import type { TRowAddPlacement } from "../row-add-button";
import type { TRowAddKind } from "../row-line-tools";
import { blankRowFields, requestRowTitleFocus } from "../row-line-tools";
import { HIGHLIGHT_CLASS, getIssueBlockId, isIssueNew } from "../utils";
import { IssueBlock } from "./block";
import type { TRenderQuickActions } from "./list-view-types";

type Props = {
  issueId: string;
  issuesMap: TIssueMap;
  updateIssue: ((projectId: string | null, issueId: string, data: Partial<TIssue>) => Promise<void>) | undefined;
  quickActions: TRenderQuickActions;
  canEditProperties: (projectId: string | undefined) => boolean;
  displayProperties: IIssueDisplayProperties | undefined;
  nestingLevel: number;
  spacingLeft?: number;
  containerRef: MutableRefObject<HTMLDivElement | null>;
  selectionHelpers: TSelectionHelper;
  groupId: string;
  isDragAllowed: boolean;
  canDropOverIssue: boolean;
  isParentIssueBeingDragged?: boolean;
  isLastChild?: boolean;
  shouldRenderByDefault?: boolean;
  isEpic?: boolean;
  /** When set, the row gets a + that adds a card right above or below it (top-level rows only). */
  quickAddCallback?: (projectId: string | null | undefined, data: TIssue) => Promise<TIssue | undefined>;
  groupQuickAddData?: Partial<TIssue>;
  /** The ids of the list this row is in, in order: the new card's sort_order lands between neighbours. */
  siblingIds?: string[];
};

export const IssueBlockRoot = observer(function IssueBlockRoot(props: Props) {
  const {
    issueId,
    issuesMap,
    groupId,
    updateIssue,
    quickActions,
    canEditProperties,
    displayProperties,
    nestingLevel,
    spacingLeft = 14,
    containerRef,
    isDragAllowed,
    canDropOverIssue,
    isParentIssueBeingDragged = false,
    isLastChild = false,
    selectionHelpers,
    shouldRenderByDefault,
    isEpic = false,
    quickAddCallback,
    groupQuickAddData,
    siblingIds,
  } = props;
  // states
  const [isExpanded, setExpanded] = useState<boolean>(false);
  const [instruction, setInstruction] = useState<"DRAG_OVER" | "DRAG_BELOW" | undefined>(undefined);
  const [isCurrentBlockDragging, setIsCurrentBlockDragging] = useState(false);
  // ref
  const issueBlockRef = useRef<HTMLDivElement | null>(null);
  // router
  const { projectId: routerProjectId } = useParams();
  // hooks
  const { isMobile } = usePlatformOS();
  // store hooks
  const { subIssues: subIssuesStore } = useIssueDetail(isEpic ? EIssueServiceType.EPICS : EIssueServiceType.ISSUES);

  const isSubIssue = nestingLevel !== 0;
  // The + adds to the board in the URL, so it needs one, and the row must belong to it.
  const canInlineAdd =
    !!quickAddCallback &&
    !!siblingIds &&
    !isSubIssue &&
    !!routerProjectId &&
    issuesMap[issueId]?.project_id === routerProjectId.toString() &&
    canEditProperties(routerProjectId.toString());

  // One click, one finished row: a blank line (or a divider) made at once, right next to this row,
  // with its own +. The cursor goes into its title so it can be typed straight away.
  const handleInlineAdd = async (placement: TRowAddPlacement, kind: TRowAddKind = "line") => {
    const issue = issuesMap[issueId];
    if (!issue || !siblingIds || !quickAddCallback || !routerProjectId) return;
    const projectId = routerProjectId.toString();
    // rows sharing one sort_order leave no room between them: spread them first (Notes)
    if (updateIssue)
      await spreadSortOrderTies(issue, placement, siblingIds, (id) => issuesMap[id], (id, sort_order) =>
        updateIssue(issuesMap[id]?.project_id ?? projectId, id, { sort_order })
      ).catch(() => 0);
    const data = buildInlineAddData(issue, placement, siblingIds, (id) => issuesMap[id], groupQuickAddData);
    quickAddCallback(projectId, { ...createIssuePayload(projectId, { ...data, ...blankRowFields(kind) }) } as TIssue)
      .then((created) => requestRowTitleFocus(created?.id))
      .catch((error: { message?: string }) =>
        setToast({ type: TOAST_TYPE.ERROR, title: "Could not add the line", message: error?.message ?? "Try again." })
      );
  };

  useEffect(() => {
    const blockElement = issueBlockRef.current;

    if (!blockElement) return;

    return combine(
      dropTargetForElements({
        element: blockElement,
        canDrop: ({ source }) => source?.data?.id !== issueId && !isSubIssue && canDropOverIssue,
        getData: ({ input, element }) => {
          const data = { id: issueId, type: "ISSUE" };

          // attach instruction for last in list
          const withInstruction = attachInstruction(data, {
            input,
            element,
            currentLevel: 0,
            indentPerLevel: 0,
            mode: isLastChild ? "last-in-group" : "standard",
          });
          // Notes (Notion style): the line goes to the row edge nearest the pointer (top half: above
          // this row, bottom half: below it), and the card lands exactly there (utils: dropAfter).
          return attachClosestEdge(withInstruction, { input, element, allowedEdges: ["top", "bottom"] });
        },
        onDrag: ({ self }) => {
          const edge = extractClosestEdge(self?.data);
          setInstruction(edge === "bottom" ? "DRAG_BELOW" : edge === "top" ? "DRAG_OVER" : undefined);
        },
        onDragLeave: () => {
          setInstruction(undefined);
        },
        onDrop: () => {
          setInstruction(undefined);
        },
      })
    );
  }, [issueId, isLastChild, issueBlockRef, isSubIssue, canDropOverIssue, setInstruction]);

  useOutsideClickDetector(issueBlockRef, () => {
    issueBlockRef?.current?.classList?.remove(HIGHLIGHT_CLASS);
  });

  if (!issueId || !issuesMap[issueId]?.created_at) return null;

  const subIssues = subIssuesStore.subIssuesByIssueId(issueId);
  return (
    <div className="relative" ref={issueBlockRef} id={getIssueBlockId(issueId, groupId)}>
      <DropIndicator classNames={"absolute top-0 z-[2]"} isVisible={instruction === "DRAG_OVER"} />
      <RenderIfVisible
        key={`${issueId}`}
        root={containerRef}
        classNames={`relative ${isLastChild && !isExpanded ? "" : "border-b border-b-subtle"}`}
        verticalOffset={100}
        defaultValue={shouldRenderByDefault || (issuesMap[issueId] ? isIssueNew(issuesMap[issueId]) : false)}
        placeholderChildren={<ListLoaderItemRow shouldAnimate={false} renderForPlaceHolder defaultPropertyCount={4} />}
        shouldRecordHeights={isMobile}
      >
        <IssueBlock
          issueId={issueId}
          issuesMap={issuesMap}
          groupId={groupId}
          updateIssue={updateIssue}
          quickActions={quickActions}
          canEditProperties={canEditProperties}
          displayProperties={displayProperties}
          isExpanded={isExpanded}
          setExpanded={setExpanded}
          nestingLevel={nestingLevel}
          spacingLeft={spacingLeft}
          selectionHelpers={selectionHelpers}
          canDrag={!isSubIssue && isDragAllowed}
          isCurrentBlockDragging={isParentIssueBeingDragged || isCurrentBlockDragging}
          setIsCurrentBlockDragging={setIsCurrentBlockDragging}
          isEpic={isEpic}
          hasAddColumn={!!quickAddCallback}
          onInlineAdd={canInlineAdd ? handleInlineAdd : undefined}
        />
      </RenderIfVisible>

      {isExpanded &&
        !isEpic &&
        subIssues?.map((subIssueId) => (
          <IssueBlockRoot
            key={`${subIssueId}`}
            issueId={subIssueId}
            issuesMap={issuesMap}
            updateIssue={updateIssue}
            quickActions={quickActions}
            canEditProperties={canEditProperties}
            displayProperties={displayProperties}
            nestingLevel={nestingLevel + 1}
            spacingLeft={spacingLeft + 12}
            containerRef={containerRef}
            selectionHelpers={selectionHelpers}
            groupId={groupId}
            isDragAllowed={isDragAllowed}
            canDropOverIssue={canDropOverIssue}
            isParentIssueBeingDragged={isParentIssueBeingDragged || isCurrentBlockDragging}
            shouldRenderByDefault={isExpanded}
            quickAddCallback={quickAddCallback}
          />
        ))}
      <DropIndicator classNames={"absolute bottom-0 z-[2]"} isVisible={instruction === "DRAG_BELOW"} />
    </div>
  );
});
