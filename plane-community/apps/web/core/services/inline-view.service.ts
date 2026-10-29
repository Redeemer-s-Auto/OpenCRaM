/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type { TCustomField, TCustomFieldValues, TIssuePriorities } from "@plane/types";
import { APIService } from "@/services/api.service";

/** Where a live view block gets its cards. */
export type TInlineViewSource =
  | { type: "project"; project_id: string }
  | { type: "children"; parent_id: string }
  | { type: "linked"; issue_id: string; field_id: string };

export type TInlineViewFilters = {
  state?: string[];
  priority?: string[];
};

export type TInlineViewQuery = {
  source: TInlineViewSource;
  filters?: TInlineViewFilters;
  search?: string;
  order_by?: string;
  limit?: number;
};

export type TInlineViewCard = {
  id: string;
  sequence_id: number;
  project_id: string;
  project_identifier: string;
  name: string;
  priority: TIssuePriorities | null;
  state_id: string | null;
  parent_id: string | null;
  start_date: string | null;
  target_date: string | null;
  created_at: string;
  updated_at: string;
  assignee_ids: string[];
  label_ids: string[];
  custom_fields: TCustomFieldValues;
};

export type TInlineViewProject = {
  id: string;
  name: string;
  identifier: string;
  states: { id: string; name: string; color: string; group: string }[];
  fields: TCustomField[];
};

export type TInlineViewResult = {
  count: number;
  results: TInlineViewCard[];
  projects: Record<string, TInlineViewProject>;
  people: Record<string, string>;
  labels: Record<string, { id: string; name: string; color: string }>;
};

export class InlineViewService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  /** The cards one block shows. Only cards the viewer may see come back. */
  async query(workspaceSlug: string, body: TInlineViewQuery): Promise<TInlineViewResult> {
    return this.post(`/api/workspaces/${workspaceSlug}/inline-views/query/`, body)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
