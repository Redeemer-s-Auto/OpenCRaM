/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { matchRoutes } from "react-router";
import type { RouteObject } from "react-router";

type TManifestRoute = {
  id: string;
  parentId?: string;
  path?: string;
  index?: boolean;
  module: string;
  imports?: string[];
};

/**
 * A cold load of a deep link (a board, a task list) only knows the root route's chunks from index.html. The
 * browser then finds the other ~200 chunks of the page one import level at a time: 8-9 waves, about 3 s
 * before the first API call on the shop's connection. The build's route manifest already lists every
 * chunk each route needs, so ask for all of them at once. Only adds <link rel="modulepreload">: if anything
 * here fails, the page loads the old way.
 */
export function preloadMatchedRouteChunks(): void {
  try {
    const manifest = (window as unknown as { __reactRouterManifest?: { routes?: Record<string, TManifestRoute> } })
      .__reactRouterManifest;
    const all = manifest?.routes ? Object.values(manifest.routes) : [];
    if (all.length === 0) return;
    const children = new Map<string | undefined, TManifestRoute[]>();
    for (const route of all) {
      const list = children.get(route.parentId) ?? [];
      list.push(route);
      children.set(route.parentId, list);
    }
    const build = (parentId: string | undefined): RouteObject[] =>
      (children.get(parentId) ?? []).map((route) =>
        route.index
          ? { id: route.id, index: true }
          : { id: route.id, path: route.path, children: build(route.id) }
      );
    const matches = matchRoutes(build(undefined), window.location.pathname) ?? [];
    const hrefs = new Set<string>();
    for (const match of matches) {
      const route = match.route.id ? manifest?.routes?.[match.route.id] : undefined;
      if (!route) continue;
      hrefs.add(route.module);
      route.imports?.forEach((href) => hrefs.add(href));
    }
    const known = new Set(
      Array.from(document.querySelectorAll<HTMLLinkElement>('link[rel="modulepreload"]')).map((link) =>
        link.getAttribute("href")
      )
    );
    for (const href of hrefs) {
      if (known.has(href)) continue;
      const link = document.createElement("link");
      link.rel = "modulepreload";
      link.href = href;
      document.head.appendChild(link);
    }
  } catch {
    // A speed-up only.
  }
}
