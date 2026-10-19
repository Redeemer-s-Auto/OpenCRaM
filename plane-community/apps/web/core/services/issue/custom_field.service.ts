/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type { TCustomField } from "@plane/types";
// services
import { APIService } from "@/services/api.service";

export class CustomFieldService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private url(workspaceSlug: string, projectId: string) {
    return `/api/workspaces/${workspaceSlug}/projects/${projectId}/custom-fields/`;
  }

  async list(
    workspaceSlug: string,
    projectId: string,
    archived: "false" | "true" | "all" = "false"
  ): Promise<TCustomField[]> {
    return this.get(this.url(workspaceSlug, projectId), { params: { archived } })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async create(workspaceSlug: string, projectId: string, data: Partial<TCustomField>): Promise<TCustomField> {
    return this.post(this.url(workspaceSlug, projectId), data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async update(
    workspaceSlug: string,
    projectId: string,
    fieldId: string,
    data: Partial<TCustomField>
  ): Promise<TCustomField> {
    return this.patch(`${this.url(workspaceSlug, projectId)}${fieldId}/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async archive(workspaceSlug: string, projectId: string, fieldId: string): Promise<TCustomField> {
    return this.post(`${this.url(workspaceSlug, projectId)}${fieldId}/archive/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async restore(workspaceSlug: string, projectId: string, fieldId: string): Promise<TCustomField> {
    return this.delete(`${this.url(workspaceSlug, projectId)}${fieldId}/archive/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Deletes the field and every value in it. The server needs the exact name. */
  async destroy(workspaceSlug: string, projectId: string, fieldId: string, confirmName: string): Promise<void> {
    return this.delete(`${this.url(workspaceSlug, projectId)}${fieldId}/`, { confirm_name: confirmName })
      .then(() => undefined)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async reorder(workspaceSlug: string, projectId: string, fieldIds: string[]): Promise<TCustomField[]> {
    return this.post(`${this.url(workspaceSlug, projectId)}reorder/`, { field_ids: fieldIds })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
