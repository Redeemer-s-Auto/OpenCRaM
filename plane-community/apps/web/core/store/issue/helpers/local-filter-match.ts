/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { IState, TIssue } from "@plane/types";

/**
 * Judge, in the browser, whether a card still fits a list's rich filter after an edit.
 *
 * The server does the real filtering. This only answers the few conditions a quick edit
 * on a row can change (state, priority, assignees, labels, a custom field box or option),
 * so a card that no longer fits (Active -> Completed, Completed -> Checked) can leave the
 * list at once, without reloading the list.
 *
 * Returns true / false when every condition that decides the answer is understood, and
 * undefined when it cannot tell. Callers keep the card on undefined (never a wrong removal).
 */

type TExpression = Record<string, unknown>;
type TContext = { stateMap: Record<string, IState> | undefined };

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const toList = (raw: unknown): string[] => {
  const items = Array.isArray(raw) ? raw : String(raw ?? "").split(",");
  return items.map((item) => String(item).trim()).filter((item) => item !== "");
};

const isBoolish = (raw: unknown) =>
  typeof raw === "boolean" || ["true", "false"].includes(String(raw).trim().toLowerCase());

const asBool = (raw: unknown) =>
  typeof raw === "boolean" ? raw : ["true", "1", "yes"].includes(String(raw).trim().toLowerCase());

/** `in` / `exact` against one value or a list of values (any one matching is enough). */
const matchIds = (have: unknown, lookup: string, raw: unknown): boolean | undefined => {
  if (lookup !== "in" && lookup !== "exact") return undefined;
  const wanted = new Set(toList(raw).map((v) => v.toLowerCase()));
  if (wanted.size === 0) return undefined;
  const values = (Array.isArray(have) ? have : have === null || have === undefined ? [] : [have]).map((v) =>
    String(v).toLowerCase()
  );
  return values.some((v) => wanted.has(v));
};

const matchCustomField = (issue: TIssue, fieldId: string, lookup: string, raw: unknown): boolean | undefined => {
  const value = (issue.custom_fields as Record<string, unknown> | undefined)?.[fieldId];
  // Checkbox: the server's rule is "ticked" vs "not ticked" (no value counts as not ticked).
  if (lookup === "exact" && isBoolish(raw) && (value === undefined || value === null || typeof value === "boolean"))
    return (value === true) === asBool(raw);
  if (lookup === "isnull" && isBoolish(raw)) {
    const empty = value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length);
    return empty === asBool(raw);
  }
  // Option / person / label ids only: text and numbers compare differently on the server.
  const ids = toList(raw);
  const valueIsIds = Array.isArray(value)
    ? value.every((v) => UUID_RE.test(String(v)))
    : value === undefined || value === null || UUID_RE.test(String(value));
  if (ids.length && ids.every((id) => UUID_RE.test(id)) && valueIsIds) return matchIds(value, lookup, raw);
  return undefined;
};

const matchCondition = (issue: TIssue, key: string, raw: unknown, ctx: TContext): boolean | undefined => {
  const split = key.lastIndexOf("__");
  const property = split > 0 ? key.slice(0, split) : key;
  const lookup = split > 0 ? key.slice(split + 2) : "exact";

  if (property.startsWith("customfield_"))
    return matchCustomField(issue, property.slice("customfield_".length), lookup, raw);

  switch (property) {
    case "state_group": {
      const group = issue.state_id ? ctx.stateMap?.[issue.state_id]?.group : undefined;
      return group ? matchIds(group, lookup, raw) : undefined;
    }
    case "state_id":
    case "state":
      return matchIds(issue.state_id, lookup, raw);
    case "priority":
      return matchIds(issue.priority ?? "none", lookup, raw);
    case "assignee_id":
      return matchIds(issue.assignee_ids, lookup, raw);
    case "label_id":
      return matchIds(issue.label_ids, lookup, raw);
    default:
      return undefined;
  }
};

const evaluate = (issue: TIssue, expression: unknown, ctx: TContext): boolean | undefined => {
  if (!expression || typeof expression !== "object" || Array.isArray(expression)) return undefined;
  const entries = Object.entries(expression as TExpression);
  if (entries.length === 0) return true;

  const results: (boolean | undefined)[] = entries.map(([key, value]) => {
    if (key === "and" || key === "or") {
      if (!Array.isArray(value)) return undefined;
      const parts = value.map((part) => evaluate(issue, part, ctx));
      if (key === "and") {
        if (parts.includes(false)) return false;
        return parts.includes(undefined) ? undefined : true;
      }
      if (parts.includes(true)) return true;
      return parts.includes(undefined) ? undefined : false;
    }
    if (key === "not") {
      const inner = evaluate(issue, value, ctx);
      return inner === undefined ? undefined : !inner;
    }
    return matchCondition(issue, key, value, ctx);
  });
  // Several keys in one object are ANDed (the server reads them the same way).
  if (results.includes(false)) return false;
  return results.includes(undefined) ? undefined : true;
};

export const issueMatchesRichFilters = (
  issue: TIssue | undefined,
  richFilters: unknown,
  stateMap: Record<string, IState> | undefined
): boolean | undefined => {
  if (!issue) return undefined;
  if (!richFilters || (typeof richFilters === "object" && Object.keys(richFilters).length === 0)) return true;
  return evaluate(issue, richFilters, { stateMap });
};
