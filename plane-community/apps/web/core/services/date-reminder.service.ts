/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import { APIService } from "@/services/api.service";

/** One reminder, as the person who set it sees it. Nobody sees anyone else reminders. */
export type TDateReminder = {
  mention_id: string;
  issue_id: string;
  date: string;
  time: string | null;
  tz: string;
  /** minutes before the event; 0 is at the event */
  offset_minutes: number;
  remind_at: string;
  sent_at: string | null;
  stopped: boolean;
  stop_reason: string;
};

export type TDateReminderInput = {
  issue_id: string;
  date: string;
  time: string | null;
  tz: string;
  offset_minutes: number;
};

export class DateReminderService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private url(workspaceSlug: string) {
    return `/api/workspaces/${workspaceSlug}/date-reminders/`;
  }

  /** The caller own reminders on one card. */
  async list(workspaceSlug: string, issueId: string): Promise<TDateReminder[]> {
    return this.get(this.url(workspaceSlug), { params: { issue_id: issueId } })
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async set(workspaceSlug: string, mentionId: string, data: TDateReminderInput): Promise<TDateReminder> {
    return this.put(`${this.url(workspaceSlug)}${mentionId}/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async remove(workspaceSlug: string, mentionId: string): Promise<void> {
    return this.delete(`${this.url(workspaceSlug)}${mentionId}/`)
      .then(() => undefined)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /** The date or time in a mention changed: move everyone pending reminders on it. */
  async move(
    workspaceSlug: string,
    mentionId: string,
    data: Omit<TDateReminderInput, "offset_minutes">
  ): Promise<{ moved: number }> {
    return this.post(`${this.url(workspaceSlug)}${mentionId}/move/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
