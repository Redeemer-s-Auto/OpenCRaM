/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Extension } from "@tiptap/core";
import { NodeSelection, Plugin, PluginKey } from "@tiptap/pm/state";
import type { EditorView } from "@tiptap/pm/view";
// constants
import { CORE_EXTENSIONS } from "@/constants/extension";
// plugins
import { ADD_HANDLE_WIDTH, AddHandlePlugin } from "@/plugins/add-handle";
import { AIHandlePlugin } from "@/plugins/ai-handle";
import { DragHandlePlugin, blockSelectors, nodeDOMAtCoords } from "@/plugins/drag-handle";

type Props = {
  aiEnabled: boolean;
  dragDropEnabled: boolean;
};

export type SideMenuPluginProps = {
  dragHandleWidth: number;
  handlesConfig: {
    ai: boolean;
    /** The + that adds a line below (Alt+click: above) a block. */
    add: boolean;
    dragDrop: boolean;
  };
  scrollThreshold: {
    up: number;
    down: number;
  };
};

export type SideMenuHandleOptions = {
  view: (view: EditorView, sideMenu: HTMLDivElement | null) => void;
  domEvents?: {
    [key: string]: (...args: any) => void;
  };
};

export const SideMenuExtension = (props: Props) => {
  const { aiEnabled, dragDropEnabled } = props;

  return Extension.create({
    name: CORE_EXTENSIONS.SIDE_MENU,
    addProseMirrorPlugins() {
      return [
        SideMenu({
          dragHandleWidth: 24,
          handlesConfig: {
            ai: aiEnabled,
            add: dragDropEnabled,
            dragDrop: dragDropEnabled,
          },
          scrollThreshold: { up: 200, down: 150 },
        }),
      ];
    },
  });
};

const absoluteRect = (node: Element) => {
  const data = node.getBoundingClientRect();

  return {
    top: data.top,
    left: data.left,
    width: data.width,
  };
};

/** A touch screen with no hover: the side menu stays beside the block that holds the caret. */
let noHoverQuery: MediaQueryList | null | undefined;
const isTouchScreen = () => {
  if (typeof window === "undefined") return false;
  // One MediaQueryList for the page: this runs on every scroll event and keystroke.
  if (noHoverQuery === undefined) noHoverQuery = window.matchMedia?.("(hover: none)") ?? null;
  return !!noHoverQuery?.matches;
};

/** The block element that holds the selection, as the side menu would find it under the mouse. */
const blockDOMAtSelection = (view: EditorView): Element | null => {
  const { selection } = view.state;
  const { $from } = selection;
  const pos = selection instanceof NodeSelection ? $from.pos : $from.depth >= 1 ? $from.before($from.depth) : null;
  if (pos === null) return null;
  const dom = view.nodeDOM(pos);
  const element = dom instanceof Element ? dom : dom?.parentElement;
  if (!element) return null;
  return element.closest(blockSelectors) ?? (element.parentElement?.matches(".ProseMirror") ? element : null);
};

