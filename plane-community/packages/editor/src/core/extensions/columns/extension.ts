/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { findParentNodeClosestToPos } from "@tiptap/react";
// constants
import { CORE_EXTENSIONS } from "@/constants/extension";
// local imports
import { ColumnExtensionConfig, ColumnListExtensionConfig } from "./extension-config";

export const ColumnExtension = ColumnExtensionConfig;

export const ColumnListExtension = ColumnListExtensionConfig.extend({
  draggable: true,

  addCommands() {
    return {
      insertColumns:
        (count: 2 | 3) =>
        ({ commands }) =>
          commands.insertContent({
            type: this.name,
            attrs: { "data-columns": count },
            content: Array.from({ length: count }, () => ({
              type: CORE_EXTENSIONS.COLUMN,
              content: [{ type: CORE_EXTENSIONS.PARAGRAPH }],
            })),
          }),
    };
  },

  addKeyboardShortcuts() {
    return {
      // Backspace in an empty first block of an empty column list removes the columns.
      Backspace: ({ editor }) => {
        const { $from, empty } = editor.state.selection;
        if (!empty || $from.parentOffset !== 0) return false;
        const list = findParentNodeClosestToPos($from, (node) => node.type.name === this.name);
        if (!list) return false;
        if (list.node.textContent.length > 0) return false;
        return editor
          .chain()
          .deleteRange({ from: list.pos, to: list.pos + list.node.nodeSize })
          .insertContentAt(list.pos, { type: CORE_EXTENSIONS.PARAGRAPH })
          .run();
      },
    };
  },
});
