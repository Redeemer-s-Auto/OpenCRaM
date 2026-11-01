/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Plus, Search, X } from "lucide-react";
import { useOutsideClickDetector } from "@plane/hooks";
import type { TCustomField, TCustomFieldLinkedCard, TCustomFieldValue } from "@plane/types";
import { cn } from "@plane/utils";
// services
import { CustomFieldService } from "@/services/issue";
// local
import { linkedCards } from "./helpers";

const service = new CustomFieldService();

type Props = {
  field: TCustomField;
  value: TCustomFieldValue | undefined;
  /** Gets the whole new list. The server keeps links to cards this person cannot see. */
  onChange: (cards: TCustomFieldLinkedCard[]) => void | Promise<void>;
  /** The board of the card being edited (the relation field lives there). */
  projectId: string;
  disabled?: boolean;
  variant?: "sidebar" | "cell";
};

/** A linked card: click opens it. */
function CardChip(props: { card: TCustomFieldLinkedCard; workspaceSlug: string; onRemove?: () => void }) {
  const { card, workspaceSlug, onRemove } = props;
  return (
    <span className="inline-flex max-w-full items-center gap-1 rounded-sm border border-subtle bg-layer-1 px-1.5 py-0.5">
      <Link
        href={`/${workspaceSlug}/browse/${card.project_identifier}-${card.sequence_id}/`}
        onClick={(e) => e.stopPropagation()}
        className="truncate text-primary hover:underline"
        title={card.name}
      >
        {card.name}
      </Link>
      {onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          aria-label={`Unlink ${card.name}`}
          className="shrink-0 text-tertiary hover:text-danger-primary"
        >
          <X className="size-3" />
        </button>
      )}
    </span>
  );
}

export const RelationInput = observer(function RelationInput(props: Props) {
  const { field, value, onChange, projectId, disabled = false, variant = "sidebar" } = props;
  const { workspaceSlug } = useParams();
  const slug = workspaceSlug?.toString() ?? "";
  const cards = linkedCards(value);

  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [results, setResults] = useState<TCustomFieldLinkedCard[]>([]);
  const [loading, setLoading] = useState(false);
  const [position, setPosition] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const ref = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  useOutsideClickDetector(ref, () => setOpen(false));

  // Search the target board as the person types (the server applies the same rule as saving).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    const timer = setTimeout(() => {
      service
        .linkCandidates(slug, projectId, field.id, search)
        .then((found) => !cancelled && setResults(found ?? []))
        .catch(() => !cancelled && setResults([]))
        .finally(() => !cancelled && setLoading(false));
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [open, search, slug, projectId, field.id]);

  const openPicker = () => {
    const rect = buttonRef.current?.getBoundingClientRect();
    if (rect) setPosition({ top: rect.bottom + 4, left: Math.min(rect.left, window.innerWidth - 300) });
    setSearch("");
    setOpen(true);
  };

  const chosen = new Set(cards.map((c) => c.id));
  const choices = results.filter((c) => !chosen.has(c.id));

  return (
    <div ref={ref} className={cn("flex w-full min-w-0 items-center gap-1 px-2 py-1 text-body-xs-regular", variant === "cell" ? "flex-nowrap overflow-hidden" : "flex-wrap")}>
      {cards.map((card) => (
        <CardChip
          key={card.id}
          card={card}
          workspaceSlug={slug}
          onRemove={disabled ? undefined : () => onChange(cards.filter((c) => c.id !== card.id))}
        />
      ))}
      {!cards.length && variant === "sidebar" && <span className="text-placeholder">{disabled ? "Empty" : ""}</span>}
      {!disabled && (
        <button
          ref={buttonRef}
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            if (open) setOpen(false);
            else openPicker();
          }}
          className="inline-flex shrink-0 items-center gap-1 rounded-sm px-1 py-0.5 text-tertiary hover:bg-layer-transparent-hover hover:text-primary"
          aria-label={`Link a card in ${field.name}`}
        >
          <Plus className="size-3" />
          {!cards.length && variant === "sidebar" && <span>Link a card</span>}
        </button>
      )}
      {open && (
        <div
          className="fixed z-30 w-72 rounded-md border border-subtle bg-surface-1 p-2 shadow-raised-200"
          style={{ top: position.top, left: position.left }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="flex items-center gap-1.5 rounded-sm border border-subtle px-2 py-1">
            <Search className="size-3.5 shrink-0 text-placeholder" />
            <input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
              placeholder="Search cards by name or number"
              className="w-full bg-transparent text-body-xs-regular outline-none"
            />
          </div>
          <div className="mt-1 max-h-60 overflow-y-auto">
            {loading && !choices.length && <p className="px-2 py-1.5 text-tertiary">Searching...</p>}
            {!loading && !choices.length && <p className="px-2 py-1.5 text-tertiary">No cards to link</p>}
            {choices.map((card) => (
              <button
                key={card.id}
                type="button"
                onClick={() => {
                  void onChange([...cards, card]);
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2 truncate rounded-sm px-2 py-1.5 text-left hover:bg-layer-transparent-hover"
              >
                <span className="truncate text-primary">{card.name}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});
