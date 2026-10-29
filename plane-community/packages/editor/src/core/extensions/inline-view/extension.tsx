/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { ReactNodeViewRenderer, NodeViewWrapper } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
// local imports
import { INLINE_VIEW_CONFIG_ATTRIBUTE, InlineViewExtensionConfig } from "./extension-config";
import type { TInlineViewConfig } from "./renderer-registry";
import { getInlineViewRenderer } from "./renderer-registry";

export const parseInlineViewConfig = (raw: unknown): TInlineViewConfig => {
  try {
    const parsed = JSON.parse(String(raw ?? "{}"));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as TInlineViewConfig) : {};
  } catch {
    return {};
  }
};

function InlineViewNodeView(props: NodeViewProps) {
  const { node, editor, updateAttributes, deleteNode } = props;
  const render = getInlineViewRenderer();
  const config = parseInlineViewConfig(node.attrs[INLINE_VIEW_CONFIG_ATTRIBUTE]);
  return (
    <NodeViewWrapper className="inline-view-block my-3" contentEditable={false}>
      {render ? (
        render({
          config,
          editable: editor.isEditable,
          updateConfig: (next) => updateAttributes({ [INLINE_VIEW_CONFIG_ATTRIBUTE]: JSON.stringify(next) }),
          deleteBlock: () => deleteNode(),
        })
      ) : (
        <div className="rounded-md border border-dashed border-subtle p-3 text-13 text-tertiary">
          Live view (not available here)
        </div>
      )}
    </NodeViewWrapper>
  );
}

export const InlineViewExtension = InlineViewExtensionConfig.extend({
  addNodeView() {
    return ReactNodeViewRenderer(InlineViewNodeView);
  },

  addCommands() {
    return {
      insertInlineView:
        () =>
        ({ commands }) =>
          commands.insertContent({ type: this.name, attrs: { [INLINE_VIEW_CONFIG_ATTRIBUTE]: "{}" } }),
    };
  },
});
