/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export type TShareTargetType = "member" | "project" | "group" | "workspace";

/** 5 = Can view, 10 = Can comment, 15 = Can edit */
export type TShareLevel = 5 | 10 | 15;

export type TItemShare = {
  target_type: TShareTargetType;
  target_id: string | null;
  name?: string;
  avatar?: string | null;
  level: TShareLevel;
};

export type TItemSharing = {
  restricted: boolean;
  shares: TItemShare[];
  can_manage?: boolean;
};

export type TShareTargets = {
  people: { id: string; name: string; avatar: string | null }[];
  projects: { id: string; name: string }[];
  groups: { id: string; name: string; member_count: number }[];
  is_admin: boolean;
};

export type TAccessGroup = {
  id: string;
  name: string;
  description: string;
  member_ids: string[];
  member_count: number;
  shared_item_count: number | null;
};

export type TSharingItem = { kind: "issue" | "page"; workspaceSlug: string; projectId: string; itemId: string };

function itemUrl({ kind, workspaceSlug, projectId, itemId }: TSharingItem) {
  const segment = kind === "issue" ? "issues" : "pages";
  return `/api/workspaces/${workspaceSlug}/projects/${projectId}/${segment}/${itemId}/permissions/`;
}

export class SharingService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async getSharing(item: TSharingItem): Promise<TItemSharing> {
    return this.get(itemUrl(item))
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async updateSharing(item: TSharingItem, data: TItemSharing): Promise<TItemSharing> {
    return this.put(itemUrl(item), data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async searchTargets(workspaceSlug: string, search: string): Promise<TShareTargets> {
    return this.get(`/api/workspaces/${workspaceSlug}/share-targets/`, { params: { search } })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async listGroups(workspaceSlug: string): Promise<TAccessGroup[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/access-groups/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async createGroup(workspaceSlug: string, data: Partial<TAccessGroup>): Promise<TAccessGroup> {
    return this.post(`/api/workspaces/${workspaceSlug}/access-groups/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async updateGroup(workspaceSlug: string, groupId: string, data: Partial<TAccessGroup>): Promise<TAccessGroup> {
    return this.patch(`/api/workspaces/${workspaceSlug}/access-groups/${groupId}/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async deleteGroup(workspaceSlug: string, groupId: string): Promise<void> {
    return this.delete(`/api/workspaces/${workspaceSlug}/access-groups/${groupId}/`)
      .then(() => undefined)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}

export const sharingService = new SharingService();
