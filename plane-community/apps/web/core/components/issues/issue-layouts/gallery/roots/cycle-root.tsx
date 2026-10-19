/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React, { useCallback } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// hooks
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useCycle } from "@/hooks/store/use-cycle";
import { useUserPermissions } from "@/hooks/store/user";
// components
import { CycleIssueQuickActions } from "../../quick-action-dropdowns";
import { BaseGalleryRoot } from "../base-gallery-root";

export const CycleGalleryLayout = observer(function CycleGalleryLayout() {
  // router
  const { cycleId } = useParams();
  // store hooks
  const { currentProjectCompletedCycleIds } = useCycle();
  const { allowPermissions } = useUserPermissions();
  // auth
  const isCompletedCycle =
    cycleId && currentProjectCompletedCycleIds ? currentProjectCompletedCycleIds.includes(cycleId.toString()) : false;
  const isEditingAllowed = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.PROJECT
  );

  const canEditIssueProperties = useCallback(
    () => !isCompletedCycle && isEditingAllowed,
    [isCompletedCycle, isEditingAllowed]
  );

  if (!cycleId) return null;

  return (
    <BaseGalleryRoot
      QuickActions={CycleIssueQuickActions}
      canEditPropertiesBasedOnProject={canEditIssueProperties}
      isCompletedCycle={isCompletedCycle}
      viewId={cycleId.toString()}
    />
  );
});
