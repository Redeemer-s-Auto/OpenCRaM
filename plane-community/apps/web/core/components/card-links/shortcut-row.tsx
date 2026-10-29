/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { CornerUpRight } from "lucide-react";
import { cn } from "@plane/utils";
import type { TCardResolution } from "@/services/card-links.service";
import { UnavailableCard } from "./card-link-chip";
import { linkedCardHref, setShortcutTarget } from "./store";

type TRowWithShortcut = { id: string; shortcut?: TCardResolution | null };

/** Remember where the shortcut rows of a tree or list go, so a click opens the target. */
export function rememberShortcutRows(rows: TRowWithShortcut[]) {
  rows.forEach((row) => {
    if (row.shortcut) setShortcutTarget(row.id, row.shortcut);
  });
}

/** Where a row opens: a visible shortcut opens its target, anything else its own page. */
export function shortcutRowHref(workspaceSlug: string, row: TRowWithShortcut, ownHref: string) {
  return row.shortcut?.status === "visible" ? linkedCardHref(workspaceSlug, row.shortcut.card) : ownHref;
}

/** Arrow + target title (or "Hidden card" / "Card removed") for a shortcut row in the tree or page list. */
export function ShortcutRowLabel(props: { shortcut: TCardResolution; className?: string; iconClassName?: string }) {
  const { shortcut, className, iconClassName } = props;
  return (
    <span className={cn("flex min-w-0 items-center gap-1.5", className)} data-shortcut-row={shortcut.status}>
      <CornerUpRight className={cn("size-3.5 flex-shrink-0 text-placeholder", iconClassName)} aria-label="Shortcut" />
      {shortcut.status === "visible" ? (
        <>
          <span
            className="size-2 flex-shrink-0 rounded-full"
            style={{ backgroundColor: shortcut.card.state_color ?? "var(--text-color-placeholder)" }}
          />
          <span className="truncate">{shortcut.card.name || "Untitled"}</span>
        </>
      ) : (
        <UnavailableCard status={shortcut.status} />
      )}
    </span>
  );
}
