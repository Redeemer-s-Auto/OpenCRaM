/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// ui
import { EUserPermissions, EUserPermissionsLevel, PROJECT_VIEW_TRACKER_ELEMENTS } from "@plane/constants";
import { Button } from "@plane/propel/button";
import { ViewsIcon } from "@plane/propel/icons";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { Breadcrumbs, Header } from "@plane/ui";
// components
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";
import { ViewListHeader } from "@/components/views/view-list-header";
// hooks
import { useCommandPalette } from "@/hooks/store/use-command-palette";
import { useProject } from "@/hooks/store/use-project";
import { useProjectView } from "@/hooks/store/use-project-view";
import { useUserPermissions } from "@/hooks/store/user";
// plane web imports
import { CommonProjectBreadcrumbs } from "@/components/breadcrumbs/common";

export const ProjectViewsHeader = observer(function ProjectViewsHeader() {
  const { workspaceSlug, projectId } = useParams();
  // states
  const [addingTaskList, setAddingTaskList] = useState(false);
  // store hooks
  const { toggleCreateViewModal } = useCommandPalette();
  const { loader } = useProject();
  const { addTaskListViews } = useProjectView();
  const { allowPermissions } = useUserPermissions();
  // derived values
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);

  // One click gives a board the task-list set: a Seen checkbox and the Active / Completed / Checked views.
  const handleAddTaskListViews = async () => {
    if (!workspaceSlug || !projectId) return;
    setAddingTaskList(true);
    try {
      const result = await addTaskListViews(workspaceSlug.toString(), projectId.toString());
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: result.created.length ? "Task list views added" : "Task list views already here",
        message: result.created.length
          ? `${result.created.join(", ")} and the "${result.field.name}" checkbox are ready.`
          : "Active, Completed and Checked were already set up; their filters were refreshed.",
      });
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not add the views", message: "Try again." });
    } finally {
      setAddingTaskList(false);
    }
  };

  return (
    <>
      <Header>
        <Header.LeftItem>
          <Breadcrumbs isLoading={loader === "init-loader"}>
            <CommonProjectBreadcrumbs workspaceSlug={workspaceSlug?.toString()} projectId={projectId?.toString()} />
            <Breadcrumbs.Item
              component={
                <BreadcrumbLink
                  label="Views"
                  href={`/${workspaceSlug}/projects/${projectId}/views/`}
                  icon={<ViewsIcon className="h-4 w-4 text-tertiary" />}
                  isLast
                />
              }
              isLast
            />
          </Breadcrumbs>
        </Header.LeftItem>
        <Header.RightItem>
          <ViewListHeader />
          {isAdmin && (
            <div className="hidden md:block">
              <Button
                variant="secondary"
                size="lg"
                onClick={() => void handleAddTaskListViews()}
                disabled={addingTaskList}
              >
                Add task list views
              </Button>
            </div>
          )}
          <div>
            <Button
              data-ph-element={PROJECT_VIEW_TRACKER_ELEMENTS.RIGHT_HEADER_ADD_BUTTON}
              variant="primary"
              size="lg"
              onClick={() => toggleCreateViewModal(true)}
            >
              Add view
            </Button>
          </div>
        </Header.RightItem>
      </Header>
    </>
  );
});
