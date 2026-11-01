/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TIdentifierTextProps } from "@plane/types";

// Team ruling 2026-10-31: the card ID (like TDL-2102) is not shown anywhere in the UI.
// The ID stays in the data and the API; only the display is removed.
export function IdentifierText(_props: TIdentifierTextProps) {
  return null;
}
