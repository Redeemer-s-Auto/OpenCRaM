/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { KeyboardEvent, SyntheticEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import { ArrowDownToLine, ArrowUpToLine, Heading, ListPlus, ListTodo, SeparatorHorizontal } from "lucide-react";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TIssue } from "@plane/types";
import { CustomMenu } from "@plane/ui";
import { cn } from "@plane/utils";
import type { TRowAddPlacement } from "./row-add-button";

/** What a row's + or line menu makes: a blank task line, or a divider (section header). */
export type TRowAddKind = "line" | "divider";

export type TRowInlineAdd = (placement: TRowAddPlacement, kind?: TRowAddKind) => void;

type TUpdateIssue = ((projectId: string | null, issueId: string, data: Partial<TIssue>) => Promise<void>) | undefined;

/** A blank line or a blank divider: no visible name. */
export const isBlankName = (name: string | null | undefined) => !name || !name.trim();

/**
 * The fields a new blank line or divider is created with. The server accepts an empty name only
 * with blank_line (from the + or the line menu) or for a divider.
 */
export const blankRowFields = (kind: TRowAddKind = "line"): Partial<TIssue> =>
  kind === "divider" ? { name: "", is_divider: true } : { name: "", blank_line: true };

// --- focus the title of a row that was just made -------------------------------------------------

let pendingFocusId: string | null = null;
/** One focus callback per mounted row title, by card id: a request wakes only that row (no listener per row). */
const rowTitleFocusers = new Map<string, () => void>();

/**
 * Put the cursor in the title of a new row. The row may mount before or after the create call
 * answers, so the id is kept until that row's title takes it.
 */
export const requestRowTitleFocus = (issueId: string | undefined) => {
  if (!issueId || typeof window === "undefined") return;
  pendingFocusId = issueId;
  rowTitleFocusers.get(issueId)?.();
};

// --- inline title ---------------------------------------------------------------------------------

type TInlineRowTitleProps = {
  issue: TIssue;
  updateIssue: TUpdateIssue;
  isReadOnly: boolean;
  /** Dividers: bold section text; may be cleared to a thin spacer line. */
  isDivider?: boolean;
  className?: string;
};

/**
 * A row title typed in place (blank lines and dividers). Lives inside the row's link, so clicks stop
 * here. Enter or leaving the field saves; Escape puts the old text back. A task line cannot be
 * cleared from here (only blank lines start empty); a divider can.
 */
export const InlineRowTitle = observer(function InlineRowTitle(props: TInlineRowTitleProps) {
  const { issue, updateIssue, isReadOnly, isDivider = false, className } = props;
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [value, setValue] = useState(issue.name ?? "");
  const [isFocused, setIsFocused] = useState(false);

  useEffect(() => {
    if (!isFocused) setValue(issue.name ?? "");
  }, [issue.name, isFocused]);

  useEffect(() => {
    const focus = () => {
      pendingFocusId = null;
      inputRef.current?.focus();
    };
    if (pendingFocusId === issue.id) focus();
    rowTitleFocusers.set(issue.id, focus);
    return () => {
      if (rowTitleFocusers.get(issue.id) === focus) rowTitleFocusers.delete(issue.id);
    };
  }, [issue.id]);

  if (isReadOnly || !updateIssue || issue.tempId) {
    return (
      <span className={cn("block min-w-0 truncate", className)} aria-label={isBlankName(issue.name) ? "Blank line" : undefined}>
        {isBlankName(issue.name) ? " " : issue.name}
      </span>
    );
  }

  const save = () => {
    const next = value.trim();
    const current = (issue.name ?? "").trim();
    if (next === current || (!next && !isDivider)) {
      setValue(issue.name ?? "");
      return;
    }
    updateIssue(issue.project_id, issue.id, { name: next }).catch(() => {
      setValue(issue.name ?? "");
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not save the line", message: "Try again." });
    });
  };

  const stop = (e: SyntheticEvent) => e.stopPropagation();

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    e.stopPropagation();
    if (e.key === "Enter") {
      e.preventDefault();
      inputRef.current?.blur();
    } else if (e.key === "Escape") {
      e.preventDefault();
      setValue(issue.name ?? "");
      // leave the field without saving: the effect above restores the text once unfocused
      setTimeout(() => inputRef.current?.blur(), 0);
    }
  };

  const isBlankDivider = isDivider && isBlankName(value);

  return (
    <input
      ref={inputRef}
      type="text"
      value={value}
      maxLength={255}
      placeholder={isDivider ? "Section name" : "Type here"}
      aria-label={isDivider ? "Section name" : "Line text"}
      className={cn(
        "block w-full min-w-0 truncate border-none bg-transparent p-0 outline-none placeholder:text-placeholder focus:ring-0",
        {
          // a blank divider is a thin spacer: its placeholder shows only on hover or while typing
          "placeholder:opacity-0 group-hover/list-block:placeholder:opacity-100 focus:placeholder:opacity-100":
            isBlankDivider,
        },
        className
      )}
      onChange={(e) => setValue(e.target.value)}
      onFocus={() => setIsFocused(true)}
      onBlur={() => {
        setIsFocused(false);
        save();
      }}
      onKeyDown={handleKeyDown}
      onMouseDown={stop}
      onPointerDown={stop}
      onTouchStart={stop}
      onClick={(e) => {
        // inside the row link: keep the click here, so the card does not open
        e.stopPropagation();
        e.preventDefault();
      }}
      draggable={false}
    />
  );
});

