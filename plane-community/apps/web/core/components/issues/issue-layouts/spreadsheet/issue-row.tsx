/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { Dispatch, MouseEvent, MutableRefObject, SetStateAction } from "react";
import { useRef, useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { MoreHorizontal } from "lucide-react";
import { SPREADSHEET_SELECT_GROUP } from "@plane/constants";
// plane helpers
import { useOutsideClickDetector } from "@plane/hooks";
import { ChevronRightIcon } from "@plane/propel/icons";
// types
import { Tooltip } from "@plane/propel/tooltip";
import type { IIssueDisplayProperties, TIssue } from "@plane/types";
import { EIssueServiceType } from "@plane/types";
// ui
import { ControlLink, Row } from "@plane/ui";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { cn, createIssuePayload, generateWorkItemLink } from "@plane/utils";
// components
import { MultipleSelectEntityAction } from "@/components/core/multiple-select";
import RenderIfVisible from "@/components/core/render-if-visible-HOC";
import { IssueIdentifier } from "@/components/issues/issue-detail/issue-identifier";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useIssues } from "@/hooks/store/use-issues";
import { useProject } from "@/hooks/store/use-project";
import useIssuePeekOverviewRedirection from "@/hooks/use-issue-peek-overview-redirection";
import type { TSelectionHelper } from "@/hooks/use-multiple-select";
import { usePlatformOS } from "@/hooks/use-platform-os";
// local components
import type { TRenderQuickActions } from "../list/list-view-types";
import { buildInlineAddData } from "../quick-add/inline-row";
import type { TRowAddPlacement } from "../row-add-button";
import { RowAddButton } from "../row-add-button";
import type { TRowAddKind, TRowInlineAdd } from "../row-line-tools";
import { InlineRowTitle, RowLineMenu, blankRowFields, isBlankName, requestRowTitleFocus } from "../row-line-tools";
import { isIssueNew } from "../utils";
import { CustomFieldCells, SeenCell } from "@/components/custom-fields/spreadsheet-columns";
import { IssueColumn } from "./issue-column";
// card shortcuts: a shortcut card shows its target's live title
import { ShortcutAwareTitle, shortcutAwareName } from "@/components/card-links/shortcut-title";

interface Props {
  displayProperties: IIssueDisplayProperties;
  isEstimateEnabled: boolean;
  quickActions: TRenderQuickActions;
  canEditProperties: (projectId: string | undefined) => boolean;
  updateIssue: ((projectId: string | null, issueId: string, data: Partial<TIssue>) => Promise<void>) | undefined;
  portalElement: React.MutableRefObject<HTMLDivElement | null>;
  nestingLevel: number;
  issueId: string;
  isScrolled: MutableRefObject<boolean>;
  containerRef: MutableRefObject<HTMLTableElement | null>;
  spreadsheetColumnsList: (keyof IIssueDisplayProperties)[];
  spacingLeft?: number;
  selectionHelpers: TSelectionHelper;
  shouldRenderByDefault?: boolean;
  isEpic?: boolean;
  /** When set, the row gets a + that adds a card right above or below it (top-level rows only). */
  quickAddCallback?: (projectId: string | null | undefined, data: TIssue) => Promise<TIssue | undefined>;
  /** The ids of the table's rows, in order: the new card's sort_order lands between neighbours. */
  siblingIds?: string[];
}

