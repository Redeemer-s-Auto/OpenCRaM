/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TInlineViewFilters, TInlineViewSource } from "@/services/inline-view.service";

export type TViewLayout = "table" | "board" | "list" | "gallery";

/** Everything a block remembers. Cards are never stored here. */
export type TViewConfig = {
  title?: string;
  source?: TInlineViewSource;
  layout?: TViewLayout;
  filters?: TInlineViewFilters;
  /** board columns: "state", "priority", or a dropdown field id */
  group_by?: string;
  order_by?: string;
  /** custom field ids shown as columns (table) or on cards */
  fields?: string[];
};

export const LAYOUTS: { key: TViewLayout; label: string }[] = [
  { key: "table", label: "Table" },
  { key: "board", label: "Board" },
  { key: "list", label: "List" },
  { key: "gallery", label: "Gallery" },
];

export const PRIORITY_OPTIONS = [
  { key: "urgent", label: "Urgent" },
  { key: "high", label: "High" },
  { key: "medium", label: "Medium" },
  { key: "low", label: "Low" },
  { key: "none", label: "None" },
];
