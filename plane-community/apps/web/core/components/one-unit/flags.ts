/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

/**
 * Plane's separate Pages feature is retired in this fork: a card is the page.
 * The Pages data and API stay; the list, menu entry and settings switch are hidden. Set to
 * false to bring them back. A single page still opens at its own address: the sidebar page
 * tree and "Link to page" blocks (pages inside pages, from the Notion import) lead there.
 */
export const PLANE_PAGES_HIDDEN = true;

/** Cards fetched per sidebar tree level before "Show more". Matches the server default. */
export const CARD_TREE_PAGE_SIZE = 50;
