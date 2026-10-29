/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { LucideIcon } from "lucide-react";
import {
  AlignLeft,
  ArrowLeftRight,
  Layers,
  CalendarDays,
  CheckSquare,
  CircleChevronDown,
  Clock,
  DollarSign,
  Hash,
  Link2,
  PencilLine,
  ListChecks,
  Sigma,
  Tag,
  Type,
  User,
  UserCheck,
  UserPlus,
} from "lucide-react";
import type {
  TCustomField,
  TCustomFieldLinkedCard,
  TCustomFieldRollupFunction,
  TCustomFieldType,
  TCustomFieldValue,
} from "@plane/types";

export const CUSTOM_FIELD_TYPES: { type: TCustomFieldType; label: string; icon: LucideIcon; hint: string }[] = [
  { type: "text", label: "Text", icon: Type, hint: "One line of text" },
  { type: "long_text", label: "Long text", icon: AlignLeft, hint: "Several lines of text" },
  { type: "number", label: "Number", icon: Hash, hint: "Any number" },
  { type: "money", label: "Money", icon: DollarSign, hint: "A dollar amount" },
  { type: "date", label: "Date", icon: CalendarDays, hint: "A date, with or without a time" },
  { type: "checkbox", label: "Checkbox", icon: CheckSquare, hint: "Yes or no" },
  { type: "select", label: "Dropdown", icon: CircleChevronDown, hint: "Pick one option from a fixed list" },
  { type: "multi_select", label: "Multi-select", icon: ListChecks, hint: "Pick many options from a fixed list" },
  { type: "label", label: "Label", icon: Tag, hint: "Colored tags; anyone can add a new tag on a card" },
  { type: "person", label: "Person", icon: User, hint: "A member of this workspace" },
  { type: "url", label: "Link", icon: Link2, hint: "A web address" },
  { type: "formula", label: "Formula", icon: Sigma, hint: "Worked out from other fields, like Notion formulas" },
  { type: "relation", label: "Relation", icon: ArrowLeftRight, hint: "Link to cards on any board, like Notion relations" },
  { type: "rollup", label: "Rollup", icon: Layers, hint: "Count, sum or show values from linked cards" },
  { type: "created_time", label: "Created time", icon: Clock, hint: "When the card was made. Filled in for you" },
  { type: "last_edited_time", label: "Last edited time", icon: PencilLine, hint: "When the card was last changed. Filled in for you" },
  { type: "created_by", label: "Created by", icon: UserPlus, hint: "Who made the card. Filled in for you" },
  { type: "last_edited_by", label: "Last edited by", icon: UserCheck, hint: "Who last changed the card. Filled in for you" },
];

/** Filled in by the server from the card itself. Shown and sorted, never typed in. */
export const AUDIT_FIELD_TYPES: TCustomFieldType[] = ["created_time", "last_edited_time", "created_by", "last_edited_by"];
export const isAuditField = (field: TCustomField) => AUDIT_FIELD_TYPES.includes(field.field_type);
export const isAuditPersonField = (field: TCustomField) =>
  field.field_type === "created_by" || field.field_type === "last_edited_by";

/** Relation and rollup values depend on who is looking; they cannot be sorted or filtered. */
export const LINKED_FIELD_TYPES: TCustomFieldType[] = ["relation", "rollup"];
export const isLinkedField = (field: TCustomField) => LINKED_FIELD_TYPES.includes(field.field_type);

export const ROLLUP_FUNCTIONS: {
  value: TCustomFieldRollupFunction;
  label: string;
  /** what the rolled-up property must be: none, any, numeric, date, checkbox */
  needs: "none" | "any" | "numeric" | "date" | "checkbox";
}[] = [
  { value: "count", label: "Count linked cards", needs: "none" },
  { value: "count_not_empty", label: "Count filled in", needs: "any" },
  { value: "count_empty", label: "Count empty", needs: "any" },
  { value: "sum", label: "Sum", needs: "numeric" },
  { value: "avg", label: "Average", needs: "numeric" },
  { value: "min", label: "Smallest", needs: "numeric" },
  { value: "max", label: "Largest", needs: "numeric" },
  { value: "earliest", label: "Earliest date", needs: "date" },
  { value: "latest", label: "Latest date", needs: "date" },
  { value: "unique", label: "Show unique values", needs: "any" },
  { value: "percent_checked", label: "Percent checked", needs: "checkbox" },
];

/** Built-in card properties a rollup can read, with what they behave as. */
export const ROLLUP_BUILT_INS: { value: string; label: string; kind: "any" | "date" }[] = [
  { value: "@title", label: "Title", kind: "any" },
  { value: "@state", label: "State", kind: "any" },
  { value: "@priority", label: "Priority", kind: "any" },
  { value: "@start_date", label: "Start date", kind: "date" },
  { value: "@due_date", label: "Due date", kind: "date" },
];

/** Whether a field on the linked board can be rolled up with a function that needs ``needs``. */
export const fitsRollup = (field: TCustomField, needs: (typeof ROLLUP_FUNCTIONS)[number]["needs"]) => {
  if (isLinkedField(field)) return false;
  const type = effectiveFieldType(field);
  if (needs === "any") return true;
  if (needs === "numeric") return type === "number" || type === "money";
  if (needs === "date") return type === "date";
  if (needs === "checkbox") return type === "checkbox";
  return false;
};

/** Linked cards in a relation value. Ids alone (just picked, before the server answers) have no name yet. */
export const linkedCards = (value: TCustomFieldValue | undefined): TCustomFieldLinkedCard[] =>
  Array.isArray(value)
    ? (value as unknown[])
        .filter((item): item is TCustomFieldLinkedCard => typeof item === "object" && item !== null && "id" in item)
    : [];

