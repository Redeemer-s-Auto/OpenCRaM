/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

// Which sidebar rows are open (sections, teamspaces, boards, pages). Everything starts closed on every
// load and nothing is remembered across a reload: opening one row opens only that row, never its children.
// The set lives for the life of the tab, so moving between pages does not fold the sidebar back up.

import { observable, runInAction } from "mobx";

const openKeys = observable.set<string>();

/** Call from an observer component: it re-renders when the row opens or closes. */
export const isSidebarRowOpen = (key: string): boolean => openKeys.has(key);

export const toggleSidebarRow = (key: string): void => {
  runInAction(() => {
    if (openKeys.has(key)) openKeys.delete(key);
    else openKeys.add(key);
  });
};
