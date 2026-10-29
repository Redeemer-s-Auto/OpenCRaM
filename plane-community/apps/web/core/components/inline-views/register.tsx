/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { registerInlineViewRenderer } from "@plane/editor";
import { InlineViewBlock } from "./block";

// Import this file once, where a card body editor is built. It teaches the editor how to draw a live view block.
registerInlineViewRenderer((props) => <InlineViewBlock {...props} />);
