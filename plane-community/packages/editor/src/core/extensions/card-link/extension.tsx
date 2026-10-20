/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Plugin, PluginKey } from "@tiptap/pm/state";
import { NodeViewWrapper, ReactNodeViewRenderer } from "@tiptap/react";
import type { NodeViewProps } from "@tiptap/react";
// local imports
import { CardLinkExtensionConfig, isCardId } from "./extension-config";

export type TCardLinkRenderProps = {
  /** null while the block waits for a card to be picked */
  cardId: string | null;
  editable: boolean;
  selected: boolean;
  /** pick a card for an empty block */
  onPick: (cardId: string) => void;
  /** take the block out */
  onRemove: () => void;
};

export type TCardLinkHandler = {
  /** Draws the block (chip or picker). Supplied by the app, which knows how to look cards up. */
  renderComponent: (props: TCardLinkRenderProps) => React.ReactNode;
  /** True when pasted text is one of this app's card addresses. Must answer at once. */
  isCardUrl?: (text: string) => boolean;
  /** The card id behind a card address, or null when the card is not found or not visible. */
  cardIdFromUrl?: (text: string) => Promise<string | null>;
};

const pasteKey = new PluginKey("cardLinkPaste");

export function CardLinkExtension(handler: TCardLinkHandler) {
  return CardLinkExtensionConfig.extend({
    addNodeView() {
      return ReactNodeViewRenderer((props: NodeViewProps) => {
        const cardId = isCardId(props.node.attrs.cardId) ? (props.node.attrs.cardId as string) : null;
        return (
          <NodeViewWrapper className="editor-card-link-component" data-drag-handle="">
            {handler.renderComponent({
              cardId,
              editable: props.editor.isEditable,
              selected: props.selected,
              onPick: (id) => {
                if (isCardId(id)) props.updateAttributes({ cardId: id.toLowerCase() });
              },
              onRemove: () => props.deleteNode(),
            })}
          </NodeViewWrapper>
        );
      });
    },

    addProseMirrorPlugins() {
      const { editor } = this;
      const name = this.name;
      if (!handler.isCardUrl || !handler.cardIdFromUrl) return [];
      return [
        new Plugin({
          key: pasteKey,
          props: {
            handlePaste: (_view, event) => {
              if (!editor.isEditable) return false;
              const text = event.clipboardData?.getData("text/plain")?.trim() ?? "";
              if (!text || /\s/.test(text) || !handler.isCardUrl?.(text)) return false;
              event.preventDefault();
              const at = editor.state.selection.from;
              void handler
                .cardIdFromUrl?.(text)
                .then((cardId) => {
                  if (isCardId(cardId)) {
                    editor.chain().focus().insertContentAt(at, { type: name, attrs: { cardId } }).run();
                  } else {
                    // Not a card this person can see: keep what they pasted, as a plain link.
                    editor
                      .chain()
                      .focus()
                      .insertContentAt(at, { type: "text", text, marks: [{ type: "link", attrs: { href: text } }] })
                      .run();
                  }
                })
                .catch(() => editor.chain().focus().insertContentAt(at, text).run());
              return true;
            },
          },
        }),
      ];
    },
  });
}
