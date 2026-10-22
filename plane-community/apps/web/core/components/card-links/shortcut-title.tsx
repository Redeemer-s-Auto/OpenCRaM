/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { CornerUpRight } from "lucide-react";
import { cn } from "@plane/utils";
import { UnavailableCard } from "./card-link-chip";
import { getShortcutTarget, useProjectShortcuts } from "./store";

type Props = {
  workspaceSlug: string | undefined;
  projectId: string | null | undefined;
  issueId: string;
  /** the card's own name, shown for normal cards */
  name: string;
  className?: string;
};

/**
 * A card's title on a board. A shortcut card shows a small arrow and its target's live
 * title, or "Hidden card" / "Card removed" when the viewer may not see the target.
 */
export const ShortcutAwareTitle = observer(function ShortcutAwareTitle(props: Props) {
  const { workspaceSlug, projectId, issueId, name, className } = props;
  useProjectShortcuts(workspaceSlug, projectId);
  const target = getShortcutTarget(issueId);
  if (!target) return <span className={className}>{name}</span>;
  return (
    <span className={cn("inline-flex max-w-full min-w-0 items-center gap-1", className)} data-shortcut-card={issueId}>
      <CornerUpRight className="size-3.5 flex-shrink-0 text-placeholder" aria-label="Shortcut" />
      {target.status === "visible" ? (
        <span className="truncate">{target.card.name || "Untitled"}</span>
      ) : (
        <UnavailableCard status={target.status} />
      )}
    </span>
  );
});

/** Plain-text title for tooltips: never more than the viewer may know. */
export function shortcutAwareName(issueId: string, name: string) {
  const target = getShortcutTarget(issueId);
  if (!target) return name;
  if (target.status === "visible") return target.card.name;
  return target.status === "hidden" ? "Hidden card" : "Card removed";
}
