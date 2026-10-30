/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

// Boards inside boards: the sidebar shows projects as a tree built from `parent_id`. A folder board
// (made from a Notion page) also lists its pages, and opens on its landing page.

import type { ReactElement } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// plane imports
import { useLocalStorage } from "@plane/hooks";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { pageHref } from "@/services/page-tree.service";
// local imports
import { SidebarProjectPages, isFolderProject, projectHasPages, usePageTree } from "./pages-tree";
import { SidebarProjectsListItem } from "./projects-list-item";

const NONE_CLOSED: string[] = [];
const NO_CHILDREN: string[] = [];

export type TSidebarProjectTree = {
  /** Top level: projects with no parent, or whose parent is not in the list. In list order. */
  rootIds: string[];
  getChildIds: (projectId: string) => string[];
  isOpen: (projectId: string) => boolean;
  toggleOpen: (projectId: string) => void;
};

/**
 * Arrange sidebar project ids (already in sidebar order) as a tree. Call it from an observer component.
 * Which parents are closed is kept per workspace in localStorage; parents start open.
 */
export const useSidebarProjectTree = (workspaceSlug: string, projectIds: string[]): TSidebarProjectTree => {
  const { getPartialProjectById } = useProject();
  const { storedValue, setValue } = useLocalStorage<string[]>(
    `sidebar_closed_project_parents_${workspaceSlug}`,
    NONE_CLOSED
  );
  const closedIds = Array.isArray(storedValue) ? storedValue : NONE_CLOSED;

  const inList = new Set(projectIds);
  const parentOf = new Map<string, string>();
  const childIds = new Map<string, string[]>();
  const rootIds: string[] = [];
  projectIds.forEach((projectId) => {
    const parentId = getPartialProjectById(projectId)?.parent_id;
    if (parentId && parentId !== projectId && inList.has(parentId)) {
      parentOf.set(projectId, parentId);
      const siblings = childIds.get(parentId);
      if (siblings) siblings.push(projectId);
      else childIds.set(parentId, [projectId]);
    } else rootIds.push(projectId);
  });

  // The API refuses loops, but if one slips in (A inside B inside A) both would vanish: lift it to the top.
  const reached = new Set<string>();
  const visit = (projectId: string) => {
    if (reached.has(projectId)) return;
    reached.add(projectId);
    childIds.get(projectId)?.forEach(visit);
  };
  rootIds.forEach(visit);
  projectIds.forEach((projectId) => {
    if (reached.has(projectId)) return;
    const parentId = parentOf.get(projectId);
    if (parentId) childIds.set(parentId, (childIds.get(parentId) ?? []).filter((id) => id !== projectId));
    rootIds.push(projectId);
    visit(projectId);
  });

  return {
    rootIds,
    getChildIds: (projectId) => childIds.get(projectId) ?? NO_CHILDREN,
    isOpen: (projectId) => !closedIds.includes(projectId),
    toggleOpen: (projectId) =>
      setValue(
        closedIds.includes(projectId) ? closedIds.filter((id) => id !== projectId) : [...closedIds, projectId]
      ),
  };
};

type TSidebarProjectTreeNodeProps = {
  projectId: string;
  tree: TSidebarProjectTree;
  handleCopyText: (projectId: string) => void;
  renderInExtendedSidebar?: boolean;
  /** Projects inside another one are not draggable; reordering is for the top level only. */
  isChild?: boolean;
  isLastChild?: boolean;
  handleOnProjectDrop?: (
    sourceId: string | undefined,
    destinationId: string | undefined,
    shouldDropAtEnd: boolean
  ) => void;
};

/**
 * One project row, followed (when open) by the projects inside it, indented.
 * The return type is spelled out because the component renders itself (TS cannot infer a self-referencing const).
 */
export const SidebarProjectTreeNode = observer(function ProjectTreeNode(
  props: TSidebarProjectTreeNodeProps
): ReactElement {
  const {
    projectId,
    tree,
    handleCopyText,
    renderInExtendedSidebar = false,
    isChild = false,
    isLastChild = false,
    handleOnProjectDrop,
  } = props;
  const childIds = tree.getChildIds(projectId);
  const isOpen = tree.isOpen(projectId);
  // A folder board opens on its landing page and lists its pages before the boards inside it.
  const { workspaceSlug } = useParams();
  const slug = workspaceSlug?.toString() ?? "";
  const { getPartialProjectById } = useProject();
  const isFolder = isFolderProject(getPartialProjectById(projectId));
  const pageTree = usePageTree(isFolder ? slug : "");
  const landing = isFolder ? pageTree.getLandingPage(projectId) : undefined;
  const hasPages = isFolder && projectHasPages(pageTree, projectId);
  const hasChildren = childIds.length > 0 || hasPages;

  return (
    <>
      <SidebarProjectsListItem
        projectId={projectId}
        handleCopyText={() => handleCopyText(projectId)}
        projectListType={"JOINED"}
        disableDrag={isChild}
        disableDrop={isChild}
        isLastChild={isLastChild}
        handleOnProjectDrop={isChild ? undefined : handleOnProjectDrop}
        renderInExtendedSidebar={renderInExtendedSidebar}
        childProjects={hasChildren ? { isOpen, onToggle: () => tree.toggleOpen(projectId) } : undefined}
        landingHref={landing ? pageHref(slug, projectId, landing.id) : undefined}
      />
      {hasChildren && isOpen && (
        <div className="flex flex-col gap-0.5 pl-3">
          {hasPages && <SidebarProjectPages workspaceSlug={slug} projectId={projectId} tree={pageTree} />}
          {childIds.map((childId) => (
            <SidebarProjectTreeNode
              key={childId}
              projectId={childId}
              tree={tree}
              handleCopyText={handleCopyText}
              renderInExtendedSidebar={renderInExtendedSidebar}
              isChild
            />
          ))}
        </div>
      )}
    </>
  );
});
