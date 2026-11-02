/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

/**
 * Notes never shows the word "Backlog": every card starts in Plane's default "Backlog" state, so on a
 * task list the word says nothing and reads as "this was put aside". Display only; the state itself
 * and every filter on it are unchanged.
 */
export const isPlainBacklogState = (state: { name?: string | null; group?: string | null } | undefined | null) =>
  !!state && state.group === "backlog" && (state.name ?? "").trim().toLowerCase() === "backlog";

/** The state's name as Notes shows it: blank for the default "Backlog" state. */
export const stateDisplayName = (state: { name?: string | null; group?: string | null } | undefined | null) =>
  isPlainBacklogState(state) ? "" : (state?.name ?? "");

/** Heading of a group (board column, list group) for cards in the default "Backlog" state, or its group. */
export const BACKLOG_GROUP_LABEL = "No status";
