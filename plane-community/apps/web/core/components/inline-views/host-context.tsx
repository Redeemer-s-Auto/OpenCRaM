/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { createContext, useContext } from "react";

/** The card whose page body holds the block. Set by the card description editor. */
export type TInlineViewHost = {
  workspaceSlug: string;
  projectId?: string;
  issueId?: string;
};

const InlineViewHostContext = createContext<TInlineViewHost | null>(null);

export const InlineViewHostProvider = InlineViewHostContext.Provider;
export const useInlineViewHost = () => useContext(InlineViewHostContext);