export const SpreadsheetIssueRow = observer(function SpreadsheetIssueRow(props: Props) {
  const {
    displayProperties,
    issueId,
    isEstimateEnabled,
    nestingLevel,
    portalElement,
    updateIssue,
    quickActions,
    canEditProperties,
    isScrolled,
    containerRef,
    spreadsheetColumnsList,
    spacingLeft = 6,
    selectionHelpers,
    shouldRenderByDefault,
    isEpic = false,
    quickAddCallback,
    siblingIds,
  } = props;
  // states
  const [isExpanded, setExpanded] = useState<boolean>(false);
  // router
  const { projectId: routerProjectId } = useParams();
  // store hooks
  const { subIssues: subIssuesStore } = useIssueDetail(isEpic ? EIssueServiceType.EPICS : EIssueServiceType.ISSUES);
  const { issueMap } = useIssues();

  // derived values
  const issue = issueMap[issueId];
  const subIssues = subIssuesStore.subIssuesByIssueId(issueId);
  const isIssueSelected = selectionHelpers.getIsEntitySelected(issueId);
  const isIssueActive = selectionHelpers.getIsEntityActive(issueId);

  if (!issue) return null;

  // The + adds to the board in the URL, so it needs one, and the row must belong to it.
  const canInlineAdd =
    !!quickAddCallback &&
    !!siblingIds &&
    nestingLevel === 0 &&
    !!routerProjectId &&
    issue.project_id === routerProjectId.toString() &&
    canEditProperties(routerProjectId.toString());

  // One click, one finished row: it is made at once, so the row looks like every other row and has its own +.
  // A blank line (or a divider) made at once next to this row; the cursor goes into its title.
  const handleInlineAdd = (placement: TRowAddPlacement, kind: TRowAddKind = "line") => {
    if (!siblingIds || !quickAddCallback || !routerProjectId) return;
    const data = buildInlineAddData(issue, placement, siblingIds, (id) => issueMap[id]);
    const projectId = routerProjectId.toString();
    quickAddCallback(projectId, { ...createIssuePayload(projectId, { ...data, ...blankRowFields(kind) }) } as TIssue)
      .then((created) => requestRowTitleFocus(created?.id))
      .catch((error: { message?: string }) =>
        setToast({ type: TOAST_TYPE.ERROR, title: "Could not add the line", message: error?.message ?? "Try again." })
      );
  };

  return (
    <>
      {/* first column/ issue name and key column */}
      <RenderIfVisible
        as="tr"
        root={containerRef}
        placeholderChildren={
          <td
            colSpan={100}
            className="border-[0.5px] border-transparent border-b-subtle-1"
            style={{ height: "calc(2.75rem - 1px)" }}
          />
        }
        classNames={cn("bg-surface-1 transition-[background-color]", {
          "group selected-issue-row": isIssueSelected,
          "border-[0.5px] border-strong-1": isIssueActive,
        })}
        verticalOffset={100}
        shouldRecordHeights={false}
        defaultValue={shouldRenderByDefault || isIssueNew(issue)}
      >
        <IssueRowDetails
          issueId={issueId}
          displayProperties={displayProperties}
          quickActions={quickActions}
          canEditProperties={canEditProperties}
          nestingLevel={nestingLevel}
          spacingLeft={spacingLeft}
          isEstimateEnabled={isEstimateEnabled}
          updateIssue={updateIssue}
          portalElement={portalElement}
          isScrolled={isScrolled}
          isExpanded={isExpanded}
          setExpanded={setExpanded}
          spreadsheetColumnsList={spreadsheetColumnsList}
          selectionHelpers={selectionHelpers}
          isEpic={isEpic}
          hasAddColumn={!!quickAddCallback}
          onInlineAdd={canInlineAdd ? handleInlineAdd : undefined}
        />
      </RenderIfVisible>

      {isExpanded &&
        !isEpic &&
        subIssues?.map((subIssueId: string) => (
          <SpreadsheetIssueRow
            key={subIssueId}
            issueId={subIssueId}
            displayProperties={displayProperties}
            quickActions={quickActions}
            canEditProperties={canEditProperties}
            nestingLevel={nestingLevel + 1}
            spacingLeft={spacingLeft + 12}
            isEstimateEnabled={isEstimateEnabled}
            updateIssue={updateIssue}
            portalElement={portalElement}
            isScrolled={isScrolled}
            containerRef={containerRef}
            spreadsheetColumnsList={spreadsheetColumnsList}
            selectionHelpers={selectionHelpers}
            shouldRenderByDefault={isExpanded}
            quickAddCallback={quickAddCallback}
          />
        ))}
    </>
  );
});

interface IssueRowDetailsProps {
  displayProperties: IIssueDisplayProperties;
  isEstimateEnabled: boolean;
  quickActions: TRenderQuickActions;
  canEditProperties: (projectId: string | undefined) => boolean;
  updateIssue: ((projectId: string | null, issueId: string, data: Partial<TIssue>) => Promise<void>) | undefined;
  portalElement: React.MutableRefObject<HTMLDivElement | null>;
  nestingLevel: number;
  issueId: string;
  isScrolled: MutableRefObject<boolean>;
  isExpanded: boolean;
  setExpanded: Dispatch<SetStateAction<boolean>>;
  spreadsheetColumnsList: (keyof IIssueDisplayProperties)[];
  spacingLeft?: number;
  selectionHelpers: TSelectionHelper;
  isEpic?: boolean;
  /** The table keeps a column for the + on every row, so sub-rows line up with their parent. */
  hasAddColumn?: boolean;
  /** Click adds a blank line below this row, Alt+click above; the line menu can add a divider. */
  onInlineAdd?: TRowInlineAdd;
}

