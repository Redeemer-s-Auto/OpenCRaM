/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { TOAST_TYPE, dismissToast, setToast } from "@plane/propel/toast";
// undo
import type { TUndoResult } from "@/store/undo/undo-stack";
import { undoStack } from "@/store/undo/undo-stack";

/** Input types that hold text: Ctrl+Z there undoes typing, not the last action. */
const NON_TEXT_INPUTS = new Set([
  "checkbox",
  "radio",
  "button",
  "submit",
  "reset",
  "range",
  "color",
  "file",
  "image",
  "hidden",
]);

/** True when the key belongs to a text box, a select or the editor (their own undo wins). */
const isTextTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable || target.closest("[contenteditable]:not([contenteditable='false'])")) return true;
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
  if (target instanceof HTMLInputElement) return !NON_TEXT_INPUTS.has((target.type || "text").toLowerCase());
  return false;
};

// one toast at a time
let lastToastId: string | undefined;

const showToast = (props: Parameters<typeof setToast>[0]) => {
  if (lastToastId) dismissToast(lastToastId);
  lastToastId = setToast(props);
};

const run = async (direction: "undo" | "redo") => {
  const result: TUndoResult = direction === "undo" ? await undoStack.undo() : await undoStack.redo();
  switch (result.status) {
    case "busy":
      return;
    case "empty":
      showToast({ type: TOAST_TYPE.INFO, title: direction === "undo" ? "Nothing to undo" : "Nothing to redo" });
      return;
    case "failed":
      showToast({
        type: TOAST_TYPE.ERROR,
        title: `Could not ${direction}: ${result.label}`,
        message: "The row or view may have changed or been removed. Reload the page and try again.",
      });
      return;
    case "done":
      if (direction === "undo") {
        showToast({
          type: TOAST_TYPE.SUCCESS,
          title: `Undone: ${result.label}`,
          actionItems: (
            <div className="-ml-2 flex items-center gap-1 text-11 text-secondary">
              <button
                type="button"
                className="rounded-sm px-2 py-1 font-medium text-accent-primary hover:bg-surface-2"
                onClick={() => void run("redo")}
              >
                Redo
              </button>
            </div>
          ),
        });
      } else {
        showToast({ type: TOAST_TYPE.SUCCESS, title: `Redone: ${result.label}` });
      }
  }
};

/**
 * Ctrl+Z / Cmd+Z undoes the last change made on this screen (cards, properties, views, pages);
 * Ctrl+Shift+Z, Cmd+Shift+Z and Ctrl+Y redo it. Mounted once, in the workspace layout.
 * In a text box, a select or the editor the key is left alone, so text undo works there.
 * The stack itself is store/undo/undo-stack.ts; the stores record into it.
 */
export function UndoShortcuts() {
  const pathname = usePathname();

  // each screen keeps its own list
  useEffect(() => {
    undoStack.setScope(pathname);
  }, [pathname]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || event.altKey) return;
      if (!event.ctrlKey && !event.metaKey) return;
      const key = event.key.toLowerCase();
      const isUndo = key === "z" && !event.shiftKey;
      const isRedo = (key === "z" && event.shiftKey) || (key === "y" && !event.shiftKey);
      if (!isUndo && !isRedo) return;
      if (isTextTarget(event.target) || isTextTarget(document.activeElement)) return;
      event.preventDefault();
      void run(isUndo ? "undo" : "redo");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      // leaving the workspace (sign out, switch): the stores behind the old entries are gone
      undoStack.clear();
    };
  }, []);

  return null;
}
