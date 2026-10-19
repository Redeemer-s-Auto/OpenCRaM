/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { FileText, PanelRight } from "lucide-react";
import { Tooltip } from "@plane/propel/tooltip";
import { cn } from "@plane/utils";
import { useCardOpenMode } from "./card-open-mode";

/** "Open cards as: Page | Side peek". The choice is kept in this browser. */
export function CardOpenModeToggle({ className }: { className?: string }) {
  const [mode, setMode] = useCardOpenMode();
  const options = [
    { key: "page" as const, label: "Page", hint: "Open cards as a full page", Icon: FileText },
    { key: "peek" as const, label: "Side peek", hint: "Open cards in a side panel", Icon: PanelRight },
  ];
  return (
    <div
      className={cn("flex items-center gap-0.5 rounded-md border border-subtle p-0.5 text-11", className)}
      role="radiogroup"
      aria-label="Open cards as"
    >
      {options.map(({ key, label, hint, Icon }) => (
        <Tooltip key={key} tooltipContent={hint}>
          <button
            type="button"
            role="radio"
            aria-checked={mode === key}
            onClick={() => setMode(key)}
            className={cn("flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-secondary", {
              "bg-layer-1 text-primary": mode === key,
            })}
          >
            <Icon className="size-3" />
            <span>{label}</span>
          </button>
        </Tooltip>
      ))}
    </div>
  );
}
