/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Node, mergeAttributes } from "@tiptap/core";
// constants
import { CORE_EXTENSIONS } from "@/constants/extension";

/**
 * Date mention: a date (and maybe a time) inside a sentence, like Notion @date. Stored as:
 *   <span data-type="date-mention" data-date="2026-10-30" data-time="14:30" data-mention-id="<uuid>">Oct 30, 2026 2:30 PM</span>
 * `data-time` is left out when there is no time. The text inside is only for readers that do not
 * draw the chip (exports, search). `data-mention-id` is what a person reminder hangs on.
 */

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    [CORE_EXTENSIONS.DATE_MENTION]: {
      insertDateMention: () => ReturnType;
    };
  }
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "Oct 30, 2026" or "Oct 30, 2026 2:30 PM". Works on the text parts, so no time zone can shift the day. */
export const formatDateMentionLabel = (date: string, time?: string | null): string => {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date ?? "");
  if (!match) return date ?? "";
  const label = `${MONTHS[Number(match[2]) - 1] ?? match[2]} ${Number(match[3])}, ${match[1]}`;
  const clock = /^(\d{2}):(\d{2})/.exec(time ?? "");
  if (!clock) return label;
  const hour = Number(clock[1]);
  return `${label} ${hour % 12 || 12}:${clock[2]} ${hour < 12 ? "AM" : "PM"}`;
};

export const todayAsDateString = (): string => {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
};

/** A random id for a new mention (the browser own, or a fallback for old browsers). */
export const newMentionId = (): string => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
};

export const DateMentionExtensionConfig = Node.create({
  name: CORE_EXTENSIONS.DATE_MENTION,
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      date: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-date") ?? "",
        renderHTML: (attributes) => ({ "data-date": String(attributes.date ?? "") }),
      },
      time: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-time") ?? "",
        renderHTML: (attributes) => (attributes.time ? { "data-time": String(attributes.time) } : {}),
      },
      mentionId: {
        default: "",
        parseHTML: (element) => element.getAttribute("data-mention-id") ?? "",
        renderHTML: (attributes) => (attributes.mentionId ? { "data-mention-id": String(attributes.mentionId) } : {}),
      },
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-type="date-mention"]' }];
  },

  renderHTML({ node, HTMLAttributes }) {
    return [
      "span",
      mergeAttributes(HTMLAttributes, { "data-type": "date-mention" }),
      formatDateMentionLabel(node.attrs.date, node.attrs.time),
    ];
  },

  renderText({ node }) {
    return formatDateMentionLabel(node.attrs.date, node.attrs.time);
  },
});
