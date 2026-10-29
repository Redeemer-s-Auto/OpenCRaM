/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";

export type TDateMentionRenderProps = {
  /** YYYY-MM-DD */
  date: string;
  /** HH:MM, or empty when the date has no time */
  time: string;
  /** The id a person reminder hangs on */
  mentionId: string;
  /** Change the date and time in the card body. */
  update: (next: { date: string; time: string }) => void;
  /** Take the date out of the card body. */
  remove: () => void;
  /** False on a read-only page: the date cannot change, but a person can still set their own reminder. */
  editable: boolean;
};

type TRenderer = (props: TDateMentionRenderProps) => ReactNode;

// The chip needs the web app data layer, which this package must not import.
// The web app registers one renderer at start-up.
let renderer: TRenderer | null = null;

export const registerDateMentionRenderer = (next: TRenderer | null) => {
  renderer = next;
};

export const getDateMentionRenderer = () => renderer;
