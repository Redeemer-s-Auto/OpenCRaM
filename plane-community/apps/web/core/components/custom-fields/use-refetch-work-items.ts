/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback } from "react";

/**
 * Kept for the callers that still chain it after a save; it no longer reloads anything.
 *
 * It used to reload the whole list after a tick, so a card that left a saved view's filter
 * (Completed -> Checked) would go. That reload emptied the list first (the page flashed to the
 * loader, every row was drawn again, and only the first page came back). The issue store now
 * does it in place: `issueUpdate` drops just that card when it no longer fits the list's filter
 * (store/issue/helpers/base-issues.store.ts, removeIssueIfFilteredOut).
 */
export const useRefetchWorkItems = () => useCallback(async () => {}, []);
