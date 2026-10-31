/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { GripVertical } from "lucide-react";
import { cn } from "@plane/utils";

export const ROW_GRIP_LABEL = "Drag to move this row";

/**
 * The six-dot grip at the start of a row. It is a sign, not a second drag source: the whole row is
 * already the drag source, so dragging from the grip drags the row. Shown on hover with a mouse and
 * always on a touch screen. Lives inside a row link, so a click stops here.
 */
export function RowDragGrip(props: { className?: string }) {
  return (
    <span
      role="img"
      aria-label={ROW_GRIP_LABEL}
      title={ROW_GRIP_LABEL}
      data-row-grip
      className={cn(
        "grid size-5 flex-shrink-0 cursor-grab place-items-center rounded-sm text-placeholder opacity-0 transition-opacity select-none active:cursor-grabbing",
        "hover:bg-layer-transparent-hover hover:text-tertiary",
        "group-hover/list-block:opacity-100 [@media(hover:none)]:opacity-100",
        props.className
      )}
      onClick={(e) => {
        e.stopPropagation();
        e.preventDefault();
      }}
    >
      <GripVertical className="size-3.5" />
    </span>
  );
}
