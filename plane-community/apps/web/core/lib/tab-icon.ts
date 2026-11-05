/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * The browser-tab icon follows the page: a board's icon on its screens and cards, a page's icon on
 * that page, the app icon everywhere else. With ten tabs open, the icons tell them apart.
 *
 * An icon becomes a 64 x 64 PNG data URL: an emoji is drawn with the system emoji font, a built-in
 * icon is drawn in its own colour (Material Symbols for boards, Lucide for pages), an image URL is
 * used as it is. A very dark or very light icon colour gets a small backdrop so it stays visible on
 * both the light and the dark tab strip.
 */

import { createElement } from "react";
// plane imports
import { LUCIDE_ICONS_LIST, stringToEmoji } from "@plane/propel/emoji-icon-picker";
import type { TLogoProps } from "@plane/types";

export type TTabIconKind = "material" | "lucide";

const SIZE = 64;
const DEFAULT_ICON_COLOR = "#6d7b8a";
const EMOJI_FONTS = '"Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", "Segoe UI Symbol", sans-serif';
const MATERIAL_FONT = '"Material Symbols Rounded"';

const cache = new Map<string, string>();

/** Only http(s) URLs and same-site paths are used as an icon image. */
function safeImageUrl(url: string | undefined): string | null {
  const value = (url || "").trim();
  if (!value) return null;
  if (value.startsWith("/") && !value.startsWith("//")) return value;
  return /^https?:\/\//i.test(value) ? value : null;
}

