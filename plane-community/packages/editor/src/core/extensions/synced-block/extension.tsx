/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
// local imports
import { SYNCED_BLOCK_ID_ATTRIBUTE, SyncedBlockExtensionConfig } from "./extension-config";
import { getSyncedBlockRenderer } from "./renderer-registry";

function SyncedBlockNodeView(props: NodeViewProps) {
  const { node, editor, updateAttributes, deleteNode, getPos } = props;
  const render = getSyncedBlockRenderer();
  const id = String(node.attrs[SYNCED_BLOCK_ID_ATTRIBUTE] ?? "");
  return (
    <NodeViewWrapper className="synced-block my-3" contentEditable={false}>
      {render ? (
        render({
          id,
          editable: editor.isEditable,
          setId: (next) => updateAttributes({ [SYNCED_BLOCK_ID_ATTRIBUTE]: next }),
          removeCopy: () => deleteNode(),
          unsync: (html) => {
            const pos = getPos();
            if (typeof pos !== "number") return;
            editor
              .chain()
              .focus()
              .insertContentAt({ from: pos, to: pos + node.nodeSize }, html)
              .run();
          },
        })
      ) : (
        <div className="rounded-md border border-dashed border-subtle p-3 text-13 text-tertiary">
          Synced block (not available here)
        </div>
      )}
    </NodeViewWrapper>
  );
}

export const SyncedBlockExtension = SyncedBlockExtensionConfig.extend({
  addNodeView() {
    return ReactNodeViewRenderer(SyncedBlockNodeView);
  },

  addCommands() {
    return {
      insertSyncedBlock:
        () =>
        ({ commands }) =>
          // a paragraph after the block keeps a place to type below it
          commands.insertContent([
            { type: this.name, attrs: { [SYNCED_BLOCK_ID_ATTRIBUTE]: "" } },
            { type: "paragraph" },
          ]),
    };
  },
});
