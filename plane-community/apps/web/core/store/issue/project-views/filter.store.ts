/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { isEmpty, set } from "lodash-es";
import { action, computed, makeObservable, observable, runInAction } from "mobx";
// base class
import { computedFn } from "mobx-utils";
import type { TSupportedFilterTypeForUpdate } from "@plane/constants";
import { EIssueFilterType } from "@plane/constants";
import type {
  IIssueDisplayFilterOptions,
  IIssueDisplayProperties,
  TIssueKanbanFilters,
  IIssueFilters,
  TIssueParams,
  IssuePaginationOptions,
  IProjectView,
  IProjectViewUserDisplay,
  TWorkItemFilterExpression,
  TSupportedFilterForUpdate,
} from "@plane/types";
import { EIssuesStoreType } from "@plane/types";
import { handleIssueQueryParamsByLayout } from "@plane/utils";
// services
import { ViewService } from "@/services/view.service";
import type { IBaseIssueFilterStore } from "../helpers/issue-filter-helper.store";
import { IssueFilterHelperStore, sameIssueFilters } from "../helpers/issue-filter-helper.store";
// helpers
// types
import type { IIssueRootStore } from "../root.store";
// undo
import { deepCopy, displayChangeLabel, pickOldValues, sameValue, undoStack } from "@/store/undo/undo-stack";
// constants

export interface IProjectViewIssuesFilter extends IBaseIssueFilterStore {
  //helper actions
  getFilterParams: (
    options: IssuePaginationOptions,
    viewId: string,
    cursor: string | undefined,
    groupId: string | undefined,
    subGroupId: string | undefined
  ) => Partial<Record<TIssueParams, string | boolean>>;
  getIssueFilters(viewId: string): IIssueFilters | undefined;
  // helper actions
  mutateFilters: (workspaceSlug: string, viewId: string, viewDetails: IProjectView) => void;
  // action
  fetchFilters: (workspaceSlug: string, projectId: string, viewId: string) => Promise<void>;
  updateFilterExpression: (
    workspaceSlug: string,
    projectId: string,
    viewId: string,
    filters: TWorkItemFilterExpression
  ) => Promise<void>;
  updateFilters: (
    workspaceSlug: string,
    projectId: string,
    filterType: TSupportedFilterTypeForUpdate,
    filters: TSupportedFilterForUpdate,
    viewId: string
  ) => Promise<void>;
  resetFilters: (workspaceSlug: string, viewId: string) => void;
}

export class ProjectViewIssuesFilter extends IssueFilterHelperStore implements IProjectViewIssuesFilter {
  // observables
  filters: { [viewId: string]: IIssueFilters } = {};
  // root store
  rootIssueStore;
  // services
  issueFilterService;

  constructor(_rootStore: IIssueRootStore) {
    super();
    makeObservable(this, {
      // observables
      filters: observable,
      // computed
      // same filter parts = same value, so adding a display-property key does not re-render every row
      issueFilters: computed({ equals: sameIssueFilters }),
      appliedFilters: computed,
      // actions
      fetchFilters: action,
      updateFilters: action,
      resetFilters: action,
    });
    // root store
    this.rootIssueStore = _rootStore;
    // services
    this.issueFilterService = new ViewService();
  }

  get issueFilters() {
    const viewId = this.rootIssueStore.viewId;
    if (!viewId) return undefined;

    return this.getIssueFilters(viewId);
  }

  get appliedFilters() {
    const viewId = this.rootIssueStore.viewId;
    if (!viewId) return undefined;

    return this.getAppliedFilters(viewId);
  }

  getIssueFilters(viewId: string) {
    const displayFilters = this.filters[viewId] || undefined;
    if (isEmpty(displayFilters)) return undefined;

    const _filters: IIssueFilters = this.computedIssueFilters(displayFilters);

    return _filters;
  }

  getAppliedFilters(viewId: string) {
    const userFilters = this.getIssueFilters(viewId);
    if (!userFilters) return undefined;

    const filteredParams = handleIssueQueryParamsByLayout(userFilters?.displayFilters?.layout, "issues");
    if (!filteredParams) return undefined;

    const filteredRouteParams: Partial<Record<TIssueParams, string | boolean>> = this.computedFilteredParams(
      userFilters?.richFilters,
      userFilters?.displayFilters,
      filteredParams
    );

    return filteredRouteParams;
  }

