/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * Undo / redo for every change made in Notes (cards, properties, views, pages).
 *
 * Plain TypeScript, no React and no MobX, so it can be unit tested on its own.
 *
 * - One stack per screen ("scope", the route path), the last `limit` actions each.
 * - A store method that makes a real change calls `undoStack.record(...)` after the server
 *   accepted it, with an undo and a redo that write the OLD / NEW values back through the
 *   same store method. While an undo or redo runs, `canRecord()` is false, so the store
 *   method it calls does not push a new entry.
 * - A card or view that is deleted and then made again gets a new id. `alias(old, new)`
 *   records that, and every entry looks its id up with `resolve(id)` when it runs, so the
 *   older entries keep pointing at the right row.
 */

export type TUndoEntry = {
  /** Short words for the toast, e.g. "Status change" or "New row". */
  label: string;
  undo: () => unknown;
  redo: () => unknown;
};

export type TUndoResult =
  | { status: "done"; label: string }
  | { status: "empty" }
  | { status: "busy" }
  | { status: "failed"; label: string; error: unknown };

type TScope = { undo: TUndoEntry[]; redo: TUndoEntry[] };

export const DEFAULT_UNDO_LIMIT = 50;
export const DEFAULT_SCOPE_LIMIT = 30;
const GLOBAL_SCOPE = "global";

export class UndoStack {
  private scopes = new Map<string, TScope>();
  private scopeKey = GLOBAL_SCOPE;
  private replaying = 0;
  private aliases = new Map<string, string>();
  private listeners = new Set<() => void>();

  constructor(
    readonly limit: number = DEFAULT_UNDO_LIMIT,
    readonly scopeLimit: number = DEFAULT_SCOPE_LIMIT
  ) {}

  /** The screen new entries go to and Ctrl+Z works on. */
  get scope(): string {
    return this.scopeKey;
  }

  setScope(key: string | null | undefined) {
    this.scopeKey = key || GLOBAL_SCOPE;
    // keep the most recently used screen last, and drop the oldest screens past the limit
    const existing = this.scopes.get(this.scopeKey);
    if (existing) {
      this.scopes.delete(this.scopeKey);
      this.scopes.set(this.scopeKey, existing);
    }
    while (this.scopes.size > this.scopeLimit) {
      const oldest = this.scopes.keys().next().value;
      if (oldest === undefined) break;
      this.scopes.delete(oldest);
    }
  }

  /** False while an undo or redo runs: the store methods it calls must not record. */
  canRecord(): boolean {
    return this.replaying === 0;
  }

  isBusy(): boolean {
    return this.replaying > 0;
  }

  canUndo(): boolean {
    return (this.scopes.get(this.scopeKey)?.undo.length ?? 0) > 0;
  }

  canRedo(): boolean {
    return (this.scopes.get(this.scopeKey)?.redo.length ?? 0) > 0;
  }

  /** Adds a finished action to the current screen. A new action empties the redo list. */
  record(entry: TUndoEntry) {
    if (!this.canRecord()) return;
    const scope = this.current();
    scope.undo.push(entry);
    if (scope.undo.length > this.limit) scope.undo.splice(0, scope.undo.length - this.limit);
    scope.redo = [];
    this.emit();
  }

  undo(): Promise<TUndoResult> {
    return this.replay("undo");
  }

  redo(): Promise<TUndoResult> {
    return this.replay("redo");
  }

  /** A row (or view) that was made again under a new id. */
  alias(oldId: string, newId: string) {
    if (!oldId || !newId || oldId === newId) return;
    this.aliases.set(oldId, newId);
  }

  /** The id a row has now, following every remake since the entry was recorded. */
  resolve(id: string): string {
    let current = id;
    const seen = new Set<string>();
    while (this.aliases.has(current) && !seen.has(current)) {
      seen.add(current);
      current = this.aliases.get(current) as string;
    }
    return current;
  }

  /** Empties every screen (sign out, workspace switch). */
  clear() {
    this.scopes.clear();
    this.aliases.clear();
    this.emit();
  }

  /** Called after every change to the stacks; returns the unsubscribe. */
  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private current(): TScope {
    let scope = this.scopes.get(this.scopeKey);
    if (!scope) {
      scope = { undo: [], redo: [] };
      this.scopes.set(this.scopeKey, scope);
      this.setScope(this.scopeKey);
    }
    return scope;
  }