export const OPTION_FIELD_TYPES: TCustomFieldType[] = ["select", "multi_select", "label"];

export const getFieldTypeDetails = (type: TCustomFieldType) =>
  CUSTOM_FIELD_TYPES.find((t) => t.type === type) ?? CUSTOM_FIELD_TYPES[0];

export const DEFAULT_OPTION_COLORS = [
  "#EE0000",
  "#F59E0B",
  "#10B981",
  "#3B82F6",
  "#8B5CF6",
  "#EC4899",
  "#6B7280",
  "#14B8A6",
];

/** 121400 -> "$1,214.00" */
export const formatMoney = (cents: number | null | undefined): string => {
  if (cents === null || cents === undefined || Number.isNaN(cents)) return "";
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(Math.trunc(cents));
  const dollars = Math.floor(abs / 100).toLocaleString("en-US");
  return `${sign}$${dollars}.${String(abs % 100).padStart(2, "0")}`;
};

/** "$1,214.5" -> 121450. Returns undefined when the text is not an amount. */
export const parseMoney = (text: string): number | null | undefined => {
  const cleaned = text.replace(/[$,\s]/g, "");
  if (cleaned === "") return null;
  if (!/^-?\d+(\.\d{0,2})?$/.test(cleaned)) return undefined;
  const negative = cleaned.startsWith("-");
  const [whole, fraction = ""] = cleaned.replace("-", "").split(".");
  const cents = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
  return negative ? -cents : cents;
};

/** "1,234.5" -> 1234.5. Returns undefined when the text is not a number. */
export const parseNumber = (text: string): number | null | undefined => {
  const cleaned = text.replace(/[,\s]/g, "");
  if (cleaned === "") return null;
  if (!/^-?\d*(\.\d+)?$/.test(cleaned) || cleaned === "-") return undefined;
  return Number(cleaned);
};

/** The type a value behaves as. A formula behaves as its result type. */
export const effectiveFieldType = (field: TCustomField): TCustomFieldType => {
  if (field.field_type !== "formula") return field.field_type;
  const result = field.settings?.result_type ?? "number";
  return result === "list" || result === "percent" ? "number" : result;
};

export const FORMULA_RESULT_TYPES: { value: NonNullable<TCustomField["settings"]["result_type"]>; label: string }[] = [
  { value: "number", label: "Number" },
  { value: "money", label: "Money" },
  { value: "text", label: "Text" },
  { value: "date", label: "Date" },
  { value: "checkbox", label: "Checkbox" },
];

export const isEmptyValue = (value: TCustomFieldValue | undefined) =>
  value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);

/** Plain text for a value, used in table cells and tooltips. People are resolved by the caller. */
export const formatCustomFieldValue = (
  field: TCustomField,
  value: TCustomFieldValue | undefined,
  getPersonName?: (userId: string) => string | undefined
): string => {
  if (isEmptyValue(value)) return "";
  if (field.field_type === "relation") {
    return linkedCards(value)
      .map((card) => card.name)
      .join(", ");
  }
  if (field.field_type === "rollup") {
    switch (field.settings?.result_type) {
      case "money":
        return formatMoney(value as number);
      case "percent":
        return `${(value as number).toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;
      case "list":
        return Array.isArray(value) ? (value as string[]).join(", ") : String(value);
      case "date": {
        const raw = String(value);
        if (raw.includes("T")) {
          const date = new Date(raw);
          return Number.isNaN(date.getTime()) ? raw : date.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
        }
        const [y, m, d] = raw.split("-").map(Number);
        return new Date(y, m - 1, d).toLocaleDateString("en-US", { dateStyle: "medium" });
      }
      default:
        return typeof value === "number" ? value.toLocaleString("en-US", { maximumFractionDigits: 6 }) : String(value);
    }
  }
  if (field.field_type === "created_time" || field.field_type === "last_edited_time") {
    const date = new Date(String(value));
    return Number.isNaN(date.getTime())
      ? String(value)
      : date.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
  }
  if (isAuditPersonField(field)) {
    return (Array.isArray(value) ? (value as string[]) : [])
      .map((id) => getPersonName?.(id))
      .filter(Boolean)
      .join(", ");
  }
  switch (effectiveFieldType(field)) {
    case "money":
      return formatMoney(value as number);
    case "number":
      return (value as number).toLocaleString("en-US", { maximumFractionDigits: 6 });
    case "checkbox":
      return value ? "Yes" : "No";
    case "date": {
      const raw = value as string;
      if (field.settings?.include_time || raw.includes("T")) {
        const date = new Date(raw);
        return Number.isNaN(date.getTime())
          ? raw
          : date.toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
      }
      const [y, m, d] = raw.split("-").map(Number);
      return new Date(y, m - 1, d).toLocaleDateString("en-US", { dateStyle: "medium" });
    }
    case "select":
    case "multi_select":
    case "label": {
      const ids = Array.isArray(value) ? value : [value as string];
      return ids
        .map((id) => field.options.find((o) => o.id === id)?.name)
        .filter(Boolean)
        .join(", ");
    }
    case "person":
      return (value as string[])
        .map((id) => getPersonName?.(id))
        .filter(Boolean)
        .join(", ");
    default:
      return String(value);
  }
};

/** Local "YYYY-MM-DDTHH:mm" for <input type="datetime-local"> from an ISO string. */
export const toLocalDateTimeInput = (iso: string | null | undefined) => {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(
    date.getMinutes()
  )}`;
};