  getFilterParams = computedFn(
    (
      options: IssuePaginationOptions,
      viewId: string,
      cursor: string | undefined,
      groupId: string | undefined,
      subGroupId: string | undefined
    ) => {
      const filterParams = this.getAppliedFilters(viewId);

      const paginationParams = this.getPaginationParams(filterParams, options, cursor, groupId, subGroupId);
      return paginationParams;
    }
  );

  /** Notes: this person's own Display choices on a view, kept in their board user properties (any device). */
  private getViewUserDisplay = (projectId: string | undefined, viewId: string): IProjectViewUserDisplay | undefined => {
    if (!projectId) return undefined;
    return this.rootIssueStore.rootStore.memberRoot.project.getProjectUserProperties(projectId)?.preferences?.views?.[
      viewId
    ];
  };

  /** Notes: a Display change on a view lasts (reload, other browser, other device), for this person only. */
  private saveViewUserDisplay = (
    workspaceSlug: string,
    projectId: string,
    viewId: string,
    kind: "display_filters" | "display_properties",
    changed: Partial<IIssueDisplayFilterOptions> | Partial<IIssueDisplayProperties>
  ) => {
    const members = this.rootIssueStore.rootStore.memberRoot.project;
    const current = members.getProjectUserProperties(projectId);
    if (!current?.preferences) return;
    const views = { ...current.preferences.views };
    const own = { ...views[viewId] };
    own[kind] = { ...own[kind], ...changed } as never;
    views[viewId] = own;
    members
      .updateProjectUserPreferences(workspaceSlug, projectId, { ...current.preferences, views })
      .catch((error) => console.log("error while saving the view's display choices", error));
  };

  mutateFilters: IProjectViewIssuesFilter["mutateFilters"] = action((workspaceSlug, viewId, viewDetails) => {
    const richFilters: TWorkItemFilterExpression = viewDetails?.rich_filters;
    // this person's own Display choices win over the view's saved ones
    const own = this.getViewUserDisplay(viewDetails?.project, viewId);
    const displayFilters: IIssueDisplayFilterOptions = this.computedDisplayFilters({
      ...viewDetails?.display_filters,
      ...own?.display_filters,
    });
    const displayProperties: IIssueDisplayProperties = this.computedDisplayProperties({
      ...viewDetails?.display_properties,
      ...own?.display_properties,
    } as IIssueDisplayProperties);

    // fetching the kanban toggle helpers in the local storage
    const kanbanFilters = {
      group_by: [],
      sub_group_by: [],
    };
    const currentUserId = this.rootIssueStore.currentUserId;
    if (currentUserId) {
      const _kanbanFilters = this.handleIssuesLocalFilters.get(
        EIssuesStoreType.PROJECT_VIEW,
        workspaceSlug,
        viewId,
        currentUserId
      );
      kanbanFilters.group_by = _kanbanFilters?.kanban_filters?.group_by || [];
      kanbanFilters.sub_group_by = _kanbanFilters?.kanban_filters?.sub_group_by || [];
    }

    runInAction(() => {
      set(this.filters, [viewId, "richFilters"], richFilters);
      set(this.filters, [viewId, "displayFilters"], displayFilters);
      set(this.filters, [viewId, "displayProperties"], displayProperties);
      set(this.filters, [viewId, "kanbanFilters"], kanbanFilters);
    });
  });

  fetchFilters = async (workspaceSlug: string, projectId: string, viewId: string) => {
    try {
      const members = this.rootIssueStore.rootStore.memberRoot.project;
      const [viewDetails] = await Promise.all([
        this.issueFilterService.getViewDetails(workspaceSlug, projectId, viewId),
        // the person's own Display choices must be in hand before the view is drawn
        members.getProjectUserProperties(projectId)
          ? Promise.resolve()
          : members.fetchProjectUserProperties(workspaceSlug, projectId).catch(() => undefined),
      ]);
      this.mutateFilters(workspaceSlug, viewId, viewDetails);
    } catch (error) {
      console.log("error while fetching project view filters", error);
      throw error;
    }
  };