  private async replay(direction: "undo" | "redo"): Promise<TUndoResult> {
    // one at a time: a held-down key must not run two undos on top of each other
    if (this.replaying > 0) return { status: "busy" };
    const scope = this.scopes.get(this.scopeKey);
    const from = direction === "undo" ? scope?.undo : scope?.redo;
    const entry = from?.pop();
    if (!scope || !entry) return { status: "empty" };
    this.replaying += 1;
    try {
      await (direction === "undo" ? entry.undo() : entry.redo());
      (direction === "undo" ? scope.redo : scope.undo).push(entry);
      return { status: "done", label: entry.label };
    } catch (error) {
      // the server refused it (row gone, no permission): drop the entry rather than retry forever
      return { status: "failed", label: entry.label, error };
    } finally {
      this.replaying -= 1;
      this.emit();
    }
  }

  private emit() {
    this.listeners.forEach((listener) => {
      try {
        listener();
      } catch {
        // a listener must not break undo
      }
    });
  }
}

/** The one stack the app uses. */
export const undoStack = new UndoStack();

/**
 * Old values of `keys` on `before`, for writing back on undo. A key the row did not have
 * comes back as null so the server clears it.
 */
export const pickOldValues = <T extends object>(before: T, keys: string[]): Record<string, unknown> => {
  const out: Record<string, unknown> = {};
  keys.forEach((key) => {
    const value = (before as unknown as Record<string, unknown>)[key];
    out[key] = value === undefined ? null : deepCopy(value);
  });
  return out;
};

/** JSON-safe deep copy for the plain values stored on rows and views. */
export const deepCopy = <T>(value: T): T => {
  if (value === null || value === undefined || typeof value !== "object") return value;
  try {
    return JSON.parse(JSON.stringify(value)) as T;
  } catch {
    return value;
  }
};

/** True when two plain values hold the same data. */
export const sameValue = (a: unknown, b: unknown): boolean => {
  if (a === b) return true;
  try {
    return JSON.stringify(a ?? null) === JSON.stringify(b ?? null);
  } catch {
    return false;
  }
};

/** Toast words for a board or view display change (layout, grouping, sort, shown properties). */
export const displayChangeLabel = (kind: "display_filters" | "display_properties", keys: string[]): string => {
  if (kind === "display_properties") return "Show / hide property";
  if (keys.includes("layout")) return "Layout change";
  if (keys.includes("group_by") || keys.includes("sub_group_by")) return "Grouping change";
  if (keys.includes("order_by")) return "Sort change";
  return "Display change";
};

const ISSUE_KEY_LABELS: Record<string, string> = {
  name: "Rename",
  state_id: "Status change",
  priority: "Priority change",
  target_date: "Due date change",
  start_date: "Start date change",
  assignee_ids: "Assignee change",
  label_ids: "Label change",
  sort_order: "Move",
  parent_id: "Parent change",
  estimate_point: "Estimate change",
  is_divider: "Divider change",
  description_html: "Description change",
  cycle_id: "Cycle change",
  module_ids: "Module change",
  type_id: "Type change",
};

/**
 * Toast words for a card edit. `fieldName` turns a custom field id into its name
 * ("Seen", "Done", ...).
 */
export const issueChangeLabel = (
  data: Record<string, unknown>,
  before: Record<string, unknown> | undefined,
  fieldName: (fieldId: string) => string | undefined
): string => {
  const keys = Object.keys(data);
  if (keys.includes("sort_order")) return "Move";
  if (keys.length === 1 && keys[0] === "custom_fields") {
    const next = (data.custom_fields ?? {}) as Record<string, unknown>;
    const prev = ((before?.custom_fields ?? {}) as Record<string, unknown>) || {};
    const changed = Object.keys({ ...prev, ...next }).filter((id) => !sameValue(prev[id], next[id]));
    if (changed.length === 1) {
      const name = fieldName(changed[0]);
      return name ? `${name} change` : "Property change";
    }
    return "Property change";
  }
  if (keys.length === 1 && ISSUE_KEY_LABELS[keys[0]]) return ISSUE_KEY_LABELS[keys[0]];
  return "Card edit";
};
