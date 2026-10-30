/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type TCustomFieldType =
  | "text"
  | "long_text"
  | "number"
  | "money"
  | "date"
  | "checkbox"
  | "select"
  | "multi_select"
  | "label"
  | "person"
  | "url"
  | "formula"
  | "relation"
  | "rollup"
  | "created_time"
  | "last_edited_time"
  | "created_by"
  | "last_edited_by"
  // Short names the server turns into number, text and dropdown fields with a format (see settings.format).
  | "percent"
  | "phone"
  | "email"
  | "status";

/** What a number, text or dropdown field is shown and checked as. Set when the field is made. */
export type TCustomFieldFormat = "percent" | "phone" | "email" | "status";

/** Where a status option sits: not started, under way, or finished. */
export type TCustomFieldStatusGroup = "todo" | "in_progress" | "complete";

export type TCustomFieldOption = {
  id: string;
  name: string;
  color: string;
  /** status fields only */
  group?: TCustomFieldStatusGroup;
};

export type TCustomFieldSettings = {
  /** number: percent. text: phone or email. dropdown: status. Fixed after the field is made. */
  format?: TCustomFieldFormat;
  /** date: also store a time */
  include_time?: boolean;
  /** person: allow more than one person */
  multiple?: boolean;
  /** number: places after the point; unset keeps what was typed */
  decimals?: number;
  /** formula: the formula text, for example prop("Amount") * 1.0825 */
  expression?: string;
  /** formula: what the result is shown and sorted as. rollup: set by the server. */
  result_type?: TCustomFieldFormulaResult | TCustomFieldRollupResult;
  /** relation: the board the linked cards are on (fixed after create) */
  target_project_id?: string;
  /** relation: also show the links on the target board, in a mirror field */
  two_way?: boolean;
  /** relation: name for the mirror field, only sent when turning two-way on */
  mirror_name?: string;
  /** relation (server-owned): the other field of a two-way pair */
  mirror_field_id?: string | null;
  /** relation (server-owned): true on the mirror side */
  is_mirror?: boolean;
  /** rollup: the relation field on this board whose linked cards are summed up */
  relation_field_id?: string;
  /** rollup: a field id on the linked board, or a built-in like "@due_date" */
  target_field_id?: string | null;
  /** rollup: the calculation */
  function?: TCustomFieldRollupFunction;
};

export type TCustomFieldRollupFunction =
  | "count"
  | "count_empty"
  | "count_not_empty"
  | "sum"
  | "avg"
  | "min"
  | "max"
  | "earliest"
  | "latest"
  | "unique"
  | "percent_checked";

export type TCustomFieldRollupResult = "number" | "money" | "date" | "list" | "percent";

/** One linked card as the server shows it (only cards the viewer may see). */
export type TCustomFieldLinkedCard = {
  id: string;
  name: string;
  sequence_id: number;
  project_id: string;
  project_identifier: string;
};

export type TCustomFieldFormulaResult = "number" | "money" | "text" | "date" | "checkbox";

export type TCustomField = {
  id: string;
  name: string;
  description: string;
  field_type: TCustomFieldType;
  options: TCustomFieldOption[];
  settings: TCustomFieldSettings;
  sort_order: number;
  archived_at: string | null;
  project: string;
  workspace: string;
  /** Set by the server for fields it made itself, like the task list "Seen" box (task_list / seen). */
  external_source?: string | null;
  external_id?: string | null;
  created_at: string;
  updated_at: string;
};

/**
 * One value, in API shape:
 * text / long_text / url / select (option id) / date ("YYYY-MM-DD" or ISO date-time) -> string
 * number -> number, money -> whole cents, checkbox -> boolean
 * multi_select / label / person -> string[]
 * relation -> linked cards (write: card ids or the same objects)
 * rollup -> number, whole cents, date string, string[] or percent, per settings.result_type
 */
export type TCustomFieldValue = string | number | boolean | string[] | TCustomFieldLinkedCard[] | null;

export type TCustomFieldValues = Record<string, TCustomFieldValue>;
