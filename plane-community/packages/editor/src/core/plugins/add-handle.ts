/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { TextSelection } from "@tiptap/pm/state";
import type { EditorView } from "@tiptap/pm/view";
// constants
import { CORE_EXTENSIONS } from "@/constants/extension";
// extensions
import type { SideMenuHandleOptions, SideMenuPluginProps } from "@/extensions";

const plusIcon =
  '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-plus"><path d="M5 12h14"/><path d="M12 5v14"/></svg>';

export const ADD_HANDLE_TOOLTIP = "Click to add below. Alt+click to add above";
/** Width of the + in the side menu, in px (size-5). */
export const ADD_HANDLE_WIDTH = 20;
const LONG_PRESS_MS = 500;

type TPlacement = "above" | "below";

const ITEM_TYPES: string[] = [CORE_EXTENSIONS.LIST_ITEM, CORE_EXTENSIONS.TASK_ITEM];

/**
 * The document position of the block the side menu sits beside (the element ``nodeDOMAtCoords`` found).
 * A list or to-do item resolves to the item, a table to the table; anything else to the innermost block.
 */
const blockPosAtDOM = (node: Element, view: EditorView, options: SideMenuPluginProps): number | undefined => {
  const rect = node.getBoundingClientRect();
  const coords = node.matches("blockquote")
    ? { left: rect.left + 1, top: rect.top + 1 }
    : { left: rect.left + 50 + options.dragHandleWidth, top: rect.top + 1 };
  let pos = view.posAtCoords(coords)?.inside;
  if (pos === undefined || pos === null || pos < 0) return undefined;

  const { doc } = view.state;
  pos = Math.min(pos, doc.content.size);
  const $pos = doc.resolve(pos);
  if (node.matches("table")) {
    for (let depth = $pos.depth; depth >= 1; depth--) {
      if ($pos.node(depth).type.name === CORE_EXTENSIONS.TABLE) return $pos.before(depth);
    }
  } else if (ITEM_TYPES.includes($pos.parent.type.name) && $pos.depth > 1) {
    return $pos.before($pos.depth);
  }
  return doc.nodeAt(pos) ? pos : undefined;
};

/** Insert an empty block right above or below the one at ``pos`` and put the caret in it. */
const insertBlock = (view: EditorView, pos: number, placement: TPlacement) => {
  const { state } = view;
  const block = state.doc.nodeAt(pos);
  if (!block) return;
  // Inside a list the new line is a sibling item (a list cannot hold a bare paragraph); elsewhere a paragraph.
  const newNode = ITEM_TYPES.includes(block.type.name)
    ? block.type.createAndFill()
    : state.schema.nodes.paragraph?.create();
  if (!newNode) return;
  const insertPos = placement === "below" ? pos + block.nodeSize : pos;
  const tr = state.tr.insert(insertPos, newNode);
  tr.setSelection(TextSelection.near(tr.doc.resolve(insertPos + 1), 1)).scrollIntoView();
  view.dispatch(tr);
  view.focus();
};

/**
 * The + at the left of every block, Notion style: click adds an empty line below the block,
 * Alt+click adds one above. On a touch screen a tap adds below and a long press (500 ms) above.
 * The side menu tells it which block is current through ``domEvents.mousemove(node)``.
 */
export const AddHandlePlugin = (options: SideMenuPluginProps): SideMenuHandleOptions => {
  let addHandleElement: HTMLButtonElement | null = null;
  let currentNode: Element | null = null;
  let pressTimer: ReturnType<typeof setTimeout> | null = null;
  let longPressFired = false;

  const add = (view: EditorView, placement: TPlacement) => {
    if (!view.editable || !currentNode) return;
    const pos = blockPosAtDOM(currentNode, view, options);
    if (pos === undefined) return;
    insertBlock(view, pos, placement);
  };

  const clearPress = () => {
    if (pressTimer) clearTimeout(pressTimer);
    pressTimer = null;
  };

  const view = (view: EditorView, sideMenu: HTMLDivElement | null) => {
    addHandleElement = document.createElement("button");
    addHandleElement.type = "button";
    addHandleElement.id = "add-handle";
    addHandleElement.title = ADD_HANDLE_TOOLTIP;
    addHandleElement.setAttribute("aria-label", ADD_HANDLE_TOOLTIP);
    addHandleElement.classList.value =
      "flex items-center justify-center size-5 aspect-square rounded-xs cursor-pointer outline-none text-tertiary hover:bg-layer-1-hover hover:text-primary active:bg-layer-1 transition-[background-color,_opacity] duration-200 ease-linear";
    const iconElement = document.createElement("span");
    iconElement.classList.value = "pointer-events-none";
    iconElement.innerHTML = plusIcon;
    addHandleElement.appendChild(iconElement);

    // Keep the editor's focus and selection where they are; the click does the work.
    addHandleElement.addEventListener("mousedown", (e) => e.preventDefault());
    addHandleElement.addEventListener("contextmenu", (e) => e.preventDefault());
    addHandleElement.addEventListener("click", (e) => {
      e.preventDefault();
      if (longPressFired) {
        longPressFired = false;
        return;
      }
      add(view, e.altKey ? "above" : "below");
    });
    addHandleElement.addEventListener("touchstart", () => {
      longPressFired = false;
      clearPress();
      pressTimer = setTimeout(() => {
        longPressFired = true;
        add(view, "above");
      }, LONG_PRESS_MS);
    });
    addHandleElement.addEventListener("touchmove", clearPress);
    addHandleElement.addEventListener("touchcancel", clearPress);
    addHandleElement.addEventListener("touchend", clearPress);

    sideMenu?.appendChild(addHandleElement);

    return {
      destroy: () => {
        clearPress();
        addHandleElement?.remove();
        addHandleElement = null;
        currentNode = null;
      },
    };
  };

  const domEvents = {
    mousemove: (node?: Element) => {
      if (node) currentNode = node;
    },
  };

  return {
    view,
    domEvents,
  };
};