  /**
   * NOTE: This method is designed as a fallback function for the work item filter store.
   * Only use this method directly when initializing filter instances.
   * For regular filter updates, use this method as a fallback function for the work item filter store methods instead.
   */
  updateFilterExpression: IProjectViewIssuesFilter["updateFilterExpression"] = async (
    workspaceSlug,
    projectId,
    viewId,
    filters
  ) => {
    // Ctrl+Z puts the old filter back (an unchanged expression is not an action)
    const undoBefore = deepCopy(this.filters[viewId]?.richFilters);
    const shouldRecord = undoStack.canRecord() && !sameValue(undoBefore, filters);
    try {
      runInAction(() => {
        set(this.filters, [viewId, "richFilters"], filters);
      });
      if (shouldRecord) {
        const after = deepCopy(filters);
        const before = undoBefore ?? ({} as TWorkItemFilterExpression);
        undoStack.record({
          label: "Filter change",
          undo: () => this.applyRichFiltersForUndo(workspaceSlug, projectId, viewId, before),
          redo: () => this.applyRichFiltersForUndo(workspaceSlug, projectId, viewId, after),
        });
      }

      this.rootIssueStore.projectViewIssues.fetchIssuesWithExistingPagination(
        workspaceSlug,
        projectId,
        viewId,
        "mutation"
      );
    } catch (error) {
      console.log("error while updating rich filters", error);
      throw error;
    }
  };

  updateFilters: IProjectViewIssuesFilter["updateFilters"] = async (
    workspaceSlug,
    projectId,
    type,
    filters,
    viewId
  ) => {
    try {
      if (isEmpty(this.filters) || isEmpty(this.filters[viewId])) return;

      // Ctrl+Z puts the old layout / grouping / sort / shown properties back
      const undoKind =
        type === EIssueFilterType.DISPLAY_FILTERS
          ? "display_filters"
          : type === EIssueFilterType.DISPLAY_PROPERTIES
            ? "display_properties"
            : undefined;
      const undoBefore =
        undoKind && undoStack.canRecord()
          ? deepCopy(
              undoKind === "display_filters"
                ? this.filters[viewId].displayFilters
                : this.filters[viewId].displayProperties
            )
          : undefined;

      const _filters = {
        richFilters: this.filters[viewId].richFilters,
        displayFilters: this.filters[viewId].displayFilters as IIssueDisplayFilterOptions,
        displayProperties: this.filters[viewId].displayProperties as IIssueDisplayProperties,
        kanbanFilters: this.filters[viewId].kanbanFilters as TIssueKanbanFilters,
      };

      switch (type) {
        case EIssueFilterType.DISPLAY_FILTERS: {
          const updatedDisplayFilters = filters as IIssueDisplayFilterOptions;
          _filters.displayFilters = { ..._filters.displayFilters, ...updatedDisplayFilters };

          // set sub_group_by to null if group_by is set to null
          if (_filters.displayFilters.group_by === null) {
            _filters.displayFilters.sub_group_by = null;
            updatedDisplayFilters.sub_group_by = null;
          }
          // set sub_group_by to null if layout is switched to kanban group_by and sub_group_by are same
          if (
            _filters.displayFilters.layout === "kanban" &&
            _filters.displayFilters.group_by === _filters.displayFilters.sub_group_by
          ) {
            _filters.displayFilters.sub_group_by = null;
            updatedDisplayFilters.sub_group_by = null;
          }
          // set group_by to state if layout is switched to kanban and group_by is null
          if (_filters.displayFilters.layout === "kanban" && _filters.displayFilters.group_by === null) {
            _filters.displayFilters.group_by = "state";
            updatedDisplayFilters.group_by = "state";
          }

          runInAction(() => {
            Object.keys(updatedDisplayFilters).forEach((_key) => {
              set(
                this.filters,
                [viewId, "displayFilters", _key],
                updatedDisplayFilters[_key as keyof IIssueDisplayFilterOptions]
              );
            });
          });

          if (this.getShouldClearIssues(updatedDisplayFilters)) {
            this.rootIssueStore.projectIssues.clear(true); // clear issues for local store when some filters like layout changes
          }

          if (this.getShouldReFetchIssues(updatedDisplayFilters)) {
            this.rootIssueStore.projectViewIssues.fetchIssuesWithExistingPagination(
              workspaceSlug,
              projectId,
              viewId,
              "mutation"
            );
          }

          this.saveViewUserDisplay(workspaceSlug, projectId, viewId, "display_filters", updatedDisplayFilters);
          break;
        }
        case EIssueFilterType.DISPLAY_PROPERTIES: {
          const updatedDisplayProperties = filters as IIssueDisplayProperties;
          _filters.displayProperties = { ..._filters.displayProperties, ...updatedDisplayProperties };

          runInAction(() => {
            Object.keys(updatedDisplayProperties).forEach((_key) => {
              set(
                this.filters,
                [viewId, "displayProperties", _key],
                updatedDisplayProperties[_key as keyof IIssueDisplayProperties]
              );
            });
          });
          this.saveViewUserDisplay(workspaceSlug, projectId, viewId, "display_properties", updatedDisplayProperties);

          break;
        }
        case EIssueFilterType.KANBAN_FILTERS: {
          const updatedKanbanFilters = filters as TIssueKanbanFilters;
          _filters.kanbanFilters = { ..._filters.kanbanFilters, ...updatedKanbanFilters };

          const currentUserId = this.rootIssueStore.currentUserId;
          if (currentUserId)
            this.handleIssuesLocalFilters.set(
              EIssuesStoreType.PROJECT_VIEW,
              type,
              workspaceSlug,
              viewId,
              currentUserId,
              {
                kanban_filters: _filters.kanbanFilters,
              }
            );

          runInAction(() => {
            Object.keys(updatedKanbanFilters).forEach((_key) => {
              set(
                this.filters,
                [viewId, "kanbanFilters", _key],
                updatedKanbanFilters[_key as keyof TIssueKanbanFilters]
              );
            });
          });

          break;
        }
        default:
          break;
      }
      if (undoKind && undoBefore)
        this.recordDisplayChange(workspaceSlug, projectId, viewId, type, undoKind, undoBefore, filters);
    } catch (error) {
      if (viewId) this.fetchFilters(workspaceSlug, projectId, viewId);
      throw error;
    }
  };

