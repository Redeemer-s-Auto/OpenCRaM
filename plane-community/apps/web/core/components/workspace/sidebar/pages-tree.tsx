/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

// Pages inside pages in the sidebar: a folder board (a project made from a Notion page) shows its
// pages as children, each page opening to its sub-pages, like Notion's tree. The rows come from one
// workspace-wide fetch (``/page-tree/``), already filtered for the viewer by the server.

import { useEffect } from "react";
import { observable, runInAction } from "mobx";
import { observer } from "mobx-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useLocalStorage } from "@plane/hooks";
import { ChevronRightIcon } from "@plane/propel/icons";
import type { TPartialProject } from "@plane/types";
import { cn } from "@plane/utils";
import { PageLogo } from "@/components/page-links/page-link-block";
import { SidebarNavItem } from "@/components/sidebar/sidebar-navigation";
import { useAppTheme } from "@/hooks/store/use-app-theme";
import type { TPageTreeNode } from "@/services/page-tree.service";
import { pageHref, pageTreeService } from "@/services/page-tree.service";

const STALE_MS = 60_000;
const MAX_DEPTH = 10;
const NO_PAGES: TPageTreeNode[] = [];
const NONE_OPEN: string[] = [];

/** A board made from a Notion page by the import: it opens on its landing page and holds pages. */
export const isFolderProject = (project: TPartialProject | undefined): boolean =>
  !!project && project.external_source === "notion" && (project.external_id ?? "").startsWith("folder:");

// ---------------------------------------------------------------------------
// One shared copy of the tree per workspace
// ---------------------------------------------------------------------------

type TEntry = { rows: TPageTreeNode[]; at: number; failed: boolean };

const trees = observable.map<string, TEntry>({}, { deep: false });
const loading = new Set<string>();

export function loadPageTree(workspaceSlug: string, force = false) {
  const entry = trees.get(workspaceSlug);
  if (!force && entry && !entry.failed && Date.now() - entry.at < STALE_MS) return;
  if (loading.has(workspaceSlug)) return;
  loading.add(workspaceSlug);
  pageTreeService
    .tree(workspaceSlug)
    .then((rows) => runInAction(() => trees.set(workspaceSlug, { rows, at: Date.now(), failed: false })))
    .catch(() => runInAction(() => trees.set(workspaceSlug, { rows: entry?.rows ?? [], at: Date.now(), failed: true })))
    .finally(() => loading.delete(workspaceSlug));
}

