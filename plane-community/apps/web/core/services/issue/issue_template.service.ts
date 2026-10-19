/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
// services
import { APIService } from "@/services/api.service";

export type TIssueTemplateNode = {
  name: string;
  description_html: string;
  priority: string;
  state_id: string | null;
  label_ids: string[];
  custom_fields: Record<string, unknown>;
  sub_items: TIssueTemplateNode[];
};

export type TIssueTemplate = {
  id: string;
  name: string;
  description: string;
  data: TIssueTemplateNode;
  sort_order: number;
  project: string;
  created_at: string;
  updated_at: string;
};

export type TTemplateUseResult = {
  id: string;
  project_id: string;
  sequence_id: number;
  name: string;
  created_count: number;
};

export class IssueTemplateService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private url(workspaceSlug: string, projectId: string) {
    return `/api/workspaces/${workspaceSlug}/projects/${projectId}/work-item-templates/`;
  }

  private unwrap<T>(promise: Promise<{ data: T }>): Promise<T> {
    return promise
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  list(workspaceSlug: string, projectId: string): Promise<TIssueTemplate[]> {
    return this.unwrap(this.get(this.url(workspaceSlug, projectId)));
  }

  update(workspaceSlug: string, projectId: string, id: string, data: Partial<TIssueTemplate>): Promise<TIssueTemplate> {
    return this.unwrap(this.patch(`${this.url(workspaceSlug, projectId)}${id}/`, data));
  }

  remove(workspaceSlug: string, projectId: string, id: string): Promise<void> {
    return this.unwrap(this.delete(`${this.url(workspaceSlug, projectId)}${id}/`));
  }

  use(workspaceSlug: string, projectId: string, id: string, name?: string): Promise<TTemplateUseResult> {
    return this.unwrap(this.post(`${this.url(workspaceSlug, projectId)}${id}/use/`, name ? { name } : {}));
  }

  saveFromIssue(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    data: { name?: string; include_sub_items: boolean }
  ): Promise<TIssueTemplate> {
    return this.unwrap(
      this.post(`/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/save-as-template/`, data)
    );
  }
}

export const issueTemplateService = new IssueTemplateService();
