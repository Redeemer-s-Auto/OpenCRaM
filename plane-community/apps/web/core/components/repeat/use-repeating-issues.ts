/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useMemo } from "react";
import useSWR, { mutate } from "swr";
import type { TRepeatingIssue } from "@/services/repeat.service";
import { repeatService } from "@/services/repeat.service";

export const repeatingIssuesKey = (projectId: string) => `REPEATING_ISSUES_${projectId}`;

/** Refresh the "which cards repeat" list after a rule changes. */
export const refreshRepeatingIssues = (projectId: string) => mutate(repeatingIssuesKey(projectId));

/**
 * Map of issue id -> next run (ISO) for the cards in a project that repeat.
 * One request per project; every card on the board shares it (SWR de-duplicates).
 */
export function useRepeatingIssues(workspaceSlug: string | undefined, projectId: string | undefined | null) {
  const { data } = useSWR<TRepeatingIssue[]>(
    workspaceSlug && projectId ? repeatingIssuesKey(projectId) : null,
    () => repeatService.listRepeating(workspaceSlug as string, projectId as string),
    { revalidateOnFocus: false, dedupingInterval: 60_000, shouldRetryOnError: false }
  );
  return useMemo(() => new Map((data ?? []).map((row) => [row.issue_id, row.next_run_at])), [data]);
}
