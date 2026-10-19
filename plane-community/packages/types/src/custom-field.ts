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
  | "url";

export type TCustomFieldOption = {
  id: string;
  name: string;
  color: string;
};

export type TCustomFieldSettings = {
  /** date: also store a time */
  include_time?: boolean;
  /** person: allow more than one person */
  multiple?: boolean;
  /** number: places after the point; unset keeps what was typed */
  decimals?: number;
};

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
  created_at: string;
  updated_at: string;
};

/**
 * One value, in API shape:
 * text / long_text / url / select (option id) / date ("YYYY-MM-DD" or ISO date-time) -> string
 * number -> number, money -> whole cents, checkbox -> boolean
 * multi_select / label / person -> string[]
 */
export type TCustomFieldValue = string | number | boolean | string[] | null;

export type TCustomFieldValues = Record<string, TCustomFieldValue>;
