/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useSyncExternalStore } from "react";

/**
 * How a click on a card opens it: as a full page (default, Notion-style) or in the side peek.
 * Kept per browser, so no server setting or migration is needed.
 */
export type TCardOpenMode = "page" | "peek";

const STORAGE_KEY = "notes.cardOpenMode";
const listeners = new Set<() => void>();

export function getCardOpenMode(): TCardOpenMode {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "peek" ? "peek" : "page";
  } catch {
    return "page";
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
  const mode = useSyncExternalStore(subscribe, getCardOpenMode, () => "page" as TCardOpenMode);
  return [mode, setCardOpenMode];
}
