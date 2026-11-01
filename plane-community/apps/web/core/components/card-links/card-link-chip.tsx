/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import Link from "next/link";
import { CornerUpRight, EyeOff, FileX } from "lucide-react";
import { StateGroupIcon } from "@plane/propel/icons";
import type { TStateGroups } from "@plane/types";
import { cn } from "@plane/utils";
import type { TCardResolution, TLinkedCard } from "@/services/card-links.service";
import { HIDDEN_CARD_LABEL, REMOVED_CARD_LABEL, linkedCardHref } from "./store";

/** The card's state icon in its colour (a plain dot when the state is unknown). */
export function LinkedCardIcon(props: { card: Pick<TLinkedCard, "state_group" | "state_color">; className?: string }) {
  const { card, className } = props;
  if (card.state_group && card.state_group !== "triage") {
    return (
      <span className={cn("grid size-4 flex-shrink-0 place-items-center", className)}>
        <StateGroupIcon stateGroup={card.state_group as TStateGroups} color={card.state_color ?? undefined} />
      </span>
    );
  }
  return (
    <span
      className={cn("size-2.5 flex-shrink-0 rounded-full", className)}
      style={{ backgroundColor: card.state_color ?? "var(--text-color-placeholder)" }}
    />
  );
}

/** "Hidden card" / "Card removed": the same words for every case, no other detail. */
export function UnavailableCard(props: { status: "hidden" | "removed"; className?: string }) {
  const { status, className } = props;
  const Icon = status === "hidden" ? EyeOff : FileX;
  return (
    <span className={cn("flex min-w-0 items-center gap-1.5 text-tertiary", className)} data-card-link-state={status}>
      <Icon className="size-3.5 flex-shrink-0" />
      <span className="truncate italic">{status === "hidden" ? HIDDEN_CARD_LABEL : REMOVED_CARD_LABEL}</span>
    </span>
  );
}

type TChipProps = {
  workspaceSlug: string;
  resolution: TCardResolution | undefined;
  /** show the small arrow used for shortcut cards */
  shortcut?: boolean;
  className?: string;
  onNavigate?: () => void;
};

/** One linked card: icon, title and board, opening the card. Unavailable cards say only that. */
export const CardLinkChip = observer(function CardLinkChip(props: TChipProps) {
  const { workspaceSlug, resolution, shortcut = false, className, onNavigate } = props;
  const base = cn(
    "flex w-full min-w-0 items-center gap-2 rounded-md border border-subtle bg-layer-1 px-2.5 py-1.5 text-13",
    className
  );
  if (!resolution) {
    return (
      <span className={cn(base, "text-placeholder")} data-card-link-state="loading">
        <span className="size-2.5 animate-pulse rounded-full bg-layer-3" />
        <span className="h-3 w-32 animate-pulse rounded bg-layer-3" />
      </span>
    );
  }
  if (resolution.status !== "visible") {
    return (
      <span className={base}>
        {shortcut && <CornerUpRight className="size-3.5 flex-shrink-0 text-placeholder" />}
        <UnavailableCard status={resolution.status} />
      </span>
    );
  }
  const { card } = resolution;
  return (
    <Link
      href={linkedCardHref(workspaceSlug, card)}
      onClick={onNavigate}
      className={cn(base, "!no-underline hover:border-strong hover:bg-layer-1-hover [&_*]:!no-underline")}
      data-card-link-state="visible"
      title={card.name}
    >
      {shortcut && <CornerUpRight className="size-3.5 flex-shrink-0 text-placeholder" />}
      <LinkedCardIcon card={card} />
      <span className="truncate font-medium text-primary">{card.name || "Untitled"}</span>
      <span className="ml-auto flex-shrink-0 truncate text-11 text-tertiary">
        {card.project_name}
      </span>
    </Link>
  );
});
