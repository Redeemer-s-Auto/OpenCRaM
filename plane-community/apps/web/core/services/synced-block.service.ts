/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export type TSyncedBlock = {
  id: string;
  content_html: string;
  version: number;
  can_edit: boolean;
  updated_at: string;
  /** the card the block was made on */
  home: { id: string; name: string; project_id: string; project_identifier: string; sequence_id: number };
  /** list results only: the first words of the text */
  snippet?: string;
};

export class SyncedBlockService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private url(workspaceSlug: string) {
    return `/api/workspaces/${workspaceSlug}/synced-blocks/`;
  }

  /** Blocks the viewer may read. */
  async list(workspaceSlug: string, search = ""): Promise<TSyncedBlock[]> {
    return this.get(this.url(workspaceSlug), { params: { search } })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async retrieve(workspaceSlug: string, id: string): Promise<TSyncedBlock> {
    return this.get(`${this.url(workspaceSlug)}${id}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data ?? { error: "failed" };
      });
  }

  async create(workspaceSlug: string, homeIssueId: string, contentHtml = ""): Promise<TSyncedBlock> {
    return this.post(this.url(workspaceSlug), { home_issue_id: homeIssueId, content_html: contentHtml })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async save(workspaceSlug: string, id: string, contentHtml: string): Promise<TSyncedBlock> {
    return this.patch(`${this.url(workspaceSlug)}${id}/`, { content_html: contentHtml })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async remove(workspaceSlug: string, id: string): Promise<void> {
    return this.delete(`${this.url(workspaceSlug)}${id}/`)
      .then(() => undefined)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
