/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Plugin, PluginKey } from "@tiptap/pm/state";
import { NodeViewWrapper, ReactNodeViewRenderer } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
// local imports
import type { TPageLinkTarget } from "./extension-config";
import { PageLinkExtensionConfig, pageLinkAttrsFromTarget, pageLinkTargetFromAttrs } from "./extension-config";

export type TPageLinkRenderProps = {
  /** null while the block waits for a page or board to be picked */
  target: TPageLinkTarget | null;
  editable: boolean;
  selected: boolean;
  /** pick a target for an empty block */
  onPick: (target: TPageLinkTarget) => void;
  /** take the block out */
  onRemove: () => void;
};

export type TPageLinkHandler = {
  /** Draws the block (chip or picker). Supplied by the app, which knows how to look pages and boards up. */
  renderComponent: (props: TPageLinkRenderProps) => React.ReactNode;
  /** True when pasted text is one of this app's page or board addresses. Must answer at once. */
  isPageUrl?: (text: string) => boolean;
  /** The target behind an address, or null when it is not found or not visible. */
  targetFromUrl?: (text: string) => Promise<TPageLinkTarget | null>;
};

const pasteKey = new PluginKey("pageLinkPaste");

export function PageLinkExtension(handler: TPageLinkHandler) {
  return PageLinkExtensionConfig.extend({
    addNodeView() {
      return ReactNodeViewRenderer((props: NodeViewProps) => (
        <NodeViewWrapper className="editor-page-link-component" data-drag-handle="">
          {handler.renderComponent({
            target: pageLinkTargetFromAttrs(props.node.attrs),
            editable: props.editor.isEditable,
            selected: props.selected,
            onPick: (target) => props.updateAttributes(pageLinkAttrsFromTarget(target)),
            onRemove: () => props.deleteNode(),
          })}
        </NodeViewWrapper>
      ));
    },

    addProseMirrorPlugins() {
      const { editor } = this;
      const name = this.name;
      if (!handler.isPageUrl || !handler.targetFromUrl) return [];
      return [
        new Plugin({
          key: pasteKey,
          props: {
            handlePaste: (_view, event) => {
              if (!editor.isEditable) return false;
              const text = event.clipboardData?.getData("text/plain")?.trim() ?? "";
              if (!text || /\s/.test(text) || !handler.isPageUrl?.(text)) return false;
              event.preventDefault();
              const at = editor.state.selection.from;
              // The body may change during the look-up: never insert past its end.
              const where = () => Math.min(at, editor.state.doc.content.size);
              void handler
                .targetFromUrl?.(text)
                .then((target) => {
                  if (target) {
                    editor
                      .chain()
                      .focus()
                      .insertContentAt(where(), { type: name, attrs: pageLinkAttrsFromTarget(target) })
                      .run();
                  } else {
                    // Not something this person can see: keep what they pasted, as a plain link.
                    editor
                      .chain()
                      .focus()
                      .insertContentAt(where(), {
                        type: "text",
                        text,
                        marks: [{ type: "link", attrs: { href: text } }],
                      })
                      .run();
                  }
                })
                .catch(() => {
                  try {
                    editor.chain().focus().insertContentAt(where(), text).run();
                  } catch {
                    // the editor is gone; nothing to do
                  }
                });
              return true;
            },
          },
        }),
      ];
    },
  });
}
