/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * THE ONE SETTING for the Task Lists Hub.
 *
 * `hub` is the identifier of the board that shows the hub; `lists` are the identifiers of the task
 * lists shown on it, top to bottom. To add a new task list later, add its identifier here.
 * Drew's own To Do List (TDL) is deliberately not in it.
 */
export const TASK_LIST_HUB = {
  hub: "TLH",
  lists: ["GSTL", "DSTL", "GTL", "BOTL", "UMTL", "TTL", "L1"],
} as const;

/** How many open items a section shows before "Open the full list". */
export const HUB_SECTION_LIMIT = 100;

/** True when this board is the Task Lists Hub. */
export const isTaskListHub = (identifier: string | undefined | null) =>
  !!identifier && identifier === TASK_LIST_HUB.hub;