/** Rows of the workspace tree, nested by parent. Call it from an observer component. */
export function usePageTree(workspaceSlug: string) {
  useEffect(() => {
    if (!workspaceSlug) return;
    loadPageTree(workspaceSlug);
    const onFocus = () => loadPageTree(workspaceSlug, true);
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [workspaceSlug]);
  const rows = trees.get(workspaceSlug)?.rows ?? NO_PAGES;
  const byParent = new Map<string, TPageTreeNode[]>();
  const rootsByProject = new Map<string, TPageTreeNode[]>();
  rows.forEach((row) => {
    if (row.parent_id) {
      const siblings = byParent.get(row.parent_id);
      if (siblings) siblings.push(row);
      else byParent.set(row.parent_id, [row]);
    } else {
      const roots = rootsByProject.get(row.project_id);
      if (roots) roots.push(row);
      else rootsByProject.set(row.project_id, [row]);
    }
  });
  return {
    loaded: trees.has(workspaceSlug),
    getChildren: (pageId: string) => byParent.get(pageId) ?? NO_PAGES,
    getRootPages: (projectId: string) => rootsByProject.get(projectId) ?? NO_PAGES,
    /** The page a folder board opens on: the flagged landing page, else its first top-level page. */
    getLandingPage: (projectId: string): TPageTreeNode | undefined => {
      const roots = rootsByProject.get(projectId) ?? NO_PAGES;
      return roots.find((row) => row.is_landing) ?? roots[0];
    },
  };
}

export type TSidebarPageTree = ReturnType<typeof usePageTree>;

/** Which pages are open in the sidebar, per workspace. Pages start closed. */
function useOpenPages(workspaceSlug: string) {
  const { storedValue, setValue } = useLocalStorage<string[]>(`sidebar_open_pages_${workspaceSlug}`, NONE_OPEN);
  const openIds = Array.isArray(storedValue) ? storedValue : NONE_OPEN;
  return {
    isOpen: (pageId: string) => openIds.includes(pageId),
    toggle: (pageId: string) =>
      setValue(openIds.includes(pageId) ? openIds.filter((id) => id !== pageId) : [...openIds, pageId]),
  };
}

type TNodeProps = {
  workspaceSlug: string;
  page: TPageTreeNode;
  tree: TSidebarPageTree;
  open: ReturnType<typeof useOpenPages>;
  depth: number;
};

/** One page row, followed (when open) by its sub-pages, indented. */
const SidebarPageTreeNode = observer(function SidebarPageTreeNode(props: TNodeProps) {
  const { workspaceSlug, page, tree, open, depth } = props;
  const { pageId: activePageId } = useParams();
  const { toggleSidebar } = useAppTheme();
  const children = tree.getChildren(page.id);
  const canOpen = children.length > 0 && depth < MAX_DEPTH;
  const isOpen = canOpen && open.isOpen(page.id);
  const name = page.name || "Untitled";
  return (
    <div className="flex flex-col" data-sidebar-page={page.id}>
      <SidebarNavItem isActive={activePageId?.toString() === page.id}>
        <div className="flex w-full min-w-0 items-center gap-1" style={{ paddingLeft: `${depth * 12}px` }}>
          <button
            type="button"
            aria-label={isOpen ? `Close ${name}` : `Open ${name}`}
            aria-expanded={isOpen}
            disabled={!canOpen}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              open.toggle(page.id);
            }}
            className={cn("grid size-4 flex-shrink-0 place-items-center rounded-sm text-placeholder", {
              invisible: !canOpen,
              "hover:bg-layer-1": canOpen,
            })}
          >
            <ChevronRightIcon className={cn("size-3 transition-transform", { "rotate-90": isOpen })} />
          </button>
          <Link
            href={pageHref(workspaceSlug, page.project_id, page.id)}
            className="flex min-w-0 flex-1 items-center gap-1.5"
            title={name}
            onClick={() => {
              // on a phone the menu is a drawer over the page: it gets out of the way after a tap
              if (window.innerWidth < 768) toggleSidebar(true);
            }}
          >
            <PageLogo logo={page.logo_props} size={14} />
            <span className="truncate text-13">{name}</span>
          </Link>
        </div>
      </SidebarNavItem>
      {isOpen && (
        <div className="flex flex-col gap-0.5">
          {children.map((child) => (
            <SidebarPageTreeNode
              key={child.id}
              workspaceSlug={workspaceSlug}
              page={child}
              tree={tree}
              open={open}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
});

type TProjectPagesProps = {
  workspaceSlug: string;
  projectId: string;
  tree: TSidebarPageTree;
};

/**
 * The pages shown under a folder board: the landing page's sub-pages first (the landing page itself
 * is what the board row opens), then any other top-level page of the board.
 */
export const SidebarProjectPages = observer(function SidebarProjectPages(props: TProjectPagesProps) {
  const { workspaceSlug, projectId, tree } = props;
  const open = useOpenPages(workspaceSlug);
  const landing = tree.getLandingPage(projectId);
  const rows = [
    ...(landing ? tree.getChildren(landing.id) : NO_PAGES),
    ...tree.getRootPages(projectId).filter((row) => row.id !== landing?.id),
  ];
  if (rows.length === 0) return null;
  return (
    <div className="flex flex-col gap-0.5">
      {rows.map((row) => (
        <SidebarPageTreeNode key={row.id} workspaceSlug={workspaceSlug} page={row} tree={tree} open={open} depth={0} />
      ))}
    </div>
  );
});

/** Does the folder board have pages to list under it? */
export const projectHasPages = (tree: TSidebarPageTree, projectId: string): boolean => {
  const landing = tree.getLandingPage(projectId);
  const roots = tree.getRootPages(projectId);
  if (!landing) return roots.length > 0;
  return tree.getChildren(landing.id).length > 0 || roots.length > 1;
};
