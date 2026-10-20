/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type { TLogoProps } from "@plane/types";
// services
import { APIService } from "@/services/api.service";

export type TBlueprintPerson = { id: string; display_name: string } | null;

export type TBlueprintSummary = {
  states: number;
  labels: number;
  fields: number;
  views: number;
  templates: number;
  sample_cards: number;
  is_private: boolean;
  /** Relation fields that link to a board outside the blueprint: pick a board when using it. */
  pick_boards: { key: string; name: string; board_name: string | null }[];
  notes: string[];
};

export type TBlueprint = {
  id: string;
  name: string;
  description: string;
  logo_props: TLogoProps | Record<string, never>;
  version: number;
  is_shared: boolean;
  created_by: TBlueprintPerson;
  created_at: string;
  updated_at: string;
  source_project: { id: string; name: string; identifier: string } | null;
  summary: TBlueprintSummary;
  can_manage: boolean;
  can_update_from_board: boolean;
};

export type TBlueprintVersion = {
  version: number;
  note: string;
  created_at: string;
  created_by: TBlueprintPerson;
  summary: TBlueprintSummary;
};

export type TBlueprintSaveData = {
  project_id: string;
  name: string;
  description?: string;
  logo_props?: TLogoProps;
  include_samples?: boolean;
  include_repeat_rules?: boolean;
  is_shared?: boolean;
};

export type TBlueprintUseData = {
  name: string;
  identifier: string;
  description?: string;
  logo_props?: TLogoProps;
  network?: number;
  relation_targets?: Record<string, string>;
  include_samples?: boolean;
};

export type TBlueprintUseResult = {
  project: { id: string; name: string; identifier: string };
  sample_cards_created: number;
  notes: string[];
};

export type TBoardOrigin = { blueprint_id: string | null; blueprint_name: string; version: number } | null;

/** The first readable message in an API error body. */
export const blueprintErrorMessage = (error: unknown, fallback = "Try again."): string => {
  const pick = (value: unknown): string | undefined => {
    if (typeof value === "string") return value;
    if (Array.isArray(value)) return value.map(pick).find(Boolean);
    if (value && typeof value === "object")
      return Object.values(value as Record<string, unknown>)
        .map(pick)
        .find(Boolean);
    return undefined;
  };
  return pick(error) ?? fallback;
};

export class BlueprintService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private url(workspaceSlug: string) {
    return `/api/workspaces/${workspaceSlug}/blueprints/`;
  }

  private unwrap<T>(promise: Promise<{ data: T }>): Promise<T> {
    return promise
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  list(workspaceSlug: string): Promise<TBlueprint[]> {
    return this.unwrap(this.get(this.url(workspaceSlug)));
  }

  saveFromBoard(workspaceSlug: string, data: TBlueprintSaveData): Promise<TBlueprint> {
    return this.unwrap(this.post(this.url(workspaceSlug), data));
  }

  update(
    workspaceSlug: string,
    id: string,
    data: Partial<Pick<TBlueprint, "name" | "description" | "is_shared">>
  ): Promise<TBlueprint> {
    return this.unwrap(this.patch(`${this.url(workspaceSlug)}${id}/`, data));
  }

  remove(workspaceSlug: string, id: string): Promise<void> {
    return this.unwrap(this.delete(`${this.url(workspaceSlug)}${id}/`));
  }

  updateFromBoard(workspaceSlug: string, id: string, data: { include_samples?: boolean } = {}): Promise<TBlueprint> {
    return this.unwrap(this.post(`${this.url(workspaceSlug)}${id}/recapture/`, data));
  }

  versions(workspaceSlug: string, id: string): Promise<TBlueprintVersion[]> {
    return this.unwrap(this.get(`${this.url(workspaceSlug)}${id}/versions/`));
  }

  exportDocument(workspaceSlug: string, id: string): Promise<Record<string, unknown>> {
    return this.unwrap(this.get(`${this.url(workspaceSlug)}${id}/export/`));
  }

  importDocument(workspaceSlug: string, document: unknown): Promise<TBlueprint> {
    return this.unwrap(this.post(`${this.url(workspaceSlug)}import/`, { document }));
  }

  use(workspaceSlug: string, id: string, data: TBlueprintUseData): Promise<TBlueprintUseResult> {
    return this.unwrap(this.post(`${this.url(workspaceSlug)}${id}/use/`, data));
  }

  boardOrigin(workspaceSlug: string, projectId: string): Promise<TBoardOrigin> {
    return this.unwrap(this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/blueprint-origin/`));
  }
}

export const blueprintService = new BlueprintService();
