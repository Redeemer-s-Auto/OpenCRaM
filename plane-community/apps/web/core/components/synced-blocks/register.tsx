/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { registerSyncedBlockRenderer } from "@plane/editor";
import { SyncedBlockView } from "./block";

// Import this file once, where a card body editor is built. It teaches the editor how to draw a synced block.
registerSyncedBlockRenderer((props) => <SyncedBlockView {...props} />);
