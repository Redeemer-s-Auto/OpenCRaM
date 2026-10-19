/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// mobx store
// components
import { ModuleIssueQuickActions } from "../../quick-action-dropdowns";
import { BaseGalleryRoot } from "../base-gallery-root";

export const ModuleGalleryLayout = observer(function ModuleGalleryLayout() {
  const { moduleId } = useParams();

  return <BaseGalleryRoot QuickActions={ModuleIssueQuickActions} viewId={moduleId?.toString()} />;
});
