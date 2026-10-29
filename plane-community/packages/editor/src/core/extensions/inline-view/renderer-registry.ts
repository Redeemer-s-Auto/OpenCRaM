/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";

/** Settings of one live view block. The editor does not read them; the web app does. */
export type TInlineViewConfig = Record<string, unknown>;

export type TInlineViewRenderProps = {
  config: TInlineViewConfig;
  /** Save new settings into the block. Does nothing useful when the editor is read-only. */
  updateConfig: (config: TInlineViewConfig) => void;
  /** Remove the block from the page. */
  deleteBlock: () => void;
  editable: boolean;
};

type TRenderer = (props: TInlineViewRenderProps) => ReactNode;

// The block needs the web app's data layer, which this package must not import.
// The web app registers one renderer at start-up.
let renderer: TRenderer | null = null;

export const registerInlineViewRenderer = (next: TRenderer | null) => {
  renderer = next;
};

export const getInlineViewRenderer = () => renderer;
