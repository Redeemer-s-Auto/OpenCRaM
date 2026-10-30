/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export * from "./extension";
export {
  PageLinkExtensionConfig,
  PAGE_LINK_TAG,
  PAGE_LINK_PAGE_ATTRIBUTE,
  PAGE_LINK_PROJECT_ATTRIBUTE,
  isEntityId,
  pageLinkTargetFromAttrs,
} from "./extension-config";
export type { TPageLinkTarget } from "./extension-config";
