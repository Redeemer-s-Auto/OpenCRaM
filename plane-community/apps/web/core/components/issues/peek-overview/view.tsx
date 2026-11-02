/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import { createPortal } from "react-dom";
// plane imports
import type { EditorRefApi } from "@plane/editor";
import type { TNameDescriptionLoader } from "@plane/types";
import { EIssueServiceType } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import useKeypress from "@/hooks/use-keypress";
import usePeekOverviewOutsideClickDetector from "@/hooks/use-peek-overview-outside-click";
// local imports
import type { TIssueOperations } from "../issue-detail";
import { IssueActivity } from "../issue-detail/issue-activity";
import { IssueDetailWidgets } from "../issue-detail-widgets";
import { IssuePeekOverviewError } from "./error";
import type { TPeekModes } from "./header";
import { IssuePeekOverviewHeader } from "./header";
import { PeekOverviewIssueDetails } from "./issue-detail";
import { IssuePeekOverviewLoader } from "./loader";
import { PeekOverviewProperties } from "./properties";

interface IIssueView {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  isLoading?: boolean;
  isError?: boolean;
  is_archived: boolean;
  disabled?: boolean;
  embedIssue?: boolean;
  embedRemoveCurrentNotification?: () => void;
  issueOperations: TIssueOperations;
}