  /**
   * @description resets the filters for a project view
   * @param workspaceSlug
   * @param viewId
   */
  resetFilters: IProjectViewIssuesFilter["resetFilters"] = action((workspaceSlug, viewId) => {
    const viewDetails = this.rootIssueStore.rootStore.projectView.getViewById(viewId);
    if (!viewDetails) return;
    this.mutateFilters(workspaceSlug, viewId, viewDetails);
  });

  // ---- undo / redo (store/undo/undo-stack.ts) ----

  private recordDisplayChange(
    workspaceSlug: string,
    projectId: string,
    viewId: string,
    type: TSupportedFilterTypeForUpdate,
    kind: "display_filters" | "display_properties",
    before: object,
    filters: TSupportedFilterForUpdate
  ) {
    const keys = Object.keys(filters ?? {});
    const oldValues = pickOldValues(before, keys) as unknown as TSupportedFilterForUpdate;
    const newValues = pickOldValues(filters as object, keys) as unknown as TSupportedFilterForUpdate;
    if (sameValue(oldValues, newValues)) return;
    undoStack.record({
      label: displayChangeLabel(kind, keys),
      undo: () => this.updateFilters(workspaceSlug, projectId, type, deepCopy(oldValues), viewId),
      redo: () => this.updateFilters(workspaceSlug, projectId, type, deepCopy(newValues), viewId),
    });
  }

  /** Puts a filter expression back on the view and in its filter bar (undo / redo). */
  private async applyRichFiltersForUndo(
    workspaceSlug: string,
    projectId: string,
    viewId: string,
    filters: TWorkItemFilterExpression
  ) {
    this.rootIssueStore.rootStore.workItemFilters
      .getFilter(EIssuesStoreType.PROJECT_VIEW, viewId)
      ?.resetExpression(deepCopy(filters), false);
    await this.updateFilterExpression(workspaceSlug, projectId, viewId, deepCopy(filters));
  }
}
