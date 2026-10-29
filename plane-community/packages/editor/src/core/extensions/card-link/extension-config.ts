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
 * "Link to card" block. Stores the card id ONLY:
 *   <card-link-component data-card-id="<uuid>"></card-link-component>
 * The title, colour and board are looked up each time the block is shown, for the
 * person looking, so renames show at once and a card they cannot see shows as
 * "Hidden card". A block with no id yet is a picker waiting for a choice.
 */

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    [CORE_EXTENSIONS.CARD_LINK]: {
      insertCardLink: (cardId?: string | null) => ReturnType;
    };
  }
}

export const CARD_LINK_TAG = "card-link-component";
export const CARD_LINK_ID_ATTRIBUTE = "data-card-id";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const isCardId = (value: unknown): value is string => typeof value === "string" && UUID.test(value);

export const CardLinkExtensionConfig = Node.create({
  name: CORE_EXTENSIONS.CARD_LINK,
  group: "block",
  atom: true,
  selectable: true,
  draggable: true,

  addAttributes() {
    return {
      cardId: {
        default: null,
        parseHTML: (element) => {
          const value = element.getAttribute(CARD_LINK_ID_ATTRIBUTE);
          return isCardId(value) ? value.toLowerCase() : null;
        },
        renderHTML: (attributes) =>
          isCardId(attributes.cardId) ? { [CARD_LINK_ID_ATTRIBUTE]: attributes.cardId } : {},
      },
    };
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: MarkdownSerializerState, node: ProseMirrorNode) {
          // Markdown has no live link: write a neutral marker, never a title.
          state.write(isCardId(node.attrs.cardId) ? "[Linked card]" : "");
          state.closeBlock(node);
        },
      },
    };
  },

  addCommands() {
    return {
      insertCardLink:
        (cardId) =>
        ({ commands }) =>
          commands.insertContent({ type: this.name, attrs: { cardId: isCardId(cardId) ? cardId : null } }),
    };
  },

  parseHTML() {
    return [{ tag: CARD_LINK_TAG }];
  },

  renderHTML({ HTMLAttributes }) {
    return [CARD_LINK_TAG, mergeAttributes(HTMLAttributes)];
  },
});
