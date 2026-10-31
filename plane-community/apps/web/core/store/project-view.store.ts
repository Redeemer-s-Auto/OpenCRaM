/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { set } from "lodash-es";
import { observable, action, makeObservable, runInAction, computed } from "mobx";
import { computedFn } from "mobx-utils";
// types
import type { IProjectView, TTaskListViewsResponse, TViewFilters } from "@plane/types";
import { EIssuesStoreType } from "@plane/types";
// constants
// helpers
import { getValidatedViewFilters, getViewName, orderViews, shouldFilterView } from "@plane/utils";
// services
import { ViewService } from "@/services/view.service";
// undo
import { deepCopy, pickOldValues, sameValue, undoStack } from "./undo/undo-stack";
// store
import type { CoreRootStore } from "./root.store";

export interface IProjectViewStore {
  //Loaders
  loader: boolean;
  fetchedMap: Record<string, boolean>;
  // observables
  viewMap: Record<string, IProjectView>;
  filters: TViewFilters;
  // computed
  projectViewIds: string[] | null;
  // computed actions
  getProjectViews: (projectId: string) => IProjectView[] | undefined;
  getFilteredProjectViews: (projectId: string) => IProjectView[] | undefined;
  getViewById: (viewId: string) => IProjectView;
  // fetch actions
  fetchViews: (workspaceSlug: string, projectId: string) => Promise<undefined | IProjectView[]>;
  fetchViewDetails: (workspaceSlug: string, projectId: string, viewId: string) => Promise<IProjectView>;
  // CRUD actions
  createView: (workspaceSlug: string, projectId: string, data: Partial<IProjectView>) => Promise<IProjectView>;
  updateView: (
    workspaceSlug: string,
    projectId: string,
    viewId: string,
    data: Partial<IProjectView>
  ) => Promise<IProjectView>;
  deleteView: (workspaceSlug: string, projectId: string, viewId: string) => Promise<any>;
  addTaskListViews: (workspaceSlug: string, projectId: string) => Promise<TTaskListViewsResponse>;
  updateFilters: <T extends keyof TViewFilters>(filterKey: T, filterValue: TViewFilters[T]) => void;
  clearAllFilters: () => void;
  // favorites actions
  addViewToFavorites: (workspaceSlug: string, projectId: string, viewId: string) => Promise<any>;
  removeViewFromFavorites: (workspaceSlug: string, projectId: string, viewId: string) => Promise<any>;
}

export class ProjectViewStore implements IProjectViewStore {
  // observables
  loader: boolean = false;
  viewMap: Record<string, IProjectView> = {};
  //loaders
  fetchedMap: Record<string, boolean> = {};
  filters: TViewFilters = { searchQuery: "", sortBy: "desc", sortKey: "updated_at" };
  // root store
  rootStore;
  // services
  viewService;

  constructor(_rootStore: CoreRootStore) {
    makeObservable(this, {
      // observables
      loader: observable.ref,
      viewMap: observable,
      fetchedMap: observable,
      filters: observable,
      // computed
      projectViewIds: computed,
      // fetch actions
      fetchViews: action,
      fetchViewDetails: action,
      // CRUD actions
      createView: action,
      updateView: action,
      deleteView: action,
      addTaskListViews: action,
      // actions
      updateFilters: action,
      clearAllFilters: action,
      // favorites actions
      addViewToFavorites: action,
      removeViewFromFavorites: action,
    });
    // root store
    this.rootStore = _rootStore;
    // services
    this.viewService = new ViewService();

    this.createView = this.createView.bind(this);
    this.updateView = this.updateView.bind(this);
  }

  /**
   * Returns array of view ids for current project
   */
  get projectViewIds() {
    const projectId = this.rootStore.router.projectId;
    if (!projectId || !this.fetchedMap[projectId]) return null;
    const viewIds = Object.keys(this.viewMap ?? {})?.filter((viewId) => this.viewMap?.[viewId]?.project === projectId);
    return viewIds;
  }

  getProjectViews = computedFn((projectId: string) => {
    if (!this.fetchedMap[projectId]) return undefined;

    const ViewsList = Object.values(this.viewMap ?? {});
    // helps to filter views based on the projectId
    let filteredViews = ViewsList.filter((view) => view?.project === projectId);
    filteredViews = orderViews(filteredViews, this.filters.sortKey, this.filters.sortBy);

    return filteredViews ?? undefined;
  });
  /**
   * returns viewsIds of issues
   */
  getFilteredProjectViews = computedFn((projectId: string) => {
    if (!this.fetchedMap[projectId]) return undefined;

    const ViewsList = Object.values(this.viewMap ?? {});
    // helps to filter views based on the projectId, searchQuery and filters
    let filteredViews = ViewsList.filter(
      (view) =>
        view?.project === projectId &&
        getViewName(view.name).toLowerCase().includes(this.filters.searchQuery.toLowerCase()) &&
        shouldFilterView(view, this.filters.filters)
    );
    filteredViews = orderViews(filteredViews, this.filters.sortKey, this.filters.sortBy);

    return filteredViews ?? undefined;
  });

