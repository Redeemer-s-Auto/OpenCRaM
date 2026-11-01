/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

// Some workspace data is not needed to draw the first cards of a page: the workspace-wide states (a large
// list), favorites and the unread-notification count. Asking for them during a cold load competes with the
// calls the first cards do need (on a small server and on the main thread). They wait until the first list of
// cards has been drawn, or a few seconds on pages without one, then load as before.

import { useEffect, useState } from "react";

/** Pages that draw no card list still load the deferred data after this long. */
const FALLBACK_MS = 3000;

let isReady = false;
const listeners = new Set<() => void>();

const setReady = () => {
  if (isReady) return;
  isReady = true;
  listeners.forEach((listener) => listener());
  listeners.clear();
};

/** Called once a list of cards has arrived; the deferred calls start after the next paint. */
export const markFirstContentReady = (): void => {
  if (isReady) return;
  if (typeof window === "undefined" || typeof requestAnimationFrame === "undefined") return setReady();
  requestAnimationFrame(() => setTimeout(setReady, 0));
};

/** False until the first list of cards is drawn (or FALLBACK_MS after this hook first runs), then true. */
export const useAfterFirstContent = (): boolean => {
  const [ready, setReadyState] = useState(isReady);
  useEffect(() => {
    if (ready) return;
    if (isReady) {
      setReadyState(true);
      return;
    }
    const onReady = () => setReadyState(true);
    listeners.add(onReady);
    const timer = setTimeout(setReady, FALLBACK_MS);
    return () => {
      listeners.delete(onReady);
      clearTimeout(timer);
    };
  }, [ready]);
  return ready;
};
