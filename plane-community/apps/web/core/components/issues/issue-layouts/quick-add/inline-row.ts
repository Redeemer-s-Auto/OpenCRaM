/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TIssue } from "@plane/types";
import type { TRowAddPlacement } from "../row-add-button";

/** The gap the server leaves between cards (Issue.sort_order default and step). */
const SORT_ORDER_GAP = 65535;

/**
 * A sort_order one gap past the last of ``issues``: the end of a list ordered by sort_order.
 * (The server alone would place a new card at the end of its own state only.)
 */
export const endOfListSortOrder = (issues: (TIssue | undefined)[]): number => {
  const last = issues.reduce<number | undefined>((max, issue) => {
    const order = issue?.sort_order;
    if (typeof order !== "number" || !Number.isFinite(order)) return max;
    return max === undefined || order > max ? order : max;
  }, undefined);
  return (last ?? 0) + SORT_ORDER_GAP;
};

/**
 * Two rows with the SAME sort_order have no room between them: a card put "between" them gets their
 * value too and lands on either side after a reload. Before a card is added next to ``row``, the run of
 * rows sharing the boundary value is spread out evenly up to the next distinct value (only those rows'
 * sort_order changes, so the order on screen stays the same). Returns the sort_order writes made.
 */
export const spreadSortOrderTies = async (
  row: TIssue,
  placement: TRowAddPlacement,
  siblingIds: string[],
  getIssueById: (issueId: string) => TIssue | undefined,
  save: (issueId: string, sortOrder: number) => Promise<void>
): Promise<number> => {
  const index = siblingIds.indexOf(row.id);
  if (index < 0) return 0;
  // the boundary: the row and the neighbour on the side the card goes
  const first = placement === "below" ? index : index - 1;
  const base = first >= 0 ? getIssueById(siblingIds[first])?.sort_order : undefined;
  const next = getIssueById(siblingIds[first + 1] ?? "")?.sort_order;
  if (typeof base !== "number" || typeof next !== "number" || next > base) return 0;
  // the run of rows after the boundary that sit at (or below) the same value
  let end = first + 1;
  while (end < siblingIds.length && (getIssueById(siblingIds[end])?.sort_order ?? Infinity) <= base) end += 1;
  const after = getIssueById(siblingIds[end] ?? "")?.sort_order;
  const room = typeof after === "number" && after > base ? after - base : SORT_ORDER_GAP;
  const step = room / (end - first + 1);
  const writes: Promise<void>[] = [];
  for (let k = first + 1; k < end; k += 1) writes.push(save(siblingIds[k], base + step * (k - first)));
  await Promise.all(writes);
  return writes.length;
};

/**
 * Pre-filled values for a card added right above or below ``row`` with the row's + button.
 *
 * The new card sits beside the row it was added from: same state, and the same priority, labels,
 * assignees, cycle and modules, so it passes whatever filters the row passed (a view's filters are
 * what put the row on screen). ``groupData`` is the group's own quick-add data (the default state and
 * the group value); the row's values win over it. ``siblingIds`` is the list the row is shown in, in
 * order, used to put ``sort_order`` midway between the row and its neighbour (one gap past the end).
 */
export const buildInlineAddData = (
  row: TIssue,
  placement: TRowAddPlacement,
  siblingIds: string[],
  getIssueById: (issueId: string) => TIssue | undefined,
  groupData: Partial<TIssue> = {}
): Partial<TIssue> => {
  const index = siblingIds.indexOf(row.id);
  const neighbourId = index < 0 ? undefined : siblingIds[placement === "below" ? index + 1 : index - 1];
  const neighbour = neighbourId ? getIssueById(neighbourId) : undefined;
  const rowOrder = row.sort_order ?? SORT_ORDER_GAP;
  const sort_order =
    neighbour && typeof neighbour.sort_order === "number"
      ? (rowOrder + neighbour.sort_order) / 2
      : placement === "below"
        ? rowOrder + SORT_ORDER_GAP
        : rowOrder - SORT_ORDER_GAP;

  return {
    ...groupData,
    state_id: row.state_id,
    priority: row.priority ?? "none",
    label_ids: row.label_ids ?? [],
    assignee_ids: row.assignee_ids ?? [],
    cycle_id: row.cycle_id ?? null,
    module_ids: row.module_ids ?? [],
    sort_order,
  };
};
