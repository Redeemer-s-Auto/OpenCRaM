/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// components
import { PageHead } from "@/components/core/page-title";
import { ProjectLayoutRoot } from "@/components/issues/issue-layouts/roots/project-layout-root";
// hooks
import { useProject } from "@/hooks/store/use-project";
import type { Route } from "./+types/page";

function ProjectIssuesPage({ params }: Route.ComponentProps) {
  const { projectId } = params;
  // store
  const { getProjectById } = useProject();

  // derived values
  const project = getProjectById(projectId);
  // The tab reads as the board ("Guisselle's Task List - Notes") with the board's icon.
  const pageTitle = project?.name ? project.name : undefined;

  return (
    <>
      <PageHead title={pageTitle} logo={project?.logo_props} />
      <div className="h-full w-full">
        <ProjectLayoutRoot />
      </div>
    </>
  );
}

export default observer(ProjectIssuesPage);
