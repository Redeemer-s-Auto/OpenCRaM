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
 * Toggle block (Notion "toggle"): a one-line title you click to open or close the
 * blocks under it. Stored as:
 *   <details data-block-type="toggle" data-open="true">
 *     <summary data-block-type="toggle-title">Title</summary>
 *     <div data-block-type="toggle-content">...blocks...</div>
 *   </details>
 */

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    [CORE_EXTENSIONS.TOGGLE]: {
      insertToggle: () => ReturnType;
    };
  }
}

export const ToggleTitleExtensionConfig = Node.create({
  name: CORE_EXTENSIONS.TOGGLE_TITLE,
  content: "inline*",
  defining: true,
  selectable: false,

  parseHTML() {
    return [{ tag: 'summary[data-block-type="toggle-title"]' }, { tag: "details > summary" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["summary", mergeAttributes(HTMLAttributes, { "data-block-type": "toggle-title" }), 0];
  },
});

export const ToggleContentExtensionConfig = Node.create({
  name: CORE_EXTENSIONS.TOGGLE_CONTENT,
  content: "block+",
  defining: true,
  selectable: false,

  parseHTML() {
    return [{ tag: 'div[data-block-type="toggle-content"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes(HTMLAttributes, { "data-block-type": "toggle-content" }), 0];
  },
});

export const ToggleExtensionConfig = Node.create({
  name: CORE_EXTENSIONS.TOGGLE,
  group: "block",
  content: `${CORE_EXTENSIONS.TOGGLE_TITLE} ${CORE_EXTENSIONS.TOGGLE_CONTENT}`,
  defining: true,

  addAttributes() {
    return {
      "data-open": {
        default: true,
        parseHTML: (element) => element.getAttribute("data-open") !== "false",
        renderHTML: (attributes) => ({ "data-open": attributes["data-open"] ? "true" : "false" }),
      },
    };
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: MarkdownSerializerState, node: ProseMirrorNode) {
          // Markdown has no toggle: write the title in bold, then the content.
          const title = node.child(0);
          state.write("**");
          state.renderInline(title);
          state.write("**");
          state.closeBlock(node);
          state.renderContent(node.child(1));
        },
      },
    };
  },

  parseHTML() {
    return [{ tag: 'details[data-block-type="toggle"]' }, { tag: "details" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["details", mergeAttributes(HTMLAttributes, { "data-block-type": "toggle", open: "" }), 0];
  },
});
