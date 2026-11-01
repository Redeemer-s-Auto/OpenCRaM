/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type React from "react";
import { useEffect, useRef } from "react";

export const useOutsideClickDetector = (
  ref: React.RefObject<HTMLElement> | any,
  callback: () => void,
  useCapture = false
) => {
  // The latest ref and callback, read at click time. The listener itself is added once per mount
  // (it used to be removed and added again on every render: ~0.1 s per cold load with the
  // 181-board sidebar, where every row uses this hook).
  const latest = useRef({ ref, callback });
  latest.current = { ref, callback };

  useEffect(() => {
    const handleClick = (event: MouseEvent) => {
      const { ref: currentRef, callback: currentCallback } = latest.current;
      if (currentRef.current && !currentRef.current.contains(event.target as any)) {
        // check for the closest element with attribute name data-prevent-outside-click
        const preventOutsideClickElement = (event.target as unknown as HTMLElement | undefined)?.closest(
          "[data-prevent-outside-click]"
        );
        // if the closest element with attribute name data-prevent-outside-click is found, return
        if (preventOutsideClickElement) {
          return;
        }
        // else call the callback
        currentCallback();
      }
    };
    document.addEventListener("mousedown", handleClick, useCapture);
    return () => {
      document.removeEventListener("mousedown", handleClick, useCapture);
    };
  }, [useCapture]);
};
