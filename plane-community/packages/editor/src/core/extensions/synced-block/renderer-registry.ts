/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";

export type TSyncedBlockRenderProps = {
  /** Id of the shared text. Empty until one is chosen. */
  id: string;
  /** Point this copy at a block. */
  setId: (id: string) => void;
  /** Replace this copy with plain text (the other copies keep the shared block). */
  unsync: (html: string) => void;
  /** Remove this copy from the page. The shared block stays. */
  removeCopy: () => void;
  editable: boolean;
};

type TRenderer = (props: TSyncedBlockRenderProps) => ReactNode;

// The block needs the web app's data layer, which this package must not import.
// The web app registers one renderer at start-up.
let renderer: TRenderer | null = null;

export const registerSyncedBlockRenderer = (next: TRenderer | null) => {
  renderer = next;
};

export const getSyncedBlockRenderer = () => renderer;
