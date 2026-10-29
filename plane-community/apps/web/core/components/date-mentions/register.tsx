/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { registerDateMentionRenderer } from "@plane/editor";
import { DateMentionChip } from "./chip";

// Import this file once, where a card body editor is built. It teaches the editor how to draw a date mention.
registerDateMentionRenderer((props) => <DateMentionChip {...props} />);
