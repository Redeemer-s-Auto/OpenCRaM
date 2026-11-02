/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useSyncExternalStore } from "react";

/**
 * How a click on a card opens it: in the half-width side peek (default, as in Notion) or as a full page.
 * Kept per browser, so no server setting or migration is needed. The key changed with the default
 * (2026-11-02) so an old "page" choice made under the previous default does not override it.
 * Below 768 px a card always opens full screen; Ctrl/Cmd+click always opens a new tab.
 */
export type TCardOpenMode = "page" | "peek";

const STORAGE_KEY = "notes.cardOpenMode.v2";
const listeners = new Set<() => void>();

export function getCardOpenMode(): TCardOpenMode {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "page" ? "page" : "peek";
  } catch {
    return "peek";
  }
}

export function setCardOpenMode(mode: TCardOpenMode) {
  try {
    window.localStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // storage blocked: the choice lasts until reload
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function useCardOpenMode(): [TCardOpenMode, (mode: TCardOpenMode) => void] {
  const mode = useSyncExternalStore(subscribe, getCardOpenMode, () => "peek" as TCardOpenMode);
  return [mode, setCardOpenMode];
}
