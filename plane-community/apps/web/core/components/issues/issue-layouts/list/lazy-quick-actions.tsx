/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

// A row's "..." menu is a heavy tree (a dozen items, a popper, icons). A board with 2,000 rows built it
// 2,000 times on load, though only one is ever used. Here the real menu is built the first time the pointer,
// a finger or the keyboard reaches that row's menu spot; until then a same-size empty box holds the place.

import type { ReactNode } from "react";
import { useState } from "react";

type Props = { render: () => ReactNode };

export function LazyQuickActions(props: Props) {
  const [armed, setArmed] = useState(false);
  if (armed) return <>{props.render()}</>;
  const arm = () => setArmed(true);
  return (
    <div
      className="size-6 flex-shrink-0"
      onPointerEnter={arm}
      onPointerDown={arm}
      onFocus={arm}
      onTouchStart={arm}
      tabIndex={0}
      role="button"
      aria-label="Open row menu"
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") arm();
      }}
    />
  );
}