export const IssueView = observer(function IssueView(props: IIssueView) {
  const {
    workspaceSlug,
    projectId,
    issueId,
    isLoading,
    isError,
    is_archived,
    disabled = false,
    embedIssue = false,
    embedRemoveCurrentNotification,
    issueOperations,
  } = props;
  // states
  const [peekMode, setPeekMode] = useState<TPeekModes>("side-peek");
  const [isSubmitting, setIsSubmitting] = useState<TNameDescriptionLoader>("saved");
  const [isDeleteIssueModalOpen, setIsDeleteIssueModalOpen] = useState(false);
  const [isArchiveIssueModalOpen, setIsArchiveIssueModalOpen] = useState(false);
  const [isDuplicateIssueModalOpen, setIsDuplicateIssueModalOpen] = useState(false);
  const [isEditIssueModalOpen, setIsEditIssueModalOpen] = useState(false);
  // Notes: the side panel can be dragged wider or narrower by its left edge (not remembered)
  const [sideWidth, setSideWidth] = useState<number | null>(null);
  // ref
  const issuePeekOverviewRef = useRef<HTMLDivElement>(null);
  const editorRef = useRef<EditorRefApi>(null);
  // store hooks
  const {
    setPeekIssue,
    isAnyModalOpen,
    issue: { getIssueById },
  } = useIssueDetail();
  const { isAnyModalOpen: isAnyEpicModalOpen } = useIssueDetail(EIssueServiceType.EPICS);
  const issue = getIssueById(issueId);
  // remove peek id
  const removeRoutePeekId = () => {
    setPeekIssue(undefined);
    if (embedIssue && embedRemoveCurrentNotification) embedRemoveCurrentNotification();
  };

  const toggleDeleteIssueModal = (value: boolean) => setIsDeleteIssueModalOpen(value);
  const toggleArchiveIssueModal = (value: boolean) => setIsArchiveIssueModalOpen(value);
  const toggleDuplicateIssueModal = (value: boolean) => setIsDuplicateIssueModalOpen(value);
  const toggleEditIssueModal = (value: boolean) => setIsEditIssueModalOpen(value);

  const isAnyLocalModalOpen =
    isDeleteIssueModalOpen || isArchiveIssueModalOpen || isDuplicateIssueModalOpen || isEditIssueModalOpen;

  usePeekOverviewOutsideClickDetector(
    issuePeekOverviewRef,
    () => {
      const isAnyDropbarOpen = editorRef.current?.isAnyDropbarOpen();
      if (!embedIssue) {
        if (!isAnyModalOpen && !isAnyEpicModalOpen && !isAnyLocalModalOpen && !isAnyDropbarOpen) {
          removeRoutePeekId();
        }
      }
    },
    issueId,
    ["main-sidebar"]
  );

  const handleKeyDown = () => {
    const editorImageFullScreenModalElement = document.querySelector(".editor-image-full-screen-modal");
    const dropdownElement = document.activeElement?.tagName === "INPUT";
    const isAnyDropbarOpen = editorRef.current?.isAnyDropbarOpen();
    if (!isAnyModalOpen && !dropdownElement && !isAnyDropbarOpen && !editorImageFullScreenModalElement) {
      removeRoutePeekId();
      const issueElement = document.getElementById(`issue-${issueId}`);
      if (issueElement) issueElement?.focus();
    }
  };

  useKeypress("Escape", () => !embedIssue && handleKeyDown());

  // Notes: Up / Down move the panel to the previous / next row of the list behind it.
  useEffect(() => {
    if (embedIssue) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true'], [role='listbox'], [role='menu']")) return;
      if (isAnyModalOpen || isAnyEpicModalOpen || isAnyLocalModalOpen) return;
      const ids: string[] = [];
      document.querySelectorAll<HTMLElement>("[id^='issue-']").forEach((element) => {
        const id = element.id.slice("issue-".length);
        // dividers (section headers, blank lines) are not cards: the panel skips them
        if (element.hasAttribute("data-divider-row") || getIssueById(id)?.is_divider) return;
        if (/^[0-9a-f-]{36}$/.test(id) && !ids.includes(id)) ids.push(id);
      });
      const index = ids.indexOf(issueId);
      if (index === -1) return;
      const nextId = ids[event.key === "ArrowDown" ? index + 1 : index - 1];
      const next = nextId ? getIssueById(nextId) : undefined;
      if (!next?.project_id) return;
      event.preventDefault();
      setPeekIssue({ workspaceSlug, projectId: next.project_id, issueId: next.id, isArchived: !!next.archived_at });
      document.getElementById(`issue-${next.id}`)?.scrollIntoView({ block: "nearest" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [
    embedIssue,
    issueId,
    workspaceSlug,
    isAnyModalOpen,
    isAnyEpicModalOpen,
    isAnyLocalModalOpen,
    getIssueById,
    setPeekIssue,
  ]);

  const startResize = (event: React.PointerEvent<HTMLDivElement>) => {
    const panel = issuePeekOverviewRef.current;
    if (!panel) return;
    event.preventDefault();
    event.stopPropagation();
    const right = panel.getBoundingClientRect().right;
    const onMove = (moveEvent: PointerEvent) => {
      const width = right - moveEvent.clientX;
      setSideWidth(Math.round(Math.min(Math.max(width, 360), right - 240)));
    };
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };
  const isWide = typeof window !== "undefined" && window.innerWidth >= 768;

  const handleRestore = async () => {
    if (!issueOperations.restore) return;
    await issueOperations.restore(workspaceSlug, projectId, issueId);
    removeRoutePeekId();
  };

  const peekOverviewIssueClassName = cn(
    !embedIssue
      ? "absolute z-[25] flex flex-col overflow-hidden rounded-sm border border-subtle bg-surface-1 transition-all duration-300"
      : `h-full w-full`,
    !embedIssue && {
      "top-0 right-0 bottom-0 w-full border-0 border-l md:w-[50%]": peekMode === "side-peek",
      "top-[8.33%] left-[8.33%] size-5/6": peekMode === "modal",
      "absolute inset-0 m-4": peekMode === "full-screen",
    }
  );

  const shouldUsePortal = !embedIssue;

  const portalContainer = document.getElementById("full-screen-portal") as HTMLElement;

  const content = (
    <div className="w-full text-body-sm-regular">
      {issueId && (
        <div
          ref={issuePeekOverviewRef}
          className={peekOverviewIssueClassName}
          data-peek-panel=""
          style={{
            ...(sideWidth && isWide && !embedIssue && peekMode === "side-peek" ? { width: sideWidth } : {}),
            boxShadow:
              "0px 4px 8px 0px rgba(0, 0, 0, 0.12), 0px 6px 12px 0px rgba(16, 24, 40, 0.12), 0px 1px 16px 0px rgba(16, 24, 40, 0.12)",
          }}
        >
          {!embedIssue && peekMode === "side-peek" && isWide && (
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Drag to resize the panel"
              onPointerDown={startResize}
              className="absolute top-0 bottom-0 left-0 z-10 w-1.5 cursor-col-resize hover:bg-accent-primary/30"
            />
          )}
          {isError ? (
            <div className="relative h-screen w-full overflow-hidden">
              <IssuePeekOverviewError removeRoutePeekId={removeRoutePeekId} />
            </div>
          ) : (
            isLoading && <IssuePeekOverviewLoader removeRoutePeekId={removeRoutePeekId} />
          )}
          {!isLoading && !isError && issue && (
            <>
              {/* header */}
              <IssuePeekOverviewHeader
                peekMode={peekMode}
                setPeekMode={(value) => setPeekMode(value)}
                removeRoutePeekId={removeRoutePeekId}
                toggleDeleteIssueModal={toggleDeleteIssueModal}
                toggleArchiveIssueModal={toggleArchiveIssueModal}
                toggleDuplicateIssueModal={toggleDuplicateIssueModal}
                toggleEditIssueModal={toggleEditIssueModal}
                handleRestoreIssue={handleRestore}
                isArchived={is_archived}
                issueId={issueId}
                workspaceSlug={workspaceSlug}
                projectId={projectId}
                isSubmitting={isSubmitting}
                disabled={disabled}
                embedIssue={embedIssue}
              />
              {/* content */}
              <div className="vertical-scrollbar relative scrollbar-md h-full w-full overflow-hidden overflow-y-auto">
                {["side-peek", "modal"].includes(peekMode) ? (
                  <div className="relative flex flex-col gap-3 space-y-3 px-4 py-5 md:px-8">
                    <PeekOverviewIssueDetails
                      editorRef={editorRef}
                      workspaceSlug={workspaceSlug}
                      projectId={projectId}
                      issueId={issueId}
                      issueOperations={issueOperations}
                      disabled={disabled}
                      isArchived={is_archived}
                      isSubmitting={isSubmitting}
                      setIsSubmitting={(value) => setIsSubmitting(value)}
                    />

                    <div className="py-2">
                      <IssueDetailWidgets
                        workspaceSlug={workspaceSlug}
                        projectId={projectId}
                        issueId={issueId}
                        disabled={disabled || is_archived}
                        issueServiceType={EIssueServiceType.ISSUES}
                      />
                    </div>

                    <PeekOverviewProperties
                      workspaceSlug={workspaceSlug}
                      projectId={projectId}
                      issueId={issueId}
                      issueOperations={issueOperations}
                      disabled={disabled || is_archived}
                    />

                    <IssueActivity
                      workspaceSlug={workspaceSlug}
                      projectId={projectId}
                      issueId={issueId}
                      disabled={is_archived}
                    />
                  </div>
                ) : (
                  <div className="vertical-scrollbar flex h-full w-full flex-col overflow-auto md:flex-row">
                    <div className="relative w-full space-y-6 p-4 py-5 md:h-full md:overflow-auto">
                      <div className="space-y-3">
                        <PeekOverviewIssueDetails
                          editorRef={editorRef}
                          workspaceSlug={workspaceSlug}
                          projectId={projectId}
                          issueId={issueId}
                          issueOperations={issueOperations}
                          disabled={disabled}
                          isArchived={is_archived}
                          isSubmitting={isSubmitting}
                          setIsSubmitting={(value) => setIsSubmitting(value)}
                        />

                        <div className="py-2">
                          <IssueDetailWidgets
                            workspaceSlug={workspaceSlug}
                            projectId={projectId}
                            issueId={issueId}
                            disabled={disabled}
                            issueServiceType={EIssueServiceType.ISSUES}
                          />
                        </div>

                        <IssueActivity
                          workspaceSlug={workspaceSlug}
                          projectId={projectId}
                          issueId={issueId}
                          disabled={is_archived}
                        />
                      </div>
                    </div>
                    <div
                      className={`vertical-scrollbar scrollbar-sm w-full flex-shrink-0 overflow-hidden border-t border-subtle p-4 py-5 md:h-full md:!w-[400px] md:border-t-0 md:border-l ${
                        is_archived ? "pointer-events-none" : ""
                      }`}
                    >
                      <PeekOverviewProperties
                        workspaceSlug={workspaceSlug}
                        projectId={projectId}
                        issueId={issueId}
                        issueOperations={issueOperations}
                        disabled={disabled || is_archived}
                      />
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );

  return <>{shouldUsePortal && portalContainer ? createPortal(content, portalContainer) : content}</>;
});