/** Relative luminance 0 (black) .. 1 (white) of a #rgb / #rrggbb colour; null when not a hex colour. */
function luminance(hex: string): number | null {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim());
  if (!m) return null;
  const h = m[1].length === 3 ? m[1].replace(/./g, (c) => c + c) : m[1];
  const [r, g, b] = [0, 2, 4].map((i) => {
    const v = parseInt(h.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function newCanvas(): [HTMLCanvasElement, CanvasRenderingContext2D] | null {
  const canvas = document.createElement("canvas");
  canvas.width = SIZE;
  canvas.height = SIZE;
  const ctx = canvas.getContext("2d");
  return ctx ? [canvas, ctx] : null;
}

/** A rounded backdrop behind an icon whose colour would vanish on a light or a dark tab strip. */
function drawBackdrop(ctx: CanvasRenderingContext2D, color: string) {
  const lum = luminance(color);
  if (lum === null || (lum > 0.08 && lum < 0.7)) return;
  ctx.fillStyle = lum <= 0.08 ? "#ffffff" : "#3a3a3a";
  ctx.beginPath();
  ctx.roundRect(0, 0, SIZE, SIZE, 14);
  ctx.fill();
}

function drawEmoji(value: string): string | null {
  const emoji = stringToEmoji(value);
  const made = newCanvas();
  if (!emoji || !made) return null;
  const [canvas, ctx] = made;
  ctx.font = `52px ${EMOJI_FONTS}`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(emoji, SIZE / 2, SIZE / 2 + 3);
  return canvas.toDataURL("image/png");
}

async function drawMaterial(name: string, color: string): Promise<string | null> {
  const made = newCanvas();
  if (!made) return null;
  const [canvas, ctx] = made;
  try {
    await document.fonts.load(`56px ${MATERIAL_FONT}`, name);
  } catch {
    // drawn with whatever font is ready
  }
  if (!document.fonts.check(`56px ${MATERIAL_FONT}`, name)) return null;
  drawBackdrop(ctx, color);
  ctx.font = `56px ${MATERIAL_FONT}`;
  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(name, SIZE / 2, SIZE / 2);
  return canvas.toDataURL("image/png");
}

/** A letter badge: a letter on a coloured rounded square. */
function drawLetter(text: string, color: string, background: string): string | null {
  const made = newCanvas();
  if (!text || !made) return null;
  const [canvas, ctx] = made;
  ctx.fillStyle = background;
  ctx.beginPath();
  ctx.roundRect(0, 0, SIZE, SIZE, 14);
  ctx.fill();
  ctx.font = `bold 44px ${EMOJI_FONTS}`;
  ctx.fillStyle = color;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, SIZE / 2, SIZE / 2 + 3);
  return canvas.toDataURL("image/png");
}

async function drawLucide(name: string, color: string): Promise<string | null> {
  const icon = LUCIDE_ICONS_LIST.find((item) => item.name === name);
  const made = newCanvas();
  if (!icon || !made) return null;
  const { renderToStaticMarkup } = await import("react-dom/server");
  const svg = renderToStaticMarkup(createElement(icon.element, { color, size: 48, strokeWidth: 2.25 }));
  const image = new Image();
  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  await image.decode();
  const [canvas, ctx] = made;
  drawBackdrop(ctx, color);
  ctx.drawImage(image, 8, 8, 48, 48);
  return canvas.toDataURL("image/png");
}

/** The tab icon for a board or page logo; null when it has none (the app icon is used then). */
export async function logoToTabIcon(
  logo: TLogoProps | null | undefined,
  kind: TTabIconKind = "material"
): Promise<string | null> {
  if (!logo?.in_use || typeof document === "undefined") return null;
  const key = `${kind}:${JSON.stringify(logo)}`;
  const cached = cache.get(key);
  if (cached) return cached;

  let href: string | null = null;
  try {
    if (logo.in_use === "emoji") {
      href = logo.emoji?.value ? drawEmoji(logo.emoji.value) : safeImageUrl(logo.emoji?.url);
    } else if (logo.in_use === "letter" && logo.letter?.text) {
      href = drawLetter(
        logo.letter.text.trim().slice(0, 1),
        logo.letter.color || "#ffffff",
        logo.letter.background || "#7a7a7a"
      );
    } else if (logo.in_use === "icon" && logo.icon?.name) {
      const color = logo.icon.color || DEFAULT_ICON_COLOR;
      href =
        kind === "lucide" ? await drawLucide(logo.icon.name, color) : await drawMaterial(logo.icon.name, color);
    }
  } catch {
    href = null;
  }
  if (href) cache.set(key, href);
  return href;
}

// ---- the <link rel="icon"> tags ----

const OVERRIDE_ATTR = "data-tab-icon";
const saved = new Map<HTMLLinkElement, { href: string | null; type: string | null; sizes: string | null }>();

/**
 * Point the tab icon at `href`, or back at the app icon when `href` is null. The app's own icon
 * links are re-pointed (and put back later) rather than replaced, so the browser has one answer.
 */
export function setTabIcon(href: string | null) {
  if (typeof document === "undefined") return;
  const links = Array.from(document.head.querySelectorAll<HTMLLinkElement>('link[rel~="icon"]'));

  if (!href) {
    for (const link of links) {
      if (link.hasAttribute(OVERRIDE_ATTR)) {
        link.remove();
        continue;
      }
      const original = saved.get(link);
      if (!original) continue;
      for (const attr of ["href", "type", "sizes"] as const) {
        const value = original[attr];
        if (value === null) link.removeAttribute(attr);
        else link.setAttribute(attr, value);
      }
    }
    saved.clear();
    return;
  }

  const appLinks = links.filter((link) => !link.hasAttribute(OVERRIDE_ATTR));
  if (appLinks.length === 0) {
    // No app icon in this build: add one link of our own (removed again on reset).
    let own = links.find((link) => link.hasAttribute(OVERRIDE_ATTR));
    if (!own) {
      own = document.createElement("link");
      own.rel = "icon";
      own.setAttribute(OVERRIDE_ATTR, "");
      document.head.appendChild(own);
    }
    own.href = href;
    return;
  }
  for (const link of appLinks) {
    if (!saved.has(link)) {
      saved.set(link, {
        href: link.getAttribute("href"),
        type: link.getAttribute("type"),
        sizes: link.getAttribute("sizes"),
      });
    }
    link.removeAttribute("type");
    link.removeAttribute("sizes");
    if (link.getAttribute("href") !== href) link.setAttribute("href", href);
  }
}
