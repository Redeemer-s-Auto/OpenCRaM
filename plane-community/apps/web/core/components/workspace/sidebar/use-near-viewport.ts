/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

// The sidebar can hold a couple of hundred boards, and only a screenful of them is ever on screen. Each full
// row carries menus, tooltips, drag-and-drop and several store look-ups, and re-renders whenever those change
// during a page load. A row far from the screen shows a plain copy of itself instead, and turns into the full
// row once it comes within a few hundred pixels of the screen (scrolling, opening the drawer). It never turns
// back, so nothing a person has opened is lost.

import { useEffect, useState } from "react";

const MARGIN = "400px 0px";

type TWatcher = (isNear: boolean) => void;
let observer: IntersectionObserver | undefined;
const watchers = new Map<Element, TWatcher>();

const getObserver = (): IntersectionObserver | undefined => {
  if (typeof IntersectionObserver === "undefined") return undefined;
  if (!observer) {
    observer = new IntersectionObserver(
      (entries) => entries.forEach((entry) => watchers.get(entry.target)?.(entry.isIntersecting)),
      { rootMargin: MARGIN }
    );
  }
  return observer;
};

/**
 * True once the element has come near the screen (and from then on). Without IntersectionObserver it is true
 * at once, so the full row is drawn as before.
 */
export const useNearViewport = (element: Element | null): boolean => {
  const [isNear, setIsNear] = useState(() => typeof IntersectionObserver === "undefined");

  useEffect(() => {
    if (isNear || !element) return;
    const io = getObserver();
    if (!io) {
      setIsNear(true);
      return;
    }
    watchers.set(element, (near) => {
      if (near) setIsNear(true);
    });
    io.observe(element);
    return () => {
      watchers.delete(element);
      io.unobserve(element);
    };
  }, [element, isNear]);

  return isNear;
};
