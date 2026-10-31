/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";
import type { TCardResolution } from "@/services/card-links.service";

/** One card as the sidebar tree and the page list show it. Only cards the viewer may see come back. */
export type TCardNode = {
  id: string;
  name: string;
  project_id: string;
  project_identifier: string;
  sequence_id: number;
  /** null when the card has no parent or the parent is hidden from the viewer */
  parent_id: string | null;
  state_color: string | null;
  state_group: string | null;
  updated_at: string;
  /** visible children only */
  child_count: number;
  updated_by_name?: string;
  /** card shortcuts: null for a normal card, else where the shortcut goes (worked out for the viewer) */
  shortcut?: TCardResolution | null;
};

export type TCardPage = {
  results: TCardNode[];
  total: number;
  offset: number;
  limit: number;
  next_offset: number | null;
};

export type TCardAncestor = Pick<
  TCardNode,
  "id" | "name" | "project_id" | "project_identifier" | "sequence_id" | "state_color"
>;

export class CardTreeService extends APIService {
  /** Card-tree requests still on the wire, by URL + params: a second identical ask shares the first. */
  private inFlight = new Map<string, Promise<TCardPage>>();

  constructor() {
    super(API_BASE_URL);
  }

  private treePage(workspaceSlug: string, params: Record<string, string | number | undefined>): Promise<TCardPage> {
    const key = `${workspaceSlug}|${JSON.stringify(params)}`;
    const pending = this.inFlight.get(key);
    if (pending) return pending;
    const request = this.get(`/api/workspaces/${workspaceSlug}/card-tree/`, { params })
      .then((response) => response?.data as TCardPage)
      .catch((error) => {
        throw error?.response?.data;
      })
      .finally(() => this.inFlight.delete(key));
    this.inFlight.set(key, request);
    return request;
  }

  /** Top cards of a project (no parent, or a parent in another project / out of sight). */
  async projectRoots(workspaceSlug: string, projectId: string, offset = 0, limit?: number): Promise<TCardPage> {
    return this.treePage(workspaceSlug, { project_id: projectId, offset, limit });
  }

  /** Visible sub-cards of a card, from any project. */
  async children(workspaceSlug: string, parentId: string, offset = 0, limit?: number): Promise<TCardPage> {
    return this.treePage(workspaceSlug, { parent_id: parentId, offset, limit });
  }

  /** Cards above a card, root first; stops at the first one the viewer may not see. */
  async breadcrumb(workspaceSlug: string, issueId: string): Promise<TCardAncestor[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/cards/${issueId}/breadcrumb/`)
      .then((response) => response?.data?.ancestors ?? [])
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** Every visible card of a project, newest edit first (page list layout). */
  async pageList(workspaceSlug: string, projectId: string, offset = 0, limit?: number): Promise<TCardPage> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/page-list/`, { params: { offset, limit } })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}

export const cardTreeService = new CardTreeService();
