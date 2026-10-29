/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ChevronRightIcon } from "@plane/propel/icons";
import { CornerUpRight, Link2 } from "lucide-react";
import { cn } from "@plane/utils";
import type { TBacklink } from "@/services/card-links.service";
import { cardLinksService } from "@/services/card-links.service";
import { LinkedCardIcon } from "./card-link-chip";
import { linkedCardHref } from "./store";

type Props = {
  workspaceSlug: string;
  issueId: string;
  className?: string;
};

/**
 * "Linked from": cards whose body links to this card, and shortcut cards that point
 * to it. Only cards the viewer may see are listed (the server leaves the rest out).
 */
export function CardBacklinks(props: Props) {
  const { workspaceSlug, issueId, className } = props;
  const [rows, setRows] = useState<TBacklink[] | undefined>(undefined);
  const [open, setOpen] = useState(true);

  const load = useCallback(() => {
    cardLinksService
      .backlinks(workspaceSlug, issueId)
      .then(setRows)
      .catch(() => setRows([]));
  }, [workspaceSlug, issueId]);

  useEffect(() => {
    setRows(undefined);
    load();
    window.addEventListener("focus", load);
    return () => window.removeEventListener("focus", load);
  }, [load]);

  if (!rows || rows.length === 0) return null;

  return (
    <section className={cn("flex flex-col gap-1", className)} data-card-backlinks={rows.length}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex items-center gap-1 text-13 font-medium text-secondary hover:text-primary"
      >
        <ChevronRightIcon className={cn("size-3.5 transition-transform", { "rotate-90": open })} />
        Linked from
        <span className="text-tertiary">{rows.length}</span>
      </button>
      {open && (
        <ul className="flex flex-col gap-0.5 pl-4">
          {rows.map((row) => (
            <li key={`${row.kind}-${row.id}`}>
              <Link
                // A shortcut opens this very card again, so it links to the board it sits on.
                href={
                  row.kind === "shortcut"
                    ? `/${workspaceSlug}/projects/${row.project_id}/issues/`
                    : linkedCardHref(workspaceSlug, row)
                }
                className="flex min-w-0 items-center gap-2 rounded-sm px-1.5 py-1 text-13 hover:bg-layer-1-hover"
                title={row.kind === "shortcut" ? `Shortcut on ${row.project_name}` : row.name}
              >
                {row.kind === "shortcut" ? (
                  <CornerUpRight className="size-3.5 flex-shrink-0 text-placeholder" />
                ) : (
                  <Link2 className="size-3.5 flex-shrink-0 text-placeholder" />
                )}
                <LinkedCardIcon card={row} />
                <span className="truncate text-primary">
                  {row.kind === "shortcut" ? `Shortcut on ${row.project_name}` : row.name || "Untitled"}
                </span>
                <span className="ml-auto flex-shrink-0 text-11 text-tertiary">
                  {row.project_name} · {row.project_identifier}-{row.sequence_id}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
