/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// components
import { Outlet } from "react-router";
import { AppHeader } from "@/components/core/app-header";
import { ContentWrapper } from "@/components/core/content-wrapper";
import { ProjectIssuesHeader } from "./header";

export default function ProjectIssuesLayout() {
  return (
    <>
      {/* One header row on every width: the phone-only button row was folded into it. */}
      <AppHeader header={<ProjectIssuesHeader />} rowClassName="h-auto min-h-11" />
      <ContentWrapper>
        <Outlet />
      </ContentWrapper>
    </>
  );
}
