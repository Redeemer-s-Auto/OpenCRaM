/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type { TLogoProps } from "@plane/types";
import { APIService } from "@/services/api.service";

/** One page as the sidebar tree shows it. Only pages the viewer may see come back. */
export type TPageTreeNode = {
  id: string;
  name: string;
  logo_props: TLogoProps | Record<string, never>;
  /** null when the page has no parent or the parent is hidden from the viewer */
  parent_id: string | null;
  project_id: string;
  access: number;
  owned_by: string;
  sort_order: number;
  updated_at: string;
  /** the page a folder board opens on (the Notion page the folder was made from) */
  is_landing: boolean;
};

/** A page as a link shows it. */
export type TLinkedPage = {
  id: string;
  name: string;
  logo_props: TLogoProps | Record<string, never>;
  project_id: string;
  access: number;
};

/** A board or folder as a link shows it. */
export type TLinkedProject = {
  id: string;
  name: string;
  identifier: string;
  logo_props: TLogoProps | Record<string, never>;
  archived: boolean;
};

/**
 * What one link points at, worked out for the viewer.
 * "hidden": the viewer may not see it (or it does not exist) - nothing else is sent.
 * "removed": it was deleted.
 */
export type TPageResolution = { status: "visible"; page: TLinkedPage } | { status: "hidden" } | { status: "removed" };
export type TProjectResolution = { status: "visible"; project: TLinkedProject } | { status: "hidden" };

export type TPageLinkResolveResponse = {
  pages: Record<string, TPageResolution>;
  projects: Record<string, TProjectResolution>;
};

export type TPageLinkSearchResponse = { pages: TLinkedPage[]; projects: TLinkedProject[] };

export class PageTreeService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  /** Every visible live page of the workspace (or of one board), flat, with parent ids. */
  async tree(workspaceSlug: string, projectId?: string): Promise<TPageTreeNode[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/page-tree/`, {
      params: projectId ? { project_id: projectId } : {},
    })
      .then((response) => response?.data?.results ?? [])
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async resolve(workspaceSlug: string, pages: string[], projects: string[]): Promise<TPageLinkResolveResponse> {
    return this.post(`/api/workspaces/${workspaceSlug}/page-links/resolve/`, { pages, projects })
      .then((response) => response?.data ?? { pages: {}, projects: {} })
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async search(workspaceSlug: string, search: string, limit = 20): Promise<TPageLinkSearchResponse> {
    return this.get(`/api/workspaces/${workspaceSlug}/page-links/search/`, { params: { search, limit } })
      .then((response) => response?.data ?? { pages: [], projects: [] })
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}

export const pageTreeService = new PageTreeService();

/** Where a page opens. */
export const pageHref = (workspaceSlug: string, projectId: string, pageId: string) =>
  `/${workspaceSlug}/projects/${projectId}/pages/${pageId}`;

/** Where a board or folder opens (its cards). */
export const projectHref = (workspaceSlug: string, projectId: string) => `/${workspaceSlug}/projects/${projectId}/issues`;
