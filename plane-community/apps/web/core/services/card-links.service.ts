/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

/** A card as a link shows it. Only sent for cards the viewer may see. */
export type TLinkedCard = {
  id: string;
  name: string;
  sequence_id: number;
  project_id: string;
  project_identifier: string;
  project_name: string;
  state_color: string | null;
  state_group: string | null;
  archived: boolean;
  is_shortcut: boolean;
};

/**
 * What one link points at, worked out for the viewer.
 * "hidden": the viewer may not see it - nothing else is sent.
 * "removed": the card was deleted.
 */
export type TCardResolution = { status: "visible"; card: TLinkedCard } | { status: "hidden" } | { status: "removed" };

export type TBacklink = TLinkedCard & { kind: "link" | "shortcut" };

export class CardLinksService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async resolve(workspaceSlug: string, ids: string[]): Promise<Record<string, TCardResolution>> {
    return this.post(`/api/workspaces/${workspaceSlug}/card-links/resolve/`, { ids })
      .then((response) => response?.data?.results ?? {})
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async search(workspaceSlug: string, search: string, limit = 20): Promise<TLinkedCard[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/card-links/search/`, { params: { search, limit } })
      .then((response) => response?.data?.results ?? [])
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async backlinks(workspaceSlug: string, issueId: string): Promise<TBacklink[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/cards/${issueId}/backlinks/`)
      .then((response) => response?.data?.results ?? [])
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async shortcutInfo(
    workspaceSlug: string,
    issueId: string
  ): Promise<{ is_shortcut: boolean; target: TCardResolution | null }> {
    return this.get(`/api/workspaces/${workspaceSlug}/cards/${issueId}/shortcut/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async projectShortcuts(workspaceSlug: string, projectId: string): Promise<Record<string, TCardResolution>> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/shortcuts/`)
      .then((response) => response?.data?.results ?? {})
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async createShortcut(
    workspaceSlug: string,
    projectId: string,
    targetId: string
  ): Promise<{ id: string; project_id: string; sequence_id: number; target: TCardResolution }> {
    return this.post(`/api/workspaces/${workspaceSlug}/projects/${projectId}/shortcuts/`, { target_id: targetId })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}

export const cardLinksService = new CardLinksService();
