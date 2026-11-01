/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { FileText, Plus } from "lucide-react";
import { Button } from "@plane/propel/button";
import { ChevronRightIcon } from "@plane/propel/icons";
import type { TIssue } from "@plane/types";
import { EIssuesStoreType } from "@plane/types";
import { Loader } from "@plane/ui";
import { calculateTimeAgo, cn, generateWorkItemLink } from "@plane/utils";
import { useCommandPalette } from "@/hooks/store/use-command-palette";
import useIssuePeekOverviewRedirection from "@/hooks/use-issue-peek-overview-redirection";
import type { TCardNode } from "@/services/card-tree.service";
import { cardTreeService } from "@/services/card-tree.service";
import { ShortcutRowLabel, rememberShortcutRows, shortcutRowHref } from "@/components/card-links/shortcut-row";
import { CardOpenModeToggle } from "./open-mode-toggle";

type TTreeRow = TCardNode & { children: TTreeRow[] };

/** Nest a flat list by parent. A card whose parent is not in the list sits at the top. */
export function nestCards(cards: TCardNode[]): TTreeRow[] {
  const byId = new Map<string, TTreeRow>(cards.map((card) => [card.id, { ...card, children: [] }]));
  const roots: TTreeRow[] = [];
  byId.forEach((row) => {
    const parent = row.parent_id ? byId.get(row.parent_id) : undefined;
    if (parent && parent !== row) parent.children.push(row);
    else roots.push(row);
  });
  return roots;
}

function PageRow(props: {
  row: TTreeRow;
  depth: number;
  open: Set<string>;
  toggle: (id: string) => void;
  onOpen: (row: TCardNode, nested: boolean) => void;
  hrefFor: (row: TCardNode) => string;
}) {
  const { row, depth, open, toggle, onOpen, hrefFor } = props;
  const isOpen = open.has(row.id);
  const hasChildren = row.children.length > 0;
  return (
    <>
      <div
        className="group flex h-9 items-center gap-2 border-b border-subtle px-4 hover:bg-layer-transparent-hover"
        style={{ paddingLeft: `${16 + depth * 20}px` }}
        data-page-row={`${row.project_identifier}-${row.sequence_id}`}
      >
        <button
          type="button"
          aria-label={isOpen ? `Close ${row.name}` : `Open ${row.name}`}
          aria-expanded={isOpen}
          onClick={() => toggle(row.id)}
          className={cn("grid size-5 flex-shrink-0 place-items-center rounded-sm text-placeholder hover:bg-layer-1", {
            invisible: !hasChildren,
          })}
        >
          <ChevronRightIcon className={cn("size-3.5 transition-transform", { "rotate-90": isOpen })} />
        </button>
        <a
          href={hrefFor(row)}
          onClick={(event) => {
            if (event.metaKey || event.ctrlKey || event.shiftKey) return;
            event.preventDefault();
            onOpen(row, depth > 0);
          }}
          className="flex min-w-0 flex-1 items-center gap-2"
        >
          {row.shortcut ? (
            <ShortcutRowLabel shortcut={row.shortcut} className="text-13 text-primary" iconClassName="size-4" />
          ) : (
            <>
              <FileText className="size-4 flex-shrink-0" style={{ color: row.state_color ?? undefined }} />
              <span className="truncate text-13 text-primary">{row.name || "Untitled"}</span>
            </>
          )}
          {hasChildren && <span className="flex-shrink-0 text-11 text-tertiary">{row.children.length}</span>}
        </a>
        <span className="w-36 flex-shrink-0 truncate text-right text-11 text-tertiary" title={row.updated_at}>
          Edited {calculateTimeAgo(row.updated_at)}
          {row.updated_by_name ? ` by ${row.updated_by_name}` : ""}
        </span>
      </div>
      {isOpen &&
        row.children.map((child) => (
          <PageRow
            key={child.id}
            row={child}
            depth={depth + 1}
            open={open}
            toggle={toggle}
            onOpen={onOpen}
            hrefFor={hrefFor}
          />
        ))}
    </>
  );
}

