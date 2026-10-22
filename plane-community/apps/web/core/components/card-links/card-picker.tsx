/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef, useState } from "react";
import { Search } from "lucide-react";
import { cn } from "@plane/utils";
import type { TLinkedCard } from "@/services/card-links.service";
import { cardLinksService } from "@/services/card-links.service";
import { LinkedCardIcon } from "./card-link-chip";

type Props = {
  workspaceSlug: string;
  onPick: (card: TLinkedCard) => void;
  onCancel?: () => void;
  /** cards not to offer (for example the card being edited) */
  excludeIds?: string[];
  autoFocus?: boolean;
  placeholder?: string;
  className?: string;
};

/** Search box over every card the person may see in the workspace (title, or an id like ABC-12). */
export function CardPicker(props: Props) {
  const { workspaceSlug, onPick, onCancel, excludeIds = [], autoFocus = true, placeholder, className } = props;
  const [text, setText] = useState("");
  const [rows, setRows] = useState<TLinkedCard[] | undefined>(undefined);
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const excluded = excludeIds.join(",");

  useEffect(() => {
    let alive = true;
    const handle = setTimeout(() => {
      cardLinksService
        .search(workspaceSlug, text, 20)
        .then((found) => {
          if (!alive) return;
          const skip = new Set(excluded ? excluded.split(",") : []);
          setRows(found.filter((row) => !skip.has(row.id)));
          setActive(0);
        })
        .catch(() => alive && setRows([]));
    }, 200);
    return () => {
      alive = false;
      clearTimeout(handle);
    };
  }, [workspaceSlug, text, excluded]);

  useEffect(() => {
    if (!autoFocus) return;
    // The editor takes focus back right after inserting the block; take it once that has happened.
    const handle = setTimeout(() => inputRef.current?.focus(), 60);
    return () => clearTimeout(handle);
  }, [autoFocus]);

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    // Keep the editor from acting on these keys.
    event.stopPropagation();
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((value) => Math.min(value + 1, Math.max((rows?.length ?? 1) - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((value) => Math.max(value - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      const row = rows?.[active];
      if (row) onPick(row);
    } else if (event.key === "Escape") {
      event.preventDefault();
      onCancel?.();
    }
  };

  return (
    <div className={cn("flex flex-col gap-1 rounded-md border border-subtle bg-layer-1 p-1.5", className)}>
      <div className="flex items-center gap-1.5 px-1">
        <Search className="size-3.5 flex-shrink-0 text-placeholder" />
        <input
          ref={inputRef}
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder ?? "Link to a card: type a title or an id like ABC-12"}
          className="w-full bg-transparent py-1 text-13 text-primary outline-none placeholder:text-placeholder"
          aria-label="Search cards"
        />
      </div>
      <div className="max-h-60 overflow-y-auto" role="listbox">
        {rows === undefined && <p className="px-2 py-1 text-12 text-tertiary">Searching…</p>}
        {rows?.length === 0 && <p className="px-2 py-1 text-12 text-tertiary">No cards found</p>}
        {rows?.map((row, index) => (
          <button
            key={row.id}
            type="button"
            role="option"
            aria-selected={index === active}
            onMouseEnter={() => setActive(index)}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => onPick(row)}
            className={cn("flex w-full min-w-0 items-center gap-2 rounded-sm px-2 py-1 text-left text-13", {
              "bg-layer-1-hover": index === active,
            })}
          >
            <LinkedCardIcon card={row} />
            <span className="truncate text-primary">{row.name || "Untitled"}</span>
            <span className="ml-auto flex-shrink-0 text-11 text-tertiary">
              {row.project_name} · {row.project_identifier}-{row.sequence_id}
            </span>
          </button>
        ))}
      </div>
      {onCancel && (
        <button
          type="button"
          onClick={onCancel}
          className="self-end px-2 py-0.5 text-11 text-tertiary hover:text-secondary"
        >
          Cancel
        </button>
      )}
    </div>
  );
}
