/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

export type TRepeatFrequency = "daily" | "weekly" | "monthly";

/** What the Repeat panel sends. weekdays: 0 = Monday ... 6 = Sunday. month_day: 1-31, or -1 for the last day. */
export type TRepeatRuleInput = {
  frequency: TRepeatFrequency;
  interval: number;
  weekdays?: number[];
  month_day?: number | null;
  time_of_day: string;
  timezone?: string;
  /** The browser's zone; used only when neither the workspace nor the person has one set. */
  fallback_timezone?: string;
  start_date?: string;
  end_date?: string | null;
  max_count?: number | null;
};

export type TIssueRef = { id: string; name: string; sequence_id: number; project_id: string };

export type TRepeatRule = Required<Omit<TRepeatRuleInput, "timezone" | "fallback_timezone">> & {
  id: string;
  issue_id: string;
  timezone: string;
  created_count: number;
  next_run_at: string | null;
  last_run_at: string | null;
  is_active: boolean;
  stop_reason: string;
  owner: { id: string; name: string } | null;
  recent_copies: (TIssueRef & { scheduled_for: string })[];
};

export type TIssueRepeat = {
  rule: TRepeatRule | null;
  copy_of: { scheduled_for: string; template: TIssueRef | null } | null;
};

export type TRepeatingIssue = { issue_id: string; next_run_at: string | null };

const issueUrl = (workspaceSlug: string, projectId: string, issueId: string) =>
  `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/repeat/`;

export class RepeatService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async getRepeat(workspaceSlug: string, projectId: string, issueId: string): Promise<TIssueRepeat> {
    return this.get(issueUrl(workspaceSlug, projectId, issueId))
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async setRepeat(workspaceSlug: string, projectId: string, issueId: string, data: TRepeatRuleInput): Promise<TIssueRepeat> {
    return this.put(issueUrl(workspaceSlug, projectId, issueId), data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async stopRepeat(workspaceSlug: string, projectId: string, issueId: string): Promise<TIssueRepeat> {
    return this.delete(issueUrl(workspaceSlug, projectId, issueId))
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async listRepeating(workspaceSlug: string, projectId: string): Promise<TRepeatingIssue[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/projects/${projectId}/repeat-rules/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}

export const repeatService = new RepeatService();