  /**
   * Returns view details by id
   */
  getViewById = computedFn((viewId: string) => this.viewMap?.[viewId] ?? null);

  /**
   * Updates the filter
   * @param filterKey
   * @param filterValue
   */
  updateFilters = <T extends keyof TViewFilters>(filterKey: T, filterValue: TViewFilters[T]) => {
    runInAction(() => {
      set(this.filters, [filterKey], filterValue);
    });
  };

  /**
   * @description clears all the filters
   */
  clearAllFilters = () =>
    runInAction(() => {
      set(this.filters, ["filters"], {});
    });

  /**
   * Fetches views for current project
   * @param workspaceSlug
   * @param projectId
   * @returns Promise<IProjectView[]>
   */
  fetchViews = async (workspaceSlug: string, projectId: string) => {
    try {
      this.loader = true;
      await this.viewService.getViews(workspaceSlug, projectId).then((response) => {
        runInAction(() => {
          response.forEach((view) => {
            set(this.viewMap, [view.id], view);
          });
          set(this.fetchedMap, projectId, true);
          this.loader = false;
        });
        return response;
      });
    } catch (_error) {
      this.loader = false;
      return undefined;
    }
  };

  /**
   * Fetches view details for a specific view
   * @param workspaceSlug
   * @param projectId
   * @param viewId
   * @returns Promise<IProjectView>
   */
  fetchViewDetails = async (workspaceSlug: string, projectId: string, viewId: string): Promise<IProjectView> =>
    await this.viewService.getViewDetails(workspaceSlug, projectId, viewId).then((response) => {
      runInAction(() => {
        set(this.viewMap, [viewId], response);
      });
      return response;
    });

  /**
   * Creates a new view for a specific project and adds it to the store
   * @param workspaceSlug
   * @param projectId
   * @param data
   * @returns Promise<IProjectView>
   */
  async createView(workspaceSlug: string, projectId: string, data: Partial<IProjectView>): Promise<IProjectView> {
    const shouldRecord = undoStack.canRecord();
    const response = await this.viewService.createView(workspaceSlug, projectId, getValidatedViewFilters(data));

    runInAction(() => {
      set(this.viewMap, [response.id], response);
    });

    if (shouldRecord) {
      // Ctrl+Z deletes the new view; Ctrl+Shift+Z makes it again
      let snapshot: IProjectView = deepCopy(response);
      undoStack.record({
        label: "New view",
        undo: async () => {
          const id = undoStack.resolve(response.id);
          snapshot = deepCopy(this.getViewById(id) ?? snapshot);
          await this.deleteView(workspaceSlug, projectId, id);
        },
        redo: () => this.recreateView(workspaceSlug, projectId, snapshot),
      });
    }

    return response;
  }

  // ---- undo / redo (store/undo/undo-stack.ts) ----

  /** Makes a deleted view again from its last values. It gets a new id; the undo stack follows it. */
  recreateView = async (workspaceSlug: string, projectId: string, snapshot: IProjectView) => {
    const payload: Partial<IProjectView> = {
      name: snapshot.name,
      description: snapshot.description,
      access: snapshot.access,
      rich_filters: snapshot.rich_filters,
      display_filters: snapshot.display_filters,
      display_properties: snapshot.display_properties,
      logo_props: snapshot.logo_props,
      is_hidden: snapshot.is_hidden,
      ...(snapshot.sort_order !== undefined ? { sort_order: snapshot.sort_order } : {}),
    };
    const response = await this.viewService.createView(workspaceSlug, projectId, getValidatedViewFilters(payload));
    runInAction(() => set(this.viewMap, [response.id], response));
    undoStack.alias(snapshot.id, response.id);
    return response;
  };

  /** After undo / redo changed a view's filters, the open view shows them too. */
  private syncOpenViewFilters = (workspaceSlug: string, projectId: string, viewId: string) => {
    const view = this.getViewById(viewId);
    const issueRoot = this.rootStore.issue;
    if (!view || issueRoot.viewId !== viewId) return;
    issueRoot.projectViewIssuesFilter.mutateFilters(workspaceSlug, viewId, view);
    this.rootStore.workItemFilters
      .getFilter(EIssuesStoreType.PROJECT_VIEW, viewId)
      ?.resetExpression(deepCopy(view.rich_filters), true);
    void issueRoot.projectViewIssues.fetchIssuesWithExistingPagination(workspaceSlug, projectId, viewId, "mutation");
  };