const IssueRowDetails = observer(function IssueRowDetails(props: IssueRowDetailsProps) {
  const {
    displayProperties,
    issueId,
    isEstimateEnabled,
    nestingLevel,
    portalElement,
    updateIssue,
    quickActions,
    canEditProperties,
    isScrolled,
    isExpanded,
    setExpanded,
    spreadsheetColumnsList,
    spacingLeft = 6,
    selectionHelpers,
    isEpic = false,
    hasAddColumn = false,
    onInlineAdd,
  } = props;
  // states
  const [isMenuActive, setIsMenuActive] = useState(false);
  // refs
  const cellRef = useRef(null);
  const menuActionRef = useRef<HTMLDivElement | null>(null);
  // router
  const { workspaceSlug, projectId } = useParams();
  // hooks
  const { getProjectIdentifierById } = useProject();
  const { getIsIssuePeeked, peekIssue } = useIssueDetail(isEpic ? EIssueServiceType.EPICS : EIssueServiceType.ISSUES);
  const { handleRedirection } = useIssuePeekOverviewRedirection(isEpic);
  const { isMobile } = usePlatformOS();

  // handlers
  const handleIssuePeekOverview = (issue: TIssue) =>
    handleRedirection(workspaceSlug?.toString(), issue, isMobile, nestingLevel);

  const { subIssues: subIssuesStore, issue } = useIssueDetail();

  const issueDetail = issue.getIssueById(issueId);

  const subIssueIndentation = `${spacingLeft}px`;

  useOutsideClickDetector(menuActionRef, () => setIsMenuActive(false));

  const customActionButton = (
    <div
      ref={menuActionRef}
      className={`flex h-full w-full cursor-pointer items-center rounded-sm p-1 text-placeholder hover:bg-layer-1 ${
        isMenuActive ? "bg-layer-1 text-primary" : "text-secondary"
      }`}
      onClick={() => setIsMenuActive(!isMenuActive)}
    >
      <MoreHorizontal className="h-3.5 w-3.5" />
    </div>
  );
  if (!issueDetail) return null;

  const handleToggleExpand = (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    e.preventDefault();
    if (nestingLevel >= 3) {
      handleIssuePeekOverview(issueDetail);
    } else {
      setExpanded((prevState) => {
        if (!prevState && workspaceSlug && issueDetail && issueDetail.project_id)
          subIssuesStore.fetchSubIssues(workspaceSlug.toString(), issueDetail.project_id, issueDetail.id);
        return !prevState;
      });
    }
  };

  const disableUserActions = !canEditProperties(issueDetail.project_id ?? undefined);
  const subIssuesCount = issueDetail?.sub_issues_count ?? 0;
  const isIssueSelected = selectionHelpers.getIsEntitySelected(issueDetail.id);
  const projectIdentifier = getProjectIdentifierById(issueDetail.project_id);

  const canSelectIssues = !disableUserActions && !selectionHelpers.isSelectionDisabled;

  const workItemLink = generateWorkItemLink({
    workspaceSlug: workspaceSlug?.toString(),
    projectId: issueDetail?.project_id,
    issueId,
    projectIdentifier,
    sequenceId: issueDetail?.sequence_id,
    isEpic,
  });

  return (
    <>
      {/* Single sticky column containing both identifier and workitem */}
      <td
        id={`issue-${issueId}`}
        ref={cellRef}
        tabIndex={0}
        className="group/list-block relative left-0 z-10 max-w-lg bg-surface-1 md:sticky"
      >
        <ControlLink
          href={workItemLink}
          onClick={() => handleIssuePeekOverview(issueDetail)}
          className="outline-none"
          disabled={!!issueDetail?.tempId}
        >
          <Row
            className={cn(
              "group clickable z-10 flex h-11 w-full cursor-pointer items-center border-r-[0.5px] border-subtle-1 bg-transparent text-13 group-[.selected-issue-row]:bg-accent-primary/5 after:absolute group-[.selected-issue-row]:hover:bg-accent-primary/10",
              {
                "border-b-[0.5px]": !getIsIssuePeeked(issueDetail.id),
                "border border-accent-strong hover:border-accent-strong":
                  getIsIssuePeeked(issueDetail.id) && nestingLevel === peekIssue?.nestingLevel,
                "shadow-[8px_22px_22px_10px_rgba(0,0,0,0.05)]": isScrolled.current,
              }
            )}
          >
            {/* + : add a line below (Alt+click: above) */}
            {hasAddColumn && (
              <div className="mr-1 grid w-6 flex-shrink-0 place-items-center">
                {onInlineAdd && !issueDetail.tempId && <RowAddButton onAdd={onInlineAdd} />}
              </div>
            )}
            {/* Identifier section - conditionally rendered */}
            {displayProperties?.key && (
              <div className="flex h-full min-w-24 flex-shrink-0 items-center">
                <div className="relative flex cursor-pointer items-center text-11 hover:text-primary">
                  {issueDetail.project_id && (
                    <IssueIdentifier
                      issueId={issueDetail.id}
                      projectId={issueDetail.project_id}
                      size="xs"
                      variant="tertiary"
                      displayProperties={displayProperties}
                    />
                  )}
                </div>
              </div>
            )}

            {/* Workitem section */}
            <div
              className={cn("flex flex-grow items-center gap-0.5 py-2", {
                "min-w-[360px]": !displayProperties?.key,
                "min-w-60": displayProperties?.key,
              })}
            >
              {/* select checkbox */}
              {projectId && canSelectIssues && (
                <Tooltip
                  tooltipContent={
                    <>
                      Only work items within the current
                      <br />
                      project can be selected.
                    </>
                  }
                  disabled={issueDetail.project_id === projectId}
                >
                  <div className="absolute left-1 mr-1 grid w-3.5 flex-shrink-0 place-items-center">
                    <MultipleSelectEntityAction
                      className={cn(
                        "pointer-events-none opacity-0 transition-opacity group-hover/list-block:pointer-events-auto group-hover/list-block:opacity-100",
                        {
                          "pointer-events-auto opacity-100": isIssueSelected,
                        }
                      )}
                      groupId={SPREADSHEET_SELECT_GROUP}
                      id={issueDetail.id}
                      selectionHelpers={selectionHelpers}
                      disabled={issueDetail.project_id !== projectId}
                    />
                  </div>
                </Tooltip>
              )}

              {/* sub issues indentation */}
              {nestingLevel !== 0 && <div style={{ width: subIssueIndentation }} />}

              {/* sub-issues chevron */}
              <div className="grid size-4 place-items-center">
                {subIssuesCount > 0 && !isEpic && (
                  <button
                    type="button"
                    className="grid size-4 place-items-center rounded-xs text-placeholder hover:text-tertiary"
                    onClick={handleToggleExpand}
                  >
                    <ChevronRightIcon
                      className={cn("size-4", {
                        "rotate-90": isExpanded,
                      })}
                      strokeWidth={2.5}
                    />
                  </button>
                )}
              </div>

              <div className="my-auto flex h-full w-full items-center justify-between gap-2 truncate">
                <div className="line-clamp-1 w-full text-14 text-primary">
                  <div className="w-full overflow-hidden">
                    {issueDetail.is_divider || isBlankName(issueDetail.name) ? (
                      // blank lines and dividers: the title is typed in place
                      <div className="h-full w-full pr-4 text-left text-13 text-primary">
                        <InlineRowTitle
                          issue={issueDetail}
                          updateIssue={updateIssue}
                          isReadOnly={disableUserActions}
                          isDivider={!!issueDetail.is_divider}
                          className={cn({ "text-14 font-semibold": issueDetail.is_divider })}
                        />
                      </div>
                    ) : (
                      <Tooltip tooltipContent={shortcutAwareName(issueDetail.id, issueDetail.name)} isMobile={isMobile}>
                        <div
                          className="h-full w-full cursor-pointer truncate pr-4 text-left text-13 text-primary focus:outline-none"
                          tabIndex={-1}
                        >
                          <ShortcutAwareTitle
                            workspaceSlug={workspaceSlug?.toString()}
                            projectId={issueDetail.project_id}
                            issueId={issueDetail.id}
                            name={issueDetail.name}
                          />
                        </div>
                      </Tooltip>
                    )}
                  </div>
                </div>
                {!issueDetail.tempId && (
                  <RowLineMenu
                    issue={issueDetail}
                    onInlineAdd={onInlineAdd}
                    updateIssue={updateIssue}
                    isReadOnly={disableUserActions}
                  />
                )}
                <div
                  className={`opacity-0 transition-opacity group-hover:opacity-100 ${isMenuActive ? "!opacity-100" : ""}`}
                  onClick={(e) => e.stopPropagation()}
                >
                  {quickActions({
                    issue: issueDetail,
                    parentRef: cellRef,
                    customActionButton,
                    portalElement: portalElement.current,
                  })}
                </div>
              </div>
            </div>
          </Row>
        </ControlLink>
      </td>
      {/* Rest of the columns */}
      {spreadsheetColumnsList.map((property) => (
        <IssueColumn
          key={property}
          displayProperties={displayProperties}
          issueDetail={issueDetail}
          disableUserActions={disableUserActions}
          property={property}
          updateIssue={updateIssue}
          isEstimateEnabled={isEstimateEnabled}
        />
      ))}
      {!isEpic && (
        <>
          <CustomFieldCells
            displayProperties={displayProperties}
            issueDetail={issueDetail}
            disableUserActions={disableUserActions}
            updateIssue={updateIssue}
          />
          {/* task lists: the check mark at the right end of the row */}
          <SeenCell issueDetail={issueDetail} disableUserActions={disableUserActions} updateIssue={updateIssue} />
        </>
      )}
    </>
  );
});
