/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type { IProjectView, TTaskListViewsResponse } from "@plane/types";
import { APIService } from "@/services/api.service";
// types
// helpers

/**
 * One GET of a view's details shared by everyone who asks within a few seconds. Opening a view asks for it
 * twice (the page and its filters), and the project layout starts it early, beside the board's own details,
 * so a cold load waits for one round trip less. Any write through this service drops the shared copy.
 */
const SHARED_VIEW_DETAILS_MS = 5000;
const sharedViewDetails = new Map<string, { promise: Promise<IProjectView>; startedAt: number }>();
const forgetSharedViewDetails = () => sharedViewDetails.clear();

export class ViewService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  /** Starts the view's GET now so the view page finds it in flight. Errors surface to the page's own call. */
  prefetchViewDetails(workspaceSlug: string, projectId: string, viewId: string): void {
    this.getViewDetails(workspaceSlug, projectId, viewId).catch(() => undefined);
  }

  /** Adds (or refreshes) the Seen checkbox and the Active / Completed / Checked views. Admins only. */
  async addTaskListViews(workspaceSlug: string, projectId: string): Promise<TTaskListViewsResponse> {
    forgetSharedViewDetails();
    return this.post(`/api/workspaces/${workspaceSlug}/projects/${projectId}/views/task-list/`, {})
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async createView(workspaceSlug: string, projectId: string, data: Partial<IProjectView>): Promise<any> {
    forgetSharedViewDetails();
    return this.post(`/api/workspaces/${workspaceSlug}/projects/${projectId}/views/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async patchView(workspaceSlug: string, projectId: string, viewId: string, data: Partial<IProjectView>): Promise<any> {
    forgetSharedViewDetails();
    return this.patch(`/api/workspaces/${workspaceSlug}/projects/${projectId}/views/${viewId}/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async deleteView(workspaceSlug: string, projectId: string, viewId: string): Promise<any> {
    forgetSharedViewDetails();
    return this.delete(`/api/workspaces/${workspaceSlug}/projects/${projectId}/views/${viewId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async getViews(workspaceSlug: string, projectId: string): Promise<IProjectView[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/views/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async getViewDetails(workspaceSlug: string, projectId: string, viewId: string): Promise<IProjectView> {
    const url = `/api/workspaces/${workspaceSlug}/projects/${projectId}/views/${viewId}/`;
    const shared = sharedViewDetails.get(url);
    if (shared && Date.now() - shared.startedAt < SHARED_VIEW_DETAILS_MS) return shared.promise;
    const promise = this.get(url)
      .then((response) => response?.data)
      .catch((error) => {
        sharedViewDetails.delete(url);
        throw error?.response?.data;
      });
    sharedViewDetails.set(url, { promise, startedAt: Date.now() });
    return promise;
  }

  async getViewIssues(workspaceSlug: string, projectId: string, viewId: string): Promise<any> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/views/${viewId}/issues/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async addViewToFavorites(
    workspaceSlug: string,
    projectId: string,
    data: {
      view: string;
    }
  ): Promise<any> {
    forgetSharedViewDetails();
    return this.post(`/api/workspaces/${workspaceSlug}/projects/${projectId}/user-favorite-views/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async removeViewFromFavorites(workspaceSlug: string, projectId: string, viewId: string): Promise<any> {
    forgetSharedViewDetails();
    return this.delete(`/api/workspaces/${workspaceSlug}/projects/${projectId}/user-favorite-views/${viewId}/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
