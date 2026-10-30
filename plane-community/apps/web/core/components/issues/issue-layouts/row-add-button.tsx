/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { MouseEvent, SyntheticEvent } from "react";
import { useRef } from "react";
import { PlusIcon } from "@plane/propel/icons";
import { Tooltip } from "@plane/propel/tooltip";
import { cn } from "@plane/utils";
// hooks
import { usePlatformOS } from "@/hooks/use-platform-os";

export type TRowAddPlacement = "above" | "below";

export const ROW_ADD_TOOLTIP = "Click to add below. Alt+click to add above";
const LONG_PRESS_MS = 500;

type Props = {
  onAdd: (placement: TRowAddPlacement) => void;
  className?: string;
};

/**
 * The + at the left of a row. Click adds a line below the row, Alt+click adds one above.
 * On a phone a tap adds below and a long press (500 ms) adds above. Shown on hover with a mouse
 * and always on a touch screen. Lives inside a row link, so every event stops here.
 */
export function RowAddButton(props: Props) {
  const { onAdd, className } = props;
  const { isMobile } = usePlatformOS();
  const pressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressFired = useRef(false);

  const stop = (e: SyntheticEvent) => {
    e.stopPropagation();
    e.preventDefault();
  };

  const clearPress = () => {
    if (pressTimer.current) clearTimeout(pressTimer.current);
    pressTimer.current = null;
  };

  const handleClick = (e: MouseEvent<HTMLButtonElement>) => {
    stop(e);
    if (longPressFired.current) {
      longPressFired.current = false;
      return;
    }
    onAdd(e.altKey ? "above" : "below");
  };

  return (
    <Tooltip
      tooltipContent={ROW_ADD_TOOLTIP}
      isMobile={isMobile}
      position="top-start"
      renderByDefault={false}
    >
      <button
        type="button"
        aria-label={ROW_ADD_TOOLTIP}
        className={cn(
          "grid size-6 flex-shrink-0 place-items-center rounded-sm text-placeholder opacity-0 transition-opacity select-none",
          "hover:bg-layer-transparent-hover hover:text-tertiary focus-visible:opacity-100",
          "group-hover/list-block:opacity-100 [@media(hover:none)]:opacity-100",
          className
        )}
        onClick={handleClick}
        onMouseDown={stop}
        onContextMenu={stop}
        onTouchStart={(e) => {
          e.stopPropagation();
          longPressFired.current = false;
          clearPress();
          pressTimer.current = setTimeout(() => {
            longPressFired.current = true;
            onAdd("above");
          }, LONG_PRESS_MS);
        }}
        onTouchMove={clearPress}
        onTouchCancel={clearPress}
        onTouchEnd={(e) => {
          e.stopPropagation();
          clearPress();
        }}
      >
        <PlusIcon className="size-3.5 stroke-2" />
      </button>
    </Tooltip>
  );
}