// --- line menu ------------------------------------------------------------------------------------

type TRowLineMenuProps = {
  issue: TIssue;
  /** Adds a blank line or divider next to this row; absent when the row cannot add. */
  onInlineAdd?: TRowInlineAdd;
  updateIssue: TUpdateIssue;
  isReadOnly: boolean;
  className?: string;
};

/**
 * A small menu on every row for lines: add a blank line below or above (the phone's way to put a
 * line in the middle of a list), add a divider below, and turn the row into a divider or back.
 * Shown on hover with a mouse and always on a touch screen.
 */
export const RowLineMenu = observer(function RowLineMenu(props: TRowLineMenuProps) {
  const { issue, onInlineAdd, updateIssue, isReadOnly, className } = props;
  const canToggle = !isReadOnly && !!updateIssue;
  if (!onInlineAdd && !canToggle) return null;

  const toggleDivider = () => {
    if (!updateIssue) return;
    updateIssue(issue.project_id, issue.id, { is_divider: !issue.is_divider }).catch(() =>
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not change the line", message: "Try again." })
    );
  };

  return (
    // oxlint-disable-next-line jsx_a11y/click-events-have-key-events oxlint-disable-next-line jsx_a11y/no-static-element-interactions
    <div
      className={cn(
        "flex flex-shrink-0 items-center opacity-0 transition-opacity group-hover/list-block:opacity-100 focus-within:opacity-100 [@media(hover:none)]:opacity-100",
        className
      )}
      onClick={(e) => {
        e.stopPropagation();
        e.preventDefault();
      }}
    >
      <CustomMenu
        customButton={
          <span
            className={cn(
              "relative grid size-6 place-items-center rounded-sm text-placeholder hover:bg-layer-transparent-hover hover:text-tertiary",
              // a 44px touch target on a phone, without widening the row
              "[@media(hover:none)]:after:absolute [@media(hover:none)]:after:-inset-2.5 [@media(hover:none)]:after:content-['']"
            )}
            aria-label="Line options"
            title="Line options"
          >
            <ListPlus className="size-3.5" />
          </span>
        }
        placement="bottom-end"
        menuItemsClassName="z-[14]"
        closeOnSelect
      >
        {onInlineAdd && (
          <>
            <CustomMenu.MenuItem onClick={() => onInlineAdd("below", "line")} className="flex items-center gap-2">
              <ArrowDownToLine className="size-3" />
              Add blank line below
            </CustomMenu.MenuItem>
            <CustomMenu.MenuItem onClick={() => onInlineAdd("above", "line")} className="flex items-center gap-2">
              <ArrowUpToLine className="size-3" />
              Add blank line above
            </CustomMenu.MenuItem>
            <CustomMenu.MenuItem onClick={() => onInlineAdd("below", "divider")} className="flex items-center gap-2">
              <SeparatorHorizontal className="size-3" />
              Add divider below
            </CustomMenu.MenuItem>
          </>
        )}
        {canToggle && (
          <CustomMenu.MenuItem onClick={toggleDivider} className="flex items-center gap-2">
            {issue.is_divider ? <ListTodo className="size-3" /> : <Heading className="size-3" />}
            {issue.is_divider ? "Turn into task line" : "Turn into divider"}
          </CustomMenu.MenuItem>
        )}
      </CustomMenu>
    </div>
  );
});