const SideMenu = (options: SideMenuPluginProps) => {
  const { handlesConfig } = options;
  const editorSideMenu: HTMLDivElement | null = document.createElement("div");
  editorSideMenu.id = "editor-side-menu";
  // the block the menu sits beside, for touch screens (re-placed on scroll and selection change)
  let currentNode: Element | null = null;
  // side menu view actions
  const hideSideMenu = () => {
    if (!editorSideMenu?.classList.contains("side-menu-hidden")) editorSideMenu?.classList.add("side-menu-hidden");
  };
  const showSideMenu = () => editorSideMenu?.classList.remove("side-menu-hidden");
  // side menu elements
  const { view: dragHandleView, domEvents: dragHandleDOMEvents } = DragHandlePlugin(options);
  const { view: aiHandleView, domEvents: aiHandleDOMEvents } = AIHandlePlugin(options);
  const { view: addHandleView, domEvents: addHandleDOMEvents } = AddHandlePlugin(options);

  /** Put the side menu at the left of ``node``. */
  const placeBeside = (node: Element) => {
    const compStyle = window.getComputedStyle(node);
    const lineHeight = parseInt(compStyle.lineHeight, 10);
    const paddingTop = parseInt(compStyle.paddingTop, 10);

    const rect = absoluteRect(node);

    rect.top += (lineHeight - 20) / 2;
    rect.top += paddingTop;

    if (handlesConfig.ai) {
      rect.left -= 20;
    }
    if (handlesConfig.add) {
      rect.left -= ADD_HANDLE_WIDTH;
    }

    if (node.parentElement?.parentElement?.matches("td") || node.parentElement?.parentElement?.matches("th")) {
      if (node.matches("ul:not([data-type=taskList]) li, ol li")) {
        rect.left -= 5;
      }
    } else {
      // Li markers
      if (node.matches("ul:not([data-type=taskList]) li, ol li")) {
        rect.left -= 18;
      }
    }

    if (node.matches("table")) {
      rect.top += 8;
      rect.left -= 8;
    }

    rect.width = options.dragHandleWidth;

    if (!editorSideMenu) return;

    editorSideMenu.style.left = `${rect.left - rect.width}px`;
    editorSideMenu.style.top = `${rect.top}px`;
    editorSideMenu.classList.add("side-menu-placed");
    currentNode = node;
    if (handlesConfig.add) {
      addHandleDOMEvents?.mousemove?.(node);
    }
  };

  return new Plugin({
    key: new PluginKey("sideMenu"),
    view: (view) => {
      hideSideMenu();
      view?.dom.parentElement?.appendChild(editorSideMenu);
      // side menu elements' initialization
      if (handlesConfig.ai && !editorSideMenu.querySelector("#ai-handle")) {
        aiHandleView(view, editorSideMenu);
      }

      if (handlesConfig.add && !editorSideMenu.querySelector("#add-handle")) {
        addHandleView(view, editorSideMenu);
      }

      if (handlesConfig.dragDrop && !editorSideMenu.querySelector("#drag-handle")) {
        dragHandleView(view, editorSideMenu);
      }

      // A fixed menu drifts when the page scrolls under a finger; follow the block.
      // One re-place per frame however many scroll events arrive (each one forces a layout).
      let placeFrame: number | null = null;
      const scrollHandler = () => {
        if (!currentNode || placeFrame !== null || !isTouchScreen()) return;
        placeFrame = requestAnimationFrame(() => {
          placeFrame = null;
          if (currentNode) placeBeside(currentNode);
        });
      };
      document.addEventListener("scroll", scrollHandler, { capture: true, passive: true });

      return {
        update: (view) => {
          // No hover on a touch screen: keep the + beside the block that holds the caret.
          if (!isTouchScreen() || !view.editable) return;
          const node = blockDOMAtSelection(view);
          if (!node) return;
          // Typing inside the same block does not move it: re-place only when the caret's block changes.
          if (node === currentNode && editorSideMenu.classList.contains("side-menu-placed")) {
            showSideMenu();
            return;
          }
          placeBeside(node);
          showSideMenu();
        },
        destroy: () => {
          document.removeEventListener("scroll", scrollHandler, { capture: true });
          if (placeFrame !== null) cancelAnimationFrame(placeFrame);
          placeFrame = null;
          currentNode = null;
          hideSideMenu();
        },
      };
    },
    props: {
      handleDOMEvents: {
        mousemove: (view, event) => {
          if (!view.editable) return;

          const node = nodeDOMAtCoords({
            x: event.clientX + 50 + options.dragHandleWidth,
            y: event.clientY,
          });

          if (!(node instanceof Element) || node.matches("ul, ol")) {
            hideSideMenu();
            return;
          }

          placeBeside(node);
          showSideMenu();
          if (handlesConfig.dragDrop) {
            dragHandleDOMEvents?.mousemove();
          }
          if (handlesConfig.ai) {
            aiHandleDOMEvents?.mousemove?.();
          }
        },
        // keydown: () => hideSideMenu(),
        mousewheel: () => {
          if (!isTouchScreen()) hideSideMenu();
        },
        dragenter: (view) => {
          if (handlesConfig.dragDrop) {
            dragHandleDOMEvents?.dragenter?.(view);
          }
        },
        drop: (view, event) => {
          if (handlesConfig.dragDrop) {
            dragHandleDOMEvents?.drop?.(view, event);
          }
        },
        dragend: (view) => {
          if (handlesConfig.dragDrop) {
            dragHandleDOMEvents?.dragend?.(view);
          }
        },
      },
    },
  });
};
