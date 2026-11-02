/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

// Boards inside boards: the sidebar shows projects as a tree built from `parent_id`. A folder board
// (made from a Notion page) also lists its pages, and opens on its landing page. Siblings are
// ordered by the shared `position` (set by an import or by dragging), then by the person's own
// `sort_order`, then by name.

import type { ReactElement } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
// plane imports
import { useLocalStorage } from "@plane/hooks";
import type { TPartialProject } from "@plane/types";
// hooks
import { isTaskListHub } from "@/components/task-list-hub/config";
import { useProject } from "@/hooks/store/use-project";
import { pageHref } from "@/services/page-tree.service";
// local imports
import { SidebarProjectPages, isFolderProject, projectHasPages, usePageTree } from "./pages-tree";
import { SidebarProjectsListItem } from "./projects-list-item";

const NONE_CLOSED: string[] = [];
const NO_CHILDREN: string[] = [];
/** Gap between positions handed out in one go; a drop lands halfway between its neighbours. */
const POSITION_STEP = 1000;
/** Below this gap the halfway point stops being exact, so every sibling is numbered afresh. */
const MIN_POSITION_GAP = 1e-6;

const asPosition = (value: number | null | undefined): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

/** Sibling order: position (null last), then the person's own sort_order (null last), then name. */
export const compareSiblingProjects = (a: TPartialProject | undefined, b: TPartialProject | undefined): number => {
  const pa = asPosition(a?.position);
  const pb = asPosition(b?.position);
  if (pa !== null || pb !== null) {
    if (pa === null) return 1;
    if (pb === null) return -1;
    if (pa !== pb) return pa - pb;
  }
  const sa = asPosition(a?.sort_order);
  const sb = asPosition(b?.sort_order);
  if (sa !== null || sb !== null) {
    if (sa === null) return 1;
    if (sb === null) return -1;
    if (sa !== sb) return sa - sb;
  }
  return (a?.name ?? "").localeCompare(b?.name ?? "");
};

/**
 * The positions to save after `movedId` was dropped so that siblings read in `orderedIds` order.
 * One write (halfway between the neighbours) when every other sibling already has an increasing
 * position; otherwise every sibling is numbered afresh, POSITION_STEP apart, in the new order.
 */
export const planSiblingPositions = (
  orderedIds: string[],
  movedId: string,
  getPosition: (projectId: string) => number | null | undefined
): { id: string; position: number }[] => {
  const index = orderedIds.indexOf(movedId);
  if (index < 0) return [];
  const renumber = () => orderedIds.map((id, i) => ({ id, position: (i + 1) * POSITION_STEP }));
  const others = orderedIds.filter((id) => id !== movedId).map((id) => asPosition(getPosition(id)));
  const increasing = others.every((p, i) => p !== null && (i === 0 || p > (others[i - 1] as number)));
  if (!increasing) return renumber();
  const prev = index > 0 ? asPosition(getPosition(orderedIds[index - 1])) : null;
  const next = index < orderedIds.length - 1 ? asPosition(getPosition(orderedIds[index + 1])) : null;
  if (prev !== null && next !== null) {
    if (next - prev < MIN_POSITION_GAP) return renumber();
    return [{ id: movedId, position: (prev + next) / 2 }];
  }
  if (prev !== null) return [{ id: movedId, position: prev + POSITION_STEP }];
  if (next !== null) return [{ id: movedId, position: next - POSITION_STEP }];
  return [{ id: movedId, position: POSITION_STEP }];
};

export type TSidebarProjectTree = {
  /** Top level: projects with no parent, or whose parent is not in the list. In sibling order. */
  rootIds: string[];
  getChildIds: (projectId: string) => string[];
  isOpen: (projectId: string) => boolean;
  toggleOpen: (projectId: string) => void;
};

/**
 * Arrange sidebar project ids as a tree, each level in sibling order. Call it from an observer component.
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
  const byId = (projectId: string) => getPartialProjectById(projectId);
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
    if (parentId)
      childIds.set(
        parentId,
        (childIds.get(parentId) ?? []).filter((id) => id !== projectId)
      );
    rootIds.push(projectId);
    visit(projectId);
  });

  const sortSiblings = (ids: string[]) => ids.sort((a, b) => compareSiblingProjects(byId(a), byId(b)));
  sortSiblings(rootIds);
  childIds.forEach(sortSiblings);

  return {
    rootIds,
    getChildIds: (projectId) => childIds.get(projectId) ?? NO_CHILDREN,
    isOpen: (projectId) => !closedIds.includes(projectId),
    toggleOpen: (projectId) =>
      setValue(closedIds.includes(projectId) ? closedIds.filter((id) => id !== projectId) : [...closedIds, projectId]),
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
  const project = getPartialProjectById(projectId);
  const isFolder = isFolderProject(project);
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
        // The Task Lists Hub opens on its lists (the hub screen), not on its page.
        landingHref={landing && !isTaskListHub(project?.identifier) ? pageHref(slug, projectId, landing.id) : undefined}
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
