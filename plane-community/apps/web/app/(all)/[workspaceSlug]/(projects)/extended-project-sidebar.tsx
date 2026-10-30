/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useRef, useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// plane imports
import { EUserPermissions, EUserPermissionsLevel, PROJECT_TRACKER_ELEMENTS } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { EmptyStateCompact } from "@plane/propel/empty-state";
import { PlusIcon, SearchIcon } from "@plane/propel/icons";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { Tooltip } from "@plane/propel/tooltip";
import { copyUrlToClipboard } from "@plane/utils";
// components
import { CreateProjectModal } from "@/components/project/create-project-modal";
import {
  SidebarProjectSection,
  SidebarTeamspaceGroup,
  groupSidebarRoots,
} from "@/components/workspace/sidebar/projects-sections";
import {
  SidebarProjectTreeNode,
  planSiblingPositions,
  useSidebarProjectTree,
} from "@/components/workspace/sidebar/projects-tree";
// hooks
import { useAppTheme } from "@/hooks/store/use-app-theme";
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";
import { ExtendedSidebarWrapper } from "./extended-sidebar-wrapper";

export const ExtendedProjectSidebar = observer(function ExtendedProjectSidebar() {
  // refs
  const extendedProjectSidebarRef = useRef<HTMLDivElement | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>("");
  // states
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  // routers
  const { workspaceSlug } = useParams();
  // store hooks
  const { t } = useTranslation();
  const { isExtendedProjectSidebarOpened, toggleExtendedProjectSidebar } = useAppTheme();
  const { getPartialProjectById, joinedProjectIds: joinedProjects, updateProject } = useProject();
  const { allowPermissions } = useUserPermissions();

  // filter projects based on search query
  const filteredProjects = joinedProjects.filter((projectId) => {
    const project = getPartialProjectById(projectId);
    if (!project) return false;
    return project.name.toLowerCase().includes(searchQuery.toLowerCase()) || project.identifier.includes(searchQuery);
  });
  // A match whose parent did not match shows at the top level.
  const projectTree = useSidebarProjectTree(workspaceSlug?.toString() ?? "", filteredProjects);
  // Same three sections as the sidebar: Private, Teamspaces, then the workspace projects.
  const sections = groupSidebarRoots(projectTree.rootIds, getPartialProjectById);
  const hasPlacedProjects = sections.privateIds.length > 0 || sections.teamspaces.length > 0;
  const slug = workspaceSlug?.toString() ?? "";

  // Same rule as the sidebar: a top-level workspace board lands before the one it was dropped on
  // (or last) and the shared `position` of the boards involved is saved.
  const handleOnProjectDrop = (
    sourceId: string | undefined,
    destinationId: string | undefined,
    shouldDropAtEnd: boolean
  ) => {
    if (!sourceId || !destinationId || !slug) return;
    if (sourceId === destinationId) return;
    const siblings = sections.workspaceIds;
    if (!siblings.includes(sourceId) || !siblings.includes(destinationId)) return;

    const others = siblings.filter((projectId) => projectId !== sourceId);
    const at = others.indexOf(destinationId) + (shouldDropAtEnd ? 1 : 0);
    const ordered = [...others.slice(0, at), sourceId, ...others.slice(at)];
    const positionOf = (projectId: string) => getPartialProjectById(projectId)?.position;
    const updates = planSiblingPositions(ordered, sourceId, positionOf);

    Promise.all(updates.map((update) => updateProject(slug, update.id, { position: update.position }))).catch(() => {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("error"),
        message: t("something_went_wrong"),
      });
    });
  };

  // auth
  const isAuthorizedUser = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.WORKSPACE
  );

  const handleClose = useCallback(() => toggleExtendedProjectSidebar(false), [toggleExtendedProjectSidebar]);

  const handleCopyText = (projectId: string) => {
    copyUrlToClipboard(`${workspaceSlug}/projects/${projectId}/issues`).then(() => {
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: t("link_copied"),
        message: t("project_link_copied_to_clipboard"),
      });
    });
  };
  return (
    <>
      {workspaceSlug && (
        <CreateProjectModal
          isOpen={isProjectModalOpen}
          onClose={() => setIsProjectModalOpen(false)}
          setToFavorite={false}
          workspaceSlug={workspaceSlug.toString()}
        />
      )}
      <ExtendedSidebarWrapper
        isExtendedSidebarOpened={!!isExtendedProjectSidebarOpened}
        extendedSidebarRef={extendedProjectSidebarRef}
        handleClose={handleClose}
        excludedElementId="extended-project-sidebar-toggle"
        className="px-0"
      >
        <div className="sticky top-4 flex w-full flex-col gap-1 px-4">
          <div className="flex items-center justify-between">
            <span className="py-1.5 text-13 font-semibold text-tertiary">Projects</span>
            {isAuthorizedUser && (
              <Tooltip tooltipHeading={t("create_project")} tooltipContent="">
                <button
                  type="button"
                  data-ph-element={PROJECT_TRACKER_ELEMENTS.EXTENDED_SIDEBAR_ADD_BUTTON}
                  className="flex-shrink-0 rounded-sm p-0.5 text-tertiary transition-colors hover:bg-layer-1 hover:text-secondary"
                  onClick={() => {
                    setIsProjectModalOpen(true);
                  }}
                >
                  <PlusIcon className="size-3" />
                </button>
              </Tooltip>
            )}
          </div>
          <div className="ml-auto flex w-full items-center gap-1.5 rounded-md border border-subtle bg-surface-1 px-2.5 py-1">
            <SearchIcon className="h-3.5 w-3.5 text-placeholder" />
            <input
              className="w-full max-w-[234px] border-none bg-transparent text-13 outline-none placeholder:text-placeholder"
              placeholder={t("search")}
              value={searchQuery}
              autoFocus
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
        </div>
        {filteredProjects.length === 0 ? (
          <div className="mt-4 flex flex-col items-center p-10">
            <EmptyStateCompact
              title={t("common_empty_state.search.title")}
              description={t("common_empty_state.search.description")}
              assetKey="search"
              assetClassName="size-20"
              align="center"
            />
          </div>
        ) : (
          <div className="vertical-scrollbar mt-4 flex scrollbar-sm flex-grow flex-col gap-0.5 overflow-x-hidden overflow-y-auto pr-2 pl-9">
            {sections.privateIds.length > 0 && (
              <SidebarProjectSection storageKey={`extended_private_section_open_${slug}`} title="Private">
                {sections.privateIds.map((projectId, index) => (
                  <SidebarProjectTreeNode
                    key={projectId}
                    projectId={projectId}
                    tree={projectTree}
                    handleCopyText={handleCopyText}
                    isChild
                    isLastChild={index === sections.privateIds.length - 1}
                    renderInExtendedSidebar
                  />
                ))}
              </SidebarProjectSection>
            )}
            {sections.teamspaces.length > 0 && (
              <SidebarProjectSection storageKey={`extended_teamspaces_section_open_${slug}`} title="Teamspaces">
                {sections.teamspaces.map((teamspace) => (
                  <SidebarTeamspaceGroup key={teamspace.id} workspaceSlug={slug} teamspace={teamspace}>
                    {teamspace.rootIds.map((projectId, index) => (
                      <SidebarProjectTreeNode
                        key={projectId}
                        projectId={projectId}
                        tree={projectTree}
                        handleCopyText={handleCopyText}
                        isChild
                        isLastChild={index === teamspace.rootIds.length - 1}
                        renderInExtendedSidebar
                      />
                    ))}
                  </SidebarTeamspaceGroup>
                ))}
              </SidebarProjectSection>
            )}
            {sections.workspaceIds.length > 0 && hasPlacedProjects && (
              <span className="px-2 py-1.5 text-13 font-semibold text-placeholder">Projects</span>
            )}
            {sections.workspaceIds.map((projectId, index) => (
              <SidebarProjectTreeNode
                key={projectId}
                projectId={projectId}
                tree={projectTree}
                handleCopyText={handleCopyText}
                isLastChild={index === sections.workspaceIds.length - 1}
                handleOnProjectDrop={handleOnProjectDrop}
                renderInExtendedSidebar
              />
            ))}
          </div>
        )}
      </ExtendedSidebarWrapper>
    </>
  );
});
