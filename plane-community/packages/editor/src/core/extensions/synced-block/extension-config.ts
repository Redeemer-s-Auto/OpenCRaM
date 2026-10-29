/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Node, mergeAttributes } from "@tiptap/core";
// constants
import { CORE_EXTENSIONS } from "@/constants/extension";

/**
 * Synced block: one block of text shown on many pages. The page stores only the block id:
 *   <div data-block-type="synced-block" data-synced-id="<uuid>"></div>
 * An empty id means "not chosen yet": the block asks which one to use.
 */

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    [CORE_EXTENSIONS.SYNCED_BLOCK]: {
      insertSyncedBlock: () => ReturnType;
    };
  }
}

export const SYNCED_BLOCK_ID_ATTRIBUTE = "data-synced-id";

export const SyncedBlockExtensionConfig = Node.create({
  name: CORE_EXTENSIONS.SYNCED_BLOCK,
  group: "block",
  atom: true,
  selectable: true,
  draggable: true,

  addAttributes() {
    return {
      [SYNCED_BLOCK_ID_ATTRIBUTE]: {
        default: "",
        parseHTML: (element) => element.getAttribute(SYNCED_BLOCK_ID_ATTRIBUTE) ?? "",
        renderHTML: (attributes) => ({ [SYNCED_BLOCK_ID_ATTRIBUTE]: String(attributes[SYNCED_BLOCK_ID_ATTRIBUTE] ?? "") }),
      },
    };
  },

  parseHTML() {
    return [{ tag: 'div[data-block-type="synced-block"]' }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["div", mergeAttributes(HTMLAttributes, { "data-block-type": "synced-block" })];
  },
});
