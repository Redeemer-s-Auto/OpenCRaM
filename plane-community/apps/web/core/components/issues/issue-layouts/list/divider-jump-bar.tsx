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
/**
 * Rows render as they come into view and change height (placeholders are not the real height), so one
 * scroll is not enough: after the jump the divider's place is re-measured and the scroll corrected,
 * until it holds still at the top of the list for a few checks in a row.
 */
const CHECK_MS = 80;
const MAX_CHECKS = 60;
const STABLE_CHECKS = 5;

/** The element that scrolls the list (the nearest scrollable ancestor). */
const scrollParentOf = (element: HTMLElement | null): HTMLElement | null => {
  let node = element?.parentElement ?? null;
  while (node) {
    const overflowY = window.getComputedStyle(node).overflowY;
    if ((overflowY === "auto" || overflowY === "scroll") && node.scrollHeight > node.clientHeight) return node;
    node = node.parentElement;
  }
  return null;
};

/**
 * Bookmarks for a list: one chip per divider that has text, in list order. A tap scrolls the list to
 * that divider and lights it up for a moment. Shown only when the list has such a divider. Sticks
 * under the group header while the list scrolls.
 */
export const DividerJumpBar = observer(function DividerJumpBar(props: Props) {
  const { issueIds, issuesMap, groupId } = props;
  const barRef = useRef<HTMLDivElement | null>(null);
  const [stickyTop, setStickyTop] = useState(0);
  // the jump that is still settling; a new tap or the person scrolling ends it
  const stopJumpRef = useRef<(() => void) | null>(null);
  useEffect(() => () => stopJumpRef.current?.(), []);

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
    stopJumpRef.current?.();
    const blockId = getIssueBlockId(issueId, groupId);
    const element = document.getElementById(blockId);
    if (!element) return;
    const container = scrollParentOf(barRef.current);
    const offset = () => stickyTop + (barRef.current?.offsetHeight ?? 0);
    // how far the divider is from its place right under the bar (the row element may be re-created)
    const distance = () => {
      const target = document.getElementById(blockId);
      if (!target || !container) return 0;
      return target.getBoundingClientRect().top - (container.getBoundingClientRect().top + offset());
    };
    if (!container) {
      element.style.scrollMarginTop = `${offset()}px`;
      element.scrollIntoView({ block: "start" });
    } else {
      container.scrollTop += distance();
      let checks = 0;
      let stable = 0;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const stop = () => {
        if (timer) clearTimeout(timer);
        container.removeEventListener("wheel", stop);
        container.removeEventListener("touchstart", stop);
        window.removeEventListener("keydown", stop);
        if (stopJumpRef.current === stop) stopJumpRef.current = null;
      };
      const check = () => {
        const off = distance();
        if (Math.abs(off) > 1) {
          const before = container.scrollTop;
          container.scrollTop += off;
          // at the very end of the list it cannot go further: that is as close as it gets
          stable = container.scrollTop === before ? stable + 1 : 0;
        } else stable += 1;
        checks += 1;
        if (stable >= STABLE_CHECKS || checks >= MAX_CHECKS) stop();
        else timer = setTimeout(check, CHECK_MS);
      };
      container.addEventListener("wheel", stop, { passive: true });
      container.addEventListener("touchstart", stop, { passive: true });
      window.addEventListener("keydown", stop);
      stopJumpRef.current = stop;
      timer = setTimeout(check, CHECK_MS);
    }
    element.classList.add(HIGHLIGHT_CLASS);
    setTimeout(() => document.getElementById(blockId)?.classList.remove(HIGHLIGHT_CLASS), HIGHLIGHT_MS);
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
