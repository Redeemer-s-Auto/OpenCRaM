/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Node, mergeAttributes } from "@tiptap/core";
import type { MarkdownSerializerState } from "@tiptap/pm/markdown";
import type { Node as ProseMirrorNode } from "@tiptap/pm/model";
// constants
import { CORE_EXTENSIONS } from "@/constants/extension";

/**
 * Columns (Notion "columns"): 2 or 3 blocks side by side. Stored as:
 *   <div data-block-type="column-list" data-columns="2">
 *     <div data-block-type="column">...blocks...</div>
 *     <div data-block-type="column">...blocks...</div>
 *   </div>
 * On narrow screens the columns stack.
 */

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    [CORE_EXTENSIONS.COLUMN_LIST]: {
      insertColumns: (count: 2 | 3) => ReturnType;
    };
  }
}

export const ColumnExtensionConfig = Node.create({
  name: CORE_EXTENSIONS.COLUMN,
  content: "block+",
  defining: true,
  isolating: true,
  selectable: false,

  parseHTML() {
    return [{ tag: 'div[data-block-type="column"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes(HTMLAttributes, { "data-block-type": "column" }), 0];
  },
});

export const ColumnListExtensionConfig = Node.create({
  name: CORE_EXTENSIONS.COLUMN_LIST,
  group: "block",
  content: `${CORE_EXTENSIONS.COLUMN}{2,3}`,
  defining: true,
  isolating: true,

  addAttributes() {
    return {
      "data-columns": {
        default: 2,
        parseHTML: (element) => Number(element.getAttribute("data-columns")) || element.children.length || 2,
        renderHTML: (attributes) => ({ "data-columns": String(attributes["data-columns"]) }),
      },
    };
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: MarkdownSerializerState, node: ProseMirrorNode) {
          // Markdown has no columns: write each column's blocks one after another.
          node.forEach((column) => {
            state.renderContent(column);
          });
        },
      },
    };
  },

  parseHTML() {
    return [{ tag: 'div[data-block-type="column-list"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes(HTMLAttributes, { "data-block-type": "column-list" }), 0];
  },
});
