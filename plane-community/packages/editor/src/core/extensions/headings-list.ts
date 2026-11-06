/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Extension } from "@tiptap/core";
import { Plugin, PluginKey } from "@tiptap/pm/state";
// constants
import { CORE_EXTENSIONS } from "@/constants/extension";
// types
import type { IMarking } from "@/types";

export type HeadingExtensionStorage = {
  headings: IMarking[];
};

declare module "@tiptap/core" {
  interface Storage {
    [CORE_EXTENSIONS.HEADINGS_LIST]: HeadingExtensionStorage;
  }
}

export const HeadingListExtension = Extension.create<unknown, HeadingExtensionStorage>({
  name: CORE_EXTENSIONS.HEADINGS_LIST,

  addStorage() {
    return {
      headings: [] as IMarking[],
    };
  },

  addProseMirrorPlugins() {
    const plugin = new Plugin({
      key: new PluginKey("heading-list"),
      appendTransaction: (_, __, newState) => {
        const headings: IMarking[] = [];
        // One counter per level: the outline finds a heading again by "the Nth heading of this level",
        // so an h4-h6 must not be counted into the h3 numbers.
        const sequences: Record<number, number> = {};

        newState.doc.descendants((node) => {
          if (node.type.name === "heading") {
            const level = node.attrs.level;
            const text = node.textContent;

            headings.push({
              type: "heading",
              level: level,
              text: text,
              sequence: (sequences[level] = (sequences[level] ?? 0) + 1),
            });
          }
        });

        this.storage.headings = headings;

        this.editor.emit("update", {
          editor: this.editor,
          transaction: newState.tr,
        });

        return null;
      },
    });

    return [plugin];
  },

  getHeadings() {
    return this.storage.headings;
  },
});
