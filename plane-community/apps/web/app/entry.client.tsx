/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { startTransition, StrictMode } from "react";
import { hydrateRoot } from "react-dom/client";
import { HydratedRouter } from "react-router/dom";

import polyfills from "@/lib/polyfills";
import { preloadMatchedRouteChunks } from "@/lib/preload-route-chunks";
import { isStaleAssetErrorMessage, recoverFromStaleAsset } from "@/lib/stale-asset-error";

void polyfills;

// Production-only: in dev these errors come from the dev server itself (restarts,
// stale optimized deps) and auto-reloading would mask them.
if (import.meta.env.PROD) {
  window.addEventListener("vite:preloadError", (event) => {
    if (recoverFromStaleAsset()) event.preventDefault();
  });

  window.addEventListener("error", (event) => {
    if (isStaleAssetErrorMessage(event.message || "")) recoverFromStaleAsset();
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason instanceof Error ? event.reason.message : String(event.reason ?? "");
    if (isStaleAssetErrorMessage(reason)) recoverFromStaleAsset();
  });
}

// Fetch every chunk of the page being opened in one go instead of one import level at a time.
preloadMatchedRouteChunks();

startTransition(() => {
  hydrateRoot(
    document,
    <StrictMode>
      <HydratedRouter />
    </StrictMode>
  );
});
