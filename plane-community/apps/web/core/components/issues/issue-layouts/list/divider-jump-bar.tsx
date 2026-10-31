/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import type { TIssue, TIssueMap } from "@plane/types";
import { cn } from "@plane/utils";
import { HIGHLIGHT_CLASS, getIssueBlockId } from "../utils";
import { isBlankName } from "../row-line-tools";

type Props = {
  issueIds: string[];
  issuesMap: TIssueMap;
  groupId: string;
};

const HIGHLIGHT_MS = 1500;
/** Rows above the target render as they come into view and may change height: one quiet re-scroll. */
const SETTLE_MS = 400;

/**
 * Bookmarks for a list: one chip per divider that has text, in list order. A tap scrolls the list to
 * that divider and lights it up for a moment. Shown only when the list has such a divider. Sticks
 * under the group header while the list scrolls.
 */
export const DividerJumpBar = observer(function DividerJumpBar(props: Props) {
  const { issueIds, issuesMap, groupId } = props;
  const barRef = useRef<HTMLDivElement | null>(null);
  const [stickyTop, setStickyTop] = useState(0);

  const bookmarks = issueIds
    .map((id) => issuesMap[id])
    .filter((issue): issue is TIssue => !!issue && !!issue.is_divider && !isBlankName(issue.name) && !issue.tempId);
  const hasBookmarks = bookmarks.length > 0;

  // Sit under the group's sticky header (the list's own header row), when there is one.
  useEffect(() => {
    const bar = barRef.current;
    const header = bar?.parentElement?.parentElement?.previousElementSibling as HTMLElement | null | undefined;
    if (!bar || !header) return;
    const measure = () =>
      setStickyTop(window.getComputedStyle(header).position === "sticky" ? header.offsetHeight : 0);
    measure();
    const resizeObserver = new ResizeObserver(measure);
    resizeObserver.observe(header);
    return () => resizeObserver.disconnect();
  }, [hasBookmarks]);

  if (!hasBookmarks) return null;

  const jumpTo = (issueId: string) => {
    const element = document.getElementById(getIssueBlockId(issueId, groupId));
    if (!element) return;
    const offset = stickyTop + (barRef.current?.offsetHeight ?? 0);
    const scrollToRow = (behavior: ScrollBehavior) => {
      element.style.scrollMarginTop = `${offset}px`;
      element.scrollIntoView({ block: "start", behavior });
    };
    scrollToRow("smooth");
    setTimeout(() => scrollToRow("auto"), SETTLE_MS);
    element.classList.add(HIGHLIGHT_CLASS);
    setTimeout(() => element.classList.remove(HIGHLIGHT_CLASS), HIGHLIGHT_MS);
  };

  return (
    <div
      ref={barRef}
      className="sticky z-[1] w-full border-b border-subtle bg-surface-1"
      style={{ top: stickyTop }}
      role="navigation"
      aria-label="Jump to a section"
    >
      <div className="flex w-full items-center gap-1.5 overflow-x-auto px-3 py-1.5 [scrollbar-width:none]">
        {bookmarks.map((issue) => (
          <button
            key={issue.id}
            type="button"
            className={cn(
              "max-w-48 flex-shrink-0 truncate rounded-full border border-subtle bg-layer-1 px-2.5 py-1 text-11 font-medium text-secondary",
              "hover:bg-layer-1-hover hover:text-primary [@media(hover:none)]:min-h-8"
            )}
            title={issue.name}
            onClick={() => jumpTo(issue.id)}
          >
            {issue.name}
          </button>
        ))}
      </div>
    </div>
  );
});