  /**
   * Adds the task-list views (Active / Completed / Checked) and the Seen checkbox to a board,
   * then puts the views in the store and reloads the board's fields so the checkbox shows.
   */
  addTaskListViews = async (workspaceSlug: string, projectId: string): Promise<TTaskListViewsResponse> => {
    const response = await this.viewService.addTaskListViews(workspaceSlug, projectId);
    runInAction(() => {
      response.views.forEach((view) => set(this.viewMap, [view.id], view));
      set(this.fetchedMap, projectId, true);
    });
    await this.rootStore.customField.fetchProjectFields(workspaceSlug, projectId);
    return response;
  };

  /**
   * Updates a view details of specific view and updates it in the store
   * @param workspaceSlug
   * @param projectId
   * @param viewId
   * @param data
   * @returns Promise<IProjectView>
   */
  async updateView(
    workspaceSlug: string,
    projectId: string,
    viewId: string,
    data: Partial<IProjectView>
  ): Promise<IProjectView> {
    const currentView = this.getViewById(viewId);
    const shouldRecord = undoStack.canRecord() && !!currentView;
    const keys = Object.keys(data);
    const oldData = currentView ? (pickOldValues(currentView, keys) as unknown as Partial<IProjectView>) : {};
    const newData = pickOldValues(data, keys) as unknown as Partial<IProjectView>;

    runInAction(() => {
      set(this.viewMap, [viewId], { ...currentView, ...data });
    });

    const response = await this.viewService.patchView(workspaceSlug, projectId, viewId, data);

    if (shouldRecord && !sameValue(oldData, newData)) {
      const touchesFilters = keys.some((k) => ["rich_filters", "display_filters", "display_properties"].includes(k));
      const label =
        keys.length === 1 && keys[0] === "is_hidden"
          ? newData.is_hidden
            ? "Hide view"
            : "Show view"
          : keys.length === 1 && keys[0] === "name"
            ? "Rename view"
            : keys.length === 1 && keys[0] === "sort_order"
              ? "Move view"
              : "View change";
      const apply = async (values: Partial<IProjectView>) => {
        const id = undoStack.resolve(viewId);
        await this.updateView(workspaceSlug, projectId, id, values);
        if (touchesFilters) this.syncOpenViewFilters(workspaceSlug, projectId, id);
      };
      undoStack.record({ label, undo: () => apply(oldData), redo: () => apply(newData) });
    }

    return response;
  }

  /**
   * Deletes a view and removes it from the viewMap object
   * @param workspaceSlug
   * @param projectId
   * @param viewId
   * @returns
   */
  deleteView = async (workspaceSlug: string, projectId: string, viewId: string): Promise<any> => {
    const shouldRecord = undoStack.canRecord();
    const snapshot = deepCopy(this.getViewById(viewId));
    await this.viewService.deleteView(workspaceSlug, projectId, viewId).then(() => {
      runInAction(() => {
        delete this.viewMap[viewId];
        if (this.rootStore.favorite.entityMap[viewId]) this.rootStore.favorite.removeFavoriteFromStore(viewId);
      });
    });
    if (shouldRecord && snapshot) {
      // the server has no undelete for views: Ctrl+Z makes it again with the same settings
      let current: IProjectView = snapshot;
      undoStack.record({
        label: "Delete view",
        undo: async () => {
          await this.recreateView(workspaceSlug, projectId, { ...current, id: undoStack.resolve(snapshot.id) });
        },
        redo: async () => {
          const id = undoStack.resolve(snapshot.id);
          current = deepCopy(this.getViewById(id) ?? current);
          await this.deleteView(workspaceSlug, projectId, id);
        },
      });
    }
  };

  /**
   * Adds a view to favorites
   * @param workspaceSlug
   * @param projectId
   * @param viewId
   * @returns
   */
  addViewToFavorites = async (workspaceSlug: string, projectId: string, viewId: string) => {
    try {
      const currentView = this.getViewById(viewId);
      if (currentView?.is_favorite) return;
      runInAction(() => {
        set(this.viewMap, [viewId, "is_favorite"], true);
      });
      await this.rootStore.favorite.addFavorite(workspaceSlug.toString(), {
        entity_type: "view",
        entity_identifier: viewId,
        project_id: projectId,
        entity_data: { name: this.viewMap[viewId].name || "" },
      });
    } catch (error) {
      console.error("Failed to add view to favorites in view store", error);
      runInAction(() => {
        set(this.viewMap, [viewId, "is_favorite"], false);
      });
    }
  };

  /**
   * Removes a view from favorites
   * @param workspaceSlug
   * @param projectId
   * @param viewId
   * @returns
   */
  removeViewFromFavorites = async (workspaceSlug: string, projectId: string, viewId: string) => {
    try {
      const currentView = this.getViewById(viewId);
      if (!currentView?.is_favorite) return;
      runInAction(() => {
        set(this.viewMap, [viewId, "is_favorite"], false);
      });
      await this.rootStore.favorite.removeFavoriteEntity(workspaceSlug, viewId);
    } catch (error) {
      console.error("Failed to remove view from favorites in view store", error);
      runInAction(() => {
        set(this.viewMap, [viewId, "is_favorite"], true);
      });
    }
  };
}
