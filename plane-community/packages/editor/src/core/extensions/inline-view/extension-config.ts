/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Node, mergeAttributes } from "@tiptap/core";
// constants
import { CORE_EXTENSIONS } from "@/constants/extension";

/**
 * Live view block: shows cards from a board (or this card's sub-cards or linked cards).
 * It stores only its settings, as JSON, never the cards:
 *   <div data-block-type="inline-view" data-view-config='{"source":{...},"layout":"board",...}'></div>
 */

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    [CORE_EXTENSIONS.INLINE_VIEW]: {
      insertInlineView: () => ReturnType;
    };
  }
}

export const INLINE_VIEW_CONFIG_ATTRIBUTE = "data-view-config";

export const InlineViewExtensionConfig = Node.create({
  name: CORE_EXTENSIONS.INLINE_VIEW,
  group: "block",
  atom: true,
  selectable: true,
  draggable: true,

  addAttributes() {
    return {
      [INLINE_VIEW_CONFIG_ATTRIBUTE]: {
        default: "{}",
        parseHTML: (element) => element.getAttribute(INLINE_VIEW_CONFIG_ATTRIBUTE) ?? "{}",
        renderHTML: (attributes) => ({
          [INLINE_VIEW_CONFIG_ATTRIBUTE]: String(attributes[INLINE_VIEW_CONFIG_ATTRIBUTE]),
        }),
      },
    };
  },

  parseHTML() {
    return [{ tag: 'div[data-block-type="inline-view"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes(HTMLAttributes, { "data-block-type": "inline-view" })];
  },
});
