/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

// A cold load of a board only asks for the board's own details after ~3 s of JavaScript and the sign-in chain.
// Those two answers decide when the page under the board can draw at all, and they do not depend on anything
// the JavaScript works out: the board id is in the address. So the entry script asks for them at once, and the
// first service call for exactly that address takes the answer (once). Anything not taken within a short
// while is dropped, so nothing old is ever handed out.

// Imported ONLY by app/entry.client.tsx, and imports nothing at runtime (see lib/early-gets.ts, which the
// services read the answers from through the window slot below).
import type { AxiosResponse } from "axios";
import type { TEarlyGets } from "@/lib/early-gets";

// same values as in lib/early-gets.ts (not imported: see above)
const EARLY_GETS_SLOT = "__notesEarlyGets";
const CURRENT_USER_PATH = "/api/users/me/";

// same value as API_BASE_URL in @plane/constants
const API_BASE_URL = process.env.VITE_API_BASE_URL || "";

const BOARD_PATH = /^\/([^/]+)\/projects\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(\/|$)/;

/**
 * On a board page, starts the app's own current-user GET (UserService.currentUser takes the answer, so a
 * signed-out load sends nothing extra), then, only when it answers with a user, the board-details and
 * my-board-membership GETs. Never throws.
 * (The view's own GET is not started here: tried, one load in about a dozen never drew its rows. The project
 * layout still starts it beside the board details.)
 */
export function startEarlyBoardGets(): void {
  try {
    const match = BOARD_PATH.exec(window.location.pathname);
    if (!match) return;
    const [, workspaceSlug, projectId] = match;
    const early: TEarlyGets = new Map();
    (window as unknown as Record<string, TEarlyGets>)[EARLY_GETS_SLOT] = early;
    // an axios-shaped answer (data, status), and an axios-shaped error for a non-2xx status unless any status is wanted
    const get = async (url: string, anyStatus: boolean): Promise<AxiosResponse> => {
      const res = await fetch(API_BASE_URL + url, {
        credentials: "include",
        headers: { Accept: "application/json, text/plain, */*" },
      });
      const text = await res.text();
      let data: unknown = text;
      try {
        data = text ? JSON.parse(text) : undefined;
      } catch {
        // not JSON: keep the text, as axios does
      }
      const response = { data, status: res.status, statusText: res.statusText, headers: {}, config: {} } as AxiosResponse;
      if (!anyStatus && (res.status < 200 || res.status >= 300))
        throw Object.assign(new Error(`Request failed with status code ${res.status}`), { response });
      return response;
    };
    const start = (url: string, anyStatus = false) => {
      const promise = get(url, anyStatus);
      promise.catch(() => undefined); // an answer nobody takes must not surface as an unhandled rejection
      early.set(API_BASE_URL + url, { promise, startedAt: Date.now() });
      return promise;
    };
    // same request as UserService.currentUser: a 401 is an answer, not an error
    start(CURRENT_USER_PATH, true)
      .then((response) => {
        if (!(response?.data as { id?: string } | undefined)?.id) return; // signed out: nothing more
        start(`/api/workspaces/${workspaceSlug}/projects/${projectId}/`);
        start(`/api/workspaces/${workspaceSlug}/projects/${projectId}/project-members/me/`);
      })
      .catch(() => undefined);
  } catch {
    // the page simply asks the usual way
  }
}