/** "Page list" project layout: the project's cards as documents, nested by parent, newest edit first. */
export const PageListLayout = observer(function PageListLayout() {
  const { workspaceSlug: routeSlug, projectId: routeProjectId } = useParams();
  const workspaceSlug = routeSlug?.toString() ?? "";
  const projectId = routeProjectId?.toString() ?? "";
  const { toggleCreateIssueModal } = useCommandPalette();
  const { handleRedirection } = useIssuePeekOverviewRedirection();

  const [cards, setCards] = useState<TCardNode[] | undefined>(undefined);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);
  const [open, setOpen] = useState<Set<string>>(new Set());

  const load = useCallback(
    (offset: number, limit?: number) => {
      if (!workspaceSlug || !projectId) return;
      cardTreeService
        .pageList(workspaceSlug, projectId, offset, limit)
        .then((page) => {
          rememberShortcutRows(page.results);
          setCards((previous) => (offset === 0 ? page.results : [...(previous ?? []), ...page.results]));
          setNextOffset(page.next_offset);
          setFailed(false);
        })
        .catch(() => setFailed(true));
    },
    [workspaceSlug, projectId]
  );

  useEffect(() => {
    load(0);
  }, [load]);

  // Pick up cards made or edited elsewhere when the person comes back to the tab,
  // keeping everything already loaded with "Load more" (server caps one page at 1000).
  const shown = cards?.length ?? 0;
  useEffect(() => {
    const onFocus = () => load(0, Math.min(Math.max(shown, 500), 1000));
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [load, shown]);

  const tree = useMemo(() => nestCards(cards ?? []), [cards]);

  const toggle = useCallback((id: string) => {
    setOpen((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const hrefFor = useCallback(
    (row: TCardNode) =>
      shortcutRowHref(
        workspaceSlug,
        row,
        generateWorkItemLink({
          workspaceSlug,
          projectId: row.project_id,
          issueId: row.id,
          projectIdentifier: row.project_identifier,
          sequenceId: row.sequence_id,
        })
      ),
    [workspaceSlug]
  );

  const onOpen = useCallback(
    (row: TCardNode, nested: boolean) =>
      handleRedirection(
        workspaceSlug,
        {
          id: row.id,
          project_id: row.project_id,
          sequence_id: row.sequence_id,
          archived_at: null,
        } as unknown as TIssue,
        false,
        undefined,
        // a page inside a parent page opens in the side panel on a plain click
        nested ? "peek" : undefined
      ),
    [handleRedirection, workspaceSlug]
  );

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      <div className="flex h-11 flex-shrink-0 items-center justify-between gap-2 border-b border-subtle px-4">
        <div className="flex items-center gap-2 text-13 font-medium text-secondary">
          <FileText className="size-4" />
          <span>Pages</span>
          {cards && <span className="text-11 text-tertiary">{cards.length}</span>}
        </div>
        <div className="flex items-center gap-2">
          <CardOpenModeToggle />
          <Button variant="primary" size="sm" onClick={() => toggleCreateIssueModal(true, EIssuesStoreType.PROJECT)}>
            <Plus className="size-3" />
            New page
          </Button>
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        {failed && <p className="p-4 text-13 text-tertiary">Could not load the pages. Reload to try again.</p>}
        {!failed && cards === undefined && (
          <Loader className="space-y-2 p-4">
            <Loader.Item height="28px" />
            <Loader.Item height="28px" />
            <Loader.Item height="28px" />
          </Loader>
        )}
        {cards && cards.length === 0 && (
          <p className="p-4 text-13 text-tertiary">No pages yet. Use "New page" to write the first one.</p>
        )}
        {tree.map((row) => (
          <PageRow key={row.id} row={row} depth={0} open={open} toggle={toggle} onOpen={onOpen} hrefFor={hrefFor} />
        ))}
        {nextOffset !== null && (
          <button
            type="button"
            onClick={() => load(nextOffset)}
            className="w-full py-2 text-center text-12 text-tertiary hover:text-secondary"
          >
            Load more
          </button>
        )}
      </div>
    </div>
  );
});
