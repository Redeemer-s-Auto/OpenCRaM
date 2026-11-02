/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

// A cold load of a board only asks for the board's own details after ~3 s of JavaScript and the sign-in chain.
// Those two answers decide when the page under the board can draw at all, and they do not depend on anything
// the JavaScript works out: the board id is in the address. So the entry script asks for them at once, and the
// first service call for exactly that address takes the answer (once). Anything not taken within a short
// while is dropped, so nothing old is ever handed out.

// The entry script starts the GETs (lib/early-board-gets.ts, imported ONLY by app/entry.client.tsx) and leaves
// them in a window slot; the services take them from here. The two files share nothing at runtime on purpose:
// while the entry script and the services imported one module, every page load threw one more React #418
// (hydration mismatch): 47 instead of 46 per load, measured 2026-11-01 on the dev stack.
import type { AxiosResponse } from "axios";

export type TEarlyGets = Map<string, { promise: Promise<AxiosResponse>; startedAt: number }>;
export const EARLY_GETS_SLOT = "__notesEarlyGets";
const MAX_AGE_MS = 15000;

/** The app's own first call: it answers with a user (an id) only when a session exists. */
export const CURRENT_USER_PATH = "/api/users/me/";

/** The early answer for this address, if one was started and is still fresh. Each answer is handed out once. */
export function takeEarlyGet(fullUrl: string): Promise<AxiosResponse> | undefined {
  const early = (window as unknown as Record<string, TEarlyGets | undefined>)[EARLY_GETS_SLOT];
  if (!early || early.size === 0) return undefined;
  const entry = early.get(fullUrl);
  if (!entry) return undefined;
  early.delete(fullUrl);
  return Date.now() - entry.startedAt < MAX_AGE_MS ? entry.promise : undefined;
}
