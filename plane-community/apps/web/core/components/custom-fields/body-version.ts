/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useSyncExternalStore } from "react";

// The page body editor keeps its own copy of the text. When text is moved into the body from
// elsewhere on the page ("Move to page body"), the editor is remounted by changing its key.
const versions = new Map<string, number>();
const listeners = new Set<() => void>();

export const bumpBodyVersion = (issueId: string) => {
  versions.set(issueId, (versions.get(issueId) ?? 0) + 1);
  listeners.forEach((listener) => listener());
};

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

/** Part of the body editor's key: changes when text was moved into the body. */
export const useBodyVersion = (issueId: string) =>
  useSyncExternalStore(
    subscribe,
    () => versions.get(issueId) ?? 0,
    () => 0
  );
