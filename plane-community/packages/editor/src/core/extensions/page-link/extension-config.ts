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
 * "Link to page" block: a page inside a page, like a Notion sub-page link. It stores an id ONLY:
 *   <page-link-component data-page-id="<uuid>"></page-link-component>      a page
 *   <page-link-component data-project-id="<uuid>"></page-link-component>   a board or folder
 * The icon and title are looked up each time the block is shown, for the person looking, so a
 * rename shows at once and a page they cannot see shows as "Hidden page". A block with no id yet
 * is a picker waiting for a choice. Exactly one of the two ids is set.
 */

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    [CORE_EXTENSIONS.PAGE_LINK]: {
      insertPageLink: (target?: TPageLinkTarget | null) => ReturnType;
    };
  }
}

export const PAGE_LINK_TAG = "page-link-component";
export const PAGE_LINK_PAGE_ATTRIBUTE = "data-page-id";
export const PAGE_LINK_PROJECT_ATTRIBUTE = "data-project-id";

/** What a block points at. */
export type TPageLinkTarget = { kind: "page"; id: string } | { kind: "project"; id: string };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const isEntityId = (value: unknown): value is string => typeof value === "string" && UUID.test(value);

/** The target of a node's attributes, or null when the block is still empty. */
export const pageLinkTargetFromAttrs = (attrs: Record<string, unknown>): TPageLinkTarget | null => {
  if (isEntityId(attrs.pageId)) return { kind: "page", id: attrs.pageId.toLowerCase() };
  if (isEntityId(attrs.projectId)) return { kind: "project", id: attrs.projectId.toLowerCase() };
  return null;
};

export const pageLinkAttrsFromTarget = (target: TPageLinkTarget | null | undefined) => ({
  pageId: target?.kind === "page" && isEntityId(target.id) ? target.id.toLowerCase() : null,
  projectId: target?.kind === "project" && isEntityId(target.id) ? target.id.toLowerCase() : null,
});

export const PageLinkExtensionConfig = Node.create({
  name: CORE_EXTENSIONS.PAGE_LINK,
  group: "block",
  atom: true,
  selectable: true,
  draggable: true,

  addAttributes() {
    return {
      pageId: {
        default: null,
        parseHTML: (element) => {
          const value = element.getAttribute(PAGE_LINK_PAGE_ATTRIBUTE);
          return isEntityId(value) ? value.toLowerCase() : null;
        },
        renderHTML: (attributes) =>
          isEntityId(attributes.pageId) ? { [PAGE_LINK_PAGE_ATTRIBUTE]: attributes.pageId } : {},
      },
      projectId: {
        default: null,
        parseHTML: (element) => {
          // a page id wins when both are present (never written that way)
          if (isEntityId(element.getAttribute(PAGE_LINK_PAGE_ATTRIBUTE))) return null;
          const value = element.getAttribute(PAGE_LINK_PROJECT_ATTRIBUTE);
          return isEntityId(value) ? value.toLowerCase() : null;
        },
        renderHTML: (attributes) =>
          !isEntityId(attributes.pageId) && isEntityId(attributes.projectId)
            ? { [PAGE_LINK_PROJECT_ATTRIBUTE]: attributes.projectId }
            : {},
      },
    };
  },

  addStorage() {
    return {
      markdown: {
        serialize(state: MarkdownSerializerState, node: ProseMirrorNode) {
          // Markdown has no live link: write a neutral marker, never a title.
          const target = pageLinkTargetFromAttrs(node.attrs);
          state.write(target ? (target.kind === "page" ? "[Linked page]" : "[Linked board]") : "");
          state.closeBlock(node);
        },
      },
    };
  },

  addCommands() {
    return {
      insertPageLink:
        (target) =>
        ({ commands }) =>
          commands.insertContent({ type: this.name, attrs: pageLinkAttrsFromTarget(target) }),
    };
  },

  parseHTML() {
    return [{ tag: PAGE_LINK_TAG }];
  },

  renderHTML({ HTMLAttributes }) {
    return [PAGE_LINK_TAG, mergeAttributes(HTMLAttributes)];
  },
});
