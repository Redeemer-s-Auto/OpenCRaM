/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { set, sortBy, unset } from "lodash-es";
import { action, makeObservable, observable, runInAction } from "mobx";
import { computedFn } from "mobx-utils";
// types
import type { TCustomField } from "@plane/types";
// services
import { CustomFieldService } from "@/services/issue";
// store
import type { CoreRootStore } from "./root.store";

export interface ICustomFieldStore {
  fieldMap: Record<string, TCustomField>;
  fetchedMap: Record<string, boolean>;
  // computed functions
  getProjectFields: (projectId: string | null | undefined) => TCustomField[] | undefined;
  getArchivedProjectFields: (projectId: string | null | undefined) => TCustomField[];
  getFieldById: (fieldId: string) => TCustomField | undefined;
  // actions
  fetchProjectFields: (workspaceSlug: string, projectId: string) => Promise<TCustomField[]>;
  createField: (workspaceSlug: string, projectId: string, data: Partial<TCustomField>) => Promise<TCustomField>;
  updateField: (
    workspaceSlug: string,
    projectId: string,
    fieldId: string,
    data: Partial<TCustomField>
  ) => Promise<TCustomField>;
  /** Adds options made on a card (label fields) without a server call. */
  mergeOptions: (fieldId: string, options: TCustomField["options"]) => void;
  archiveField: (workspaceSlug: string, projectId: string, fieldId: string) => Promise<void>;
  restoreField: (workspaceSlug: string, projectId: string, fieldId: string) => Promise<void>;
  deleteField: (workspaceSlug: string, projectId: string, fieldId: string, confirmName: string) => Promise<void>;
  moveField: (workspaceSlug: string, projectId: string, fieldId: string, direction: "up" | "down") => Promise<void>;
}

export class CustomFieldStore implements ICustomFieldStore {
  fieldMap: Record<string, TCustomField> = {};
  fetchedMap: Record<string, boolean> = {};
  rootStore: CoreRootStore;
  service: CustomFieldService;

  constructor(_rootStore: CoreRootStore) {
    makeObservable(this, {
      fieldMap: observable,
      fetchedMap: observable,
      fetchProjectFields: action,
      createField: action,
      updateField: action,
      mergeOptions: action,
      archiveField: action,
      restoreField: action,
      deleteField: action,
      moveField: action,
    });
    this.rootStore = _rootStore;
    this.service = new CustomFieldService();
  }

  /** Live (not archived) fields of a project, in board order. undefined until fetched. */
  getProjectFields = computedFn((projectId: string | null | undefined) => {
    if (!projectId || !this.fetchedMap[projectId]) return undefined;
    return sortBy(
      Object.values(this.fieldMap).filter((f) => f.project === projectId && !f.archived_at),
      "sort_order"
    );
  });

  getArchivedProjectFields = computedFn((projectId: string | null | undefined) => {
    if (!projectId) return [];
    return sortBy(
      Object.values(this.fieldMap).filter((f) => f.project === projectId && !!f.archived_at),
      "name"
    );
  });

  getFieldById = computedFn((fieldId: string) => this.fieldMap[fieldId]);

  fetchProjectFields = async (workspaceSlug: string, projectId: string) => {
    const response = await this.service.list(workspaceSlug, projectId, "all");
    runInAction(() => {
      Object.values(this.fieldMap)
        .filter((f) => f.project === projectId)
        .forEach((f) => unset(this.fieldMap, [f.id]));
      response.forEach((field) => set(this.fieldMap, [field.id], field));
      set(this.fetchedMap, projectId, true);
    });
    return response;
  };

  createField = async (workspaceSlug: string, projectId: string, data: Partial<TCustomField>) => {
    const field = await this.service.create(workspaceSlug, projectId, data);
    runInAction(() => set(this.fieldMap, [field.id], field));
    return field;
  };

  updateField = async (workspaceSlug: string, projectId: string, fieldId: string, data: Partial<TCustomField>) => {
    const field = await this.service.update(workspaceSlug, projectId, fieldId, data);
    runInAction(() => set(this.fieldMap, [field.id], field));
    return field;
  };

  mergeOptions = (fieldId: string, options: TCustomField["options"]) => {
    const field = this.fieldMap[fieldId];
    if (!field) return;
    const known = new Set(field.options.map((o) => o.id));
    const added = options.filter((o) => !known.has(o.id));
    if (added.length) set(this.fieldMap, [fieldId, "options"], [...field.options, ...added]);
  };

  archiveField = async (workspaceSlug: string, projectId: string, fieldId: string) => {
    const field = await this.service.archive(workspaceSlug, projectId, fieldId);
    runInAction(() => set(this.fieldMap, [field.id], field));
  };

  restoreField = async (workspaceSlug: string, projectId: string, fieldId: string) => {
    const field = await this.service.restore(workspaceSlug, projectId, fieldId);
    runInAction(() => set(this.fieldMap, [field.id], field));
  };

  deleteField = async (workspaceSlug: string, projectId: string, fieldId: string, confirmName: string) => {
    await this.service.destroy(workspaceSlug, projectId, fieldId, confirmName);
    runInAction(() => unset(this.fieldMap, [fieldId]));
  };

  moveField = async (workspaceSlug: string, projectId: string, fieldId: string, direction: "up" | "down") => {
    const fields = this.getProjectFields(projectId) ?? [];
    const index = fields.findIndex((f) => f.id === fieldId);
    const target = direction === "up" ? index - 1 : index + 1;
    if (index < 0 || target < 0 || target >= fields.length) return;
    const ids = fields.map((f) => f.id);
    [ids[index], ids[target]] = [ids[target], ids[index]];
    const response = await this.service.reorder(workspaceSlug, projectId, ids);
    runInAction(() => response.forEach((field) => set(this.fieldMap, [field.id], field)));
  };
}
