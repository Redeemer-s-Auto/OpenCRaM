/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { findParentNodeClosestToPos, ReactNodeViewRenderer } from "@tiptap/react";
import { TextSelection } from "@tiptap/pm/state";
// constants
import { CORE_EXTENSIONS } from "@/constants/extension";
// local imports
import { ToggleBlock } from "./block";
import { ToggleContentExtensionConfig, ToggleExtensionConfig, ToggleTitleExtensionConfig } from "./extension-config";

export const ToggleTitleExtension = ToggleTitleExtensionConfig.extend({
  addKeyboardShortcuts() {
    return {
      // Enter in the title opens the toggle and moves into its first block.
      Enter: ({ editor }) => {
        const { $from } = editor.state.selection;
        if ($from.parent.type.name !== this.name) return false;
        const toggle = findParentNodeClosestToPos($from, (node) => node.type.name === CORE_EXTENSIONS.TOGGLE);
        if (!toggle) return false;
        const titleNode = toggle.node.child(0);
        // position of the first text position inside the content's first block
        const contentStart = toggle.pos + 1 + titleNode.nodeSize + 2;
        return editor
          .chain()
          .command(({ tr }) => {
            tr.setNodeMarkup(toggle.pos, undefined, { ...toggle.node.attrs, "data-open": true });
            tr.setSelection(TextSelection.near(tr.doc.resolve(contentStart)));
            return true;
          })
          .run();
      },
      // Backspace at the start of an empty title turns the toggle back into its content.
      Backspace: ({ editor }) => {
        const { $from, empty } = editor.state.selection;
        if (!empty || $from.parent.type.name !== this.name || $from.parentOffset !== 0) return false;
        if ($from.parent.content.size > 0) return false;
        const toggle = findParentNodeClosestToPos($from, (node) => node.type.name === CORE_EXTENSIONS.TOGGLE);
        if (!toggle) return false;
        const content = toggle.node.child(1).content;
        return editor
          .chain()
          .command(({ tr }) => {
            tr.replaceWith(toggle.pos, toggle.pos + toggle.node.nodeSize, content);
            tr.setSelection(TextSelection.near(tr.doc.resolve(toggle.pos + 1)));
            return true;
          })
          .run();
      },
    };
  },
});

export const ToggleContentExtension = ToggleContentExtensionConfig;

export const ToggleExtension = ToggleExtensionConfig.extend({
  draggable: true,

  addCommands() {
    return {
      insertToggle:
        () =>
        ({ commands }) =>
          commands.insertContent({
            type: this.name,
            attrs: { "data-open": true },
            content: [
              { type: CORE_EXTENSIONS.TOGGLE_TITLE },
              { type: CORE_EXTENSIONS.TOGGLE_CONTENT, content: [{ type: CORE_EXTENSIONS.PARAGRAPH }] },
            ],
          }),
    };
  },

  addNodeView() {
    return ReactNodeViewRenderer((props) => <ToggleBlock {...props} />);
  },
});
