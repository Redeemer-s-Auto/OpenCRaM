/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

// A cold load of a board only asks for the board's own details after ~3 s of JavaScript and the sign-in chain.
// Those two answers decide when the page under the board can draw at all, and they do not depend on anything
// the JavaScript works out: the board id is in the address. So the entry script asks for them at once, and the
// first service call for exactly that address takes the answer (once). Anything not taken within a short
// while is dropped, so nothing old is ever handed out.

import type { AxiosResponse } from "axios";
import { create } from "axios";
import { API_BASE_URL } from "@plane/constants";

const MAX_AGE_MS = 15000;
const early = new Map<string, { promise: Promise<AxiosResponse>; startedAt: number }>();

const BOARD_PATH = /^\/([^/]+)\/projects\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(\/|$)/;

/**
 * Starts the board-details and my-board-membership GETs when the address is a board page. Never throws.
 * (The view's own GET is not started here: tried, one load in about a dozen never drew its rows. The project
 * layout still starts it beside the board details.)
 */
export function startEarlyBoardGets(): void {
  try {
    const match = BOARD_PATH.exec(window.location.pathname);
    if (!match) return;
    const [, workspaceSlug, projectId] = match;
    const client = create({ baseURL: API_BASE_URL, withCredentials: true });
    [
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/`,
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/project-members/me/`,
    ].forEach((url) => {
      const promise = client.get(url);
      promise.catch(() => undefined); // an answer nobody takes must not surface as an unhandled rejection
      early.set(API_BASE_URL + url, { promise, startedAt: Date.now() });
    });
  } catch {
    // the page simply asks the usual way
  }
}

/** The early answer for this address, if one was started and is still fresh. Each answer is handed out once. */
export function takeEarlyGet(fullUrl: string): Promise<AxiosResponse> | undefined {
  if (early.size === 0) return undefined;
  const entry = early.get(fullUrl);
  if (!entry) return undefined;
  early.delete(fullUrl);
  return Date.now() - entry.startedAt < MAX_AGE_MS ? entry.promise : undefined;
}
