/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
// local imports
import { DateMentionExtensionConfig, formatDateMentionLabel, newMentionId, todayAsDateString } from "./extension-config";
import { getDateMentionRenderer } from "./renderer-registry";

function DateMentionNodeView(props: NodeViewProps) {
  const { node, editor, updateAttributes, deleteNode } = props;
  const render = getDateMentionRenderer();
  const date = String(node.attrs.date ?? "");
  const time = String(node.attrs.time ?? "");
  return (
    <NodeViewWrapper as="span" className="date-mention inline-block align-baseline">
      {render ? (
        render({
          date,
          time,
          mentionId: String(node.attrs.mentionId ?? ""),
          editable: editor.isEditable,
          update: (next) => updateAttributes({ date: next.date, time: next.time }),
          remove: () => deleteNode(),
        })
      ) : (
        <span className="rounded-sm bg-layer-1 px-1 text-secondary">{formatDateMentionLabel(date, time)}</span>
      )}
    </NodeViewWrapper>
  );
}

export const DateMentionExtension = DateMentionExtensionConfig.extend({
  addNodeView() {
    return ReactNodeViewRenderer(DateMentionNodeView);
  },

  addCommands() {
    return {
      insertDateMention:
        () =>
        ({ commands }) =>
          commands.insertContent([
            { type: this.name, attrs: { date: todayAsDateString(), time: "", mentionId: newMentionId() } },
            { type: "text", text: " " },
          ]),
    };
  },
});
