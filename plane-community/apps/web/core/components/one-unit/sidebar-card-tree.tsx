/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { FileText } from "lucide-react";
import { ChevronRightIcon } from "@plane/propel/icons";
import { cn } from "@plane/utils";
import { SidebarNavItem } from "@/components/sidebar/sidebar-navigation";
import type { TCardNode, TCardPage } from "@/services/card-tree.service";
import { cardTreeService } from "@/services/card-tree.service";
import { ShortcutRowLabel, rememberShortcutRows, shortcutRowHref } from "@/components/card-links/shortcut-row";
import { CARD_TREE_PAGE_SIZE } from "./flags";

const MAX_DEPTH = 8;

type TLoader = (offset: number, limit?: number) => Promise<TCardPage>;

/** Loads one level of the tree lazily, with "Show more" paging. */
function useLevel(load: TLoader, enabled: boolean) {
  const [rows, setRows] = useState<TCardNode[] | undefined>(undefined);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);

  const fetchPage = useCallback(
    (offset: number, limit?: number) => {
      setBusy(true);
      load(offset, limit)
        .then((page) => {
          rememberShortcutRows(page.results);
          setRows((previous) => (offset === 0 ? page.results : [...(previous ?? []), ...page.results]));
          setNextOffset(page.next_offset);
          setFailed(false);
        })
        .catch(() => setFailed(true))
        .finally(() => setBusy(false));
    },
    [load]
  );

  useEffect(() => {
    if (enabled && rows === undefined) fetchPage(0);
  }, [enabled, rows, fetchPage]);

  // Coming back to the tab reloads what is already shown (names, new and moved cards).
  const shown = rows?.length ?? 0;
  useEffect(() => {
    if (!enabled) return;
    const onFocus = () => fetchPage(0, Math.min(Math.max(shown, CARD_TREE_PAGE_SIZE), 200));
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [enabled, shown, fetchPage]);

  return { rows, nextOffset, failed, busy, more: () => nextOffset !== null && fetchPage(nextOffset) };
}

function TreeLevel(props: { workspaceSlug: string; load: TLoader; depth: number }) {
  const { workspaceSlug, load, depth } = props;
  const { rows, nextOffset, failed, busy, more } = useLevel(load, true);
  if (failed) return <p className="px-2 py-1 text-11 text-tertiary">Could not load cards</p>;
  if (rows === undefined) return <p className="px-2 py-1 text-11 text-tertiary">Loading…</p>;
  if (rows.length === 0 && depth === 0) return <p className="px-2 py-1 text-11 text-tertiary">No cards yet</p>;
  return (
    <>
      {rows.map((node) => (
        <TreeNode key={node.id} workspaceSlug={workspaceSlug} node={node} depth={depth} />
      ))}
      {nextOffset !== null && (
        <button
          type="button"
          disabled={busy}
          onClick={more}
          className="py-0.5 text-left text-11 text-tertiary hover:text-secondary"
          style={{ paddingLeft: `${depth * 12 + 22}px` }}
        >
          {busy ? "Loading…" : "Show more"}
        </button>
      )}
    </>
  );
}

function TreeNode(props: { workspaceSlug: string; node: TCardNode; depth: number }) {
  const { workspaceSlug, node, depth } = props;
  const { workItem } = useParams();
  const [open, setOpen] = useState(false);
  const identifier = `${node.project_identifier}-${node.sequence_id}`;
  const href = shortcutRowHref(workspaceSlug, node, `/${workspaceSlug}/browse/${identifier}/`);
  const canOpen = node.child_count > 0 && depth < MAX_DEPTH;
  const loadChildren = useCallback(
    (offset: number, limit?: number) => cardTreeService.children(workspaceSlug, node.id, offset, limit),
    [workspaceSlug, node.id]
  );

  return (
    <div className="flex flex-col" data-card-tree-node={identifier}>
      <SidebarNavItem isActive={workItem?.toString() === identifier}>
        <div className="flex w-full items-center gap-1" style={{ paddingLeft: `${depth * 12}px` }}>
          <button
            type="button"
            aria-label={open ? `Close ${node.name}` : `Open ${node.name}`}
            aria-expanded={open}
            disabled={!canOpen}
            onClick={() => setOpen((value) => !value)}
            className={cn("grid size-4 flex-shrink-0 place-items-center rounded-sm text-placeholder", {
              invisible: !canOpen,
              "hover:bg-layer-1": canOpen,
            })}
          >
            <ChevronRightIcon className={cn("size-3 transition-transform", { "rotate-90": open })} />
          </button>
          <Link
            href={href}
            className="flex min-w-0 flex-1 items-center gap-1.5"
            title={node.shortcut ? undefined : node.name}
          >
            {node.shortcut ? (
              <ShortcutRowLabel shortcut={node.shortcut} className="text-12" />
            ) : (
              <>
                <FileText className="size-3.5 flex-shrink-0" style={{ color: node.state_color ?? undefined }} />
                <span className="truncate text-12">{node.name || "Untitled"}</span>
              </>
            )}
          </Link>
        </div>
      </SidebarNavItem>
      {open && <TreeLevel workspaceSlug={workspaceSlug} load={loadChildren} depth={depth + 1} />}
    </div>
  );
}

/** localStorage key: "1" when a person has the Cards tree of this board open. */
const openKey = (projectId: string) => `card-tree-open:${projectId}`;

const readOpen = (projectId: string) => {
  try {
    return window.localStorage.getItem(openKey(projectId)) === "1";
  } catch {
    return false;
  }
};

const writeOpen = (projectId: string, open: boolean) => {
  try {
    if (open) window.localStorage.setItem(openKey(projectId), "1");
    else window.localStorage.removeItem(openKey(projectId));
  } catch {
    // private mode or storage off: the tree still opens, it just forgets
  }
};

/**
 * Sidebar tree under a project: its top cards, each opening to its sub-cards (from any project).
 * Closed until opened (then remembered per board), so opening a big board does not also load
 * its card tree in the sidebar.
 */
export function SidebarCardTree(props: { workspaceSlug: string; projectId: string }) {
  const { workspaceSlug, projectId } = props;
  const [open, setOpenState] = useState(() => readOpen(projectId));
  const setOpen = (update: (value: boolean) => boolean) =>
    setOpenState((value) => {
      const next = update(value);
      writeOpen(projectId, next);
      return next;
    });
  const loadRoots = useCallback(
    (offset: number, limit?: number) => cardTreeService.projectRoots(workspaceSlug, projectId, offset, limit),
    [workspaceSlug, projectId]
  );
  return (
    <div className="mt-0.5 flex flex-col gap-0.5">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex items-center gap-1 px-2 py-0.5 text-left text-11 font-medium text-tertiary hover:text-secondary"
      >
        <ChevronRightIcon className={cn("size-3 transition-transform", { "rotate-90": open })} />
        Cards
      </button>
      {open && <TreeLevel workspaceSlug={workspaceSlug} load={loadRoots} depth={0} />}
    </div>
  );
}
