/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { observer } from "mobx-react";
import { Outlet, useParams } from "react-router";
// plane imports
import { Header, Row } from "@plane/ui";
import { cn } from "@plane/utils";
// components
import { TabNavigationRoot } from "@/components/navigation/tab-navigation-root";
import { AppSidebarToggleButton } from "@/components/sidebar/sidebar-toggle-button";
// hooks
import { useAppTheme } from "@/hooks/store/use-app-theme";
import { useProjectNavigationPreferences } from "@/hooks/use-navigation-preferences";
// layouts
import { ProjectAuthWrapper } from "@/layouts/auth-layout/project-wrapper";
// services
import { ViewService } from "@/services/view.service";
// local imports
import type { Route } from "./+types/layout";

const viewService = new ViewService();

function ProjectLayout({ params }: Route.ComponentProps) {
  // router
  const { workspaceSlug, projectId } = params;
  const { viewId } = useParams();
  // A view (a task list tab) waits for the board's details before it asks for its own. Ask now, beside them.
  useEffect(() => {
    if (viewId) viewService.prefetchViewDetails(workspaceSlug, projectId, viewId);
  }, [workspaceSlug, projectId, viewId]);
  // store hooks
  const { sidebarCollapsed } = useAppTheme();
  // preferences
  const { preferences: projectPreferences } = useProjectNavigationPreferences();

  return (
    <>
      {projectPreferences.navigationMode === "TABBED" && (
        <div className="z-20">
          <Row className="flex h-header w-full items-center gap-2 border-b border-subtle bg-surface-1">
            <div className="flex h-full w-full items-center gap-2 divide-x divide-subtle">
              <div className="flex size-full flex-1 items-center gap-2">
                {sidebarCollapsed && (
                  <div className="shrink-0">
                    <AppSidebarToggleButton />
                  </div>
                )}
                <Header className={cn("h-full", { "pl-1.5": !sidebarCollapsed })}>
                  <Header.LeftItem className="flex h-full max-w-full items-center gap-2">
                    <TabNavigationRoot workspaceSlug={workspaceSlug} projectId={projectId} />
                  </Header.LeftItem>
                </Header>
              </div>
            </div>
          </Row>
        </div>
      )}
      <ProjectAuthWrapper workspaceSlug={workspaceSlug} projectId={projectId}>
        <Outlet />
      </ProjectAuthWrapper>
    </>
  );
}

export default observer(ProjectLayout);
