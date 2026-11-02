/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Outlet } from "react-router";
import { AppHeader } from "@/components/core/app-header";
import { ContentWrapper } from "@/components/core/content-wrapper";
// local components
import { ProjectViewIssuesHeader } from "./[viewId]/header";

export default function ProjectViewIssuesLayout() {
  return (
    <>
      {/* auto height: on a narrow screen the buttons wrap under the board name */}
      <AppHeader header={<ProjectViewIssuesHeader />} rowClassName="h-auto min-h-11" />
      <ContentWrapper>
        <Outlet />
      </ContentWrapper>
    </>
  );
}
