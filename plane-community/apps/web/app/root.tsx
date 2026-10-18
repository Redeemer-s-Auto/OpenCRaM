/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, type ReactNode } from "react";
import Script from "next/script";
import { Links, Meta, Outlet, Scripts } from "react-router";
import type { LinksFunction } from "react-router";
import { ThemeProvider, useTheme } from "next-themes";
// plane imports
import { SITE_DESCRIPTION, SITE_NAME } from "@plane/constants";
import { cn } from "@plane/utils";
// assets
import favicon16 from "@/app/assets/favicon/favicon-16x16.png?url";
import favicon32 from "@/app/assets/favicon/favicon-32x32.png?url";
import faviconIco from "@/app/assets/favicon/favicon.ico?url";
import gardenMark from "@/app/assets/garden-mark.svg?url";
import icon180 from "@/app/assets/icons/icon-180x180.png?url";
import icon512 from "@/app/assets/icons/icon-512x512.png?url";
import ogImage from "@/app/assets/og-image.png?url";
import globalStyles from "@/styles/globals.css?url";
import type { Route } from "./+types/root";
// components
import { LogoSpinner } from "@/components/common/logo-spinner";
// lib
import { isStaleAssetError, recoverFromStaleAsset } from "@/lib/stale-asset-error";
// local
import { CustomErrorComponent } from "./error";
import { AppProvider } from "./provider";
// fonts
import "@fontsource/material-symbols-rounded";

const gardenMode = process.env.VITE_GARDEN_AUTH_ENABLED === "1";
const gardenWorkUrl = process.env.VITE_GARDEN_WORK_URL || "";
const gardenAdminUrl = process.env.VITE_GARDEN_ADMIN_URL || "https://gardenchurch.web.app/admin";
const APP_TITLE = gardenMode ? "The Garden Work" : "Plane | Simple, extensible, open-source project management tool.";
const APP_DESCRIPTION = gardenMode
  ? "Projects, tasks, planning, and operational work for The Garden staff."
  : SITE_DESCRIPTION;

function GardenEmbeddedNavigationBridge() {
  useEffect(() => {
    if (!gardenMode || window.parent === window) return undefined;

    let parentOrigin: string;
    try {
      parentOrigin = new URL(gardenAdminUrl).origin;
    } catch {
      parentOrigin = "https://gardenchurch.web.app";
    }

    const onDocumentClick = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const target = event.target;
      if (!(target instanceof Element)) return;
      const anchor = target.closest<HTMLAnchorElement>("a[href]");
      if (!anchor || anchor.hasAttribute("download")) return;

      const rawHref = anchor.getAttribute("href")?.trim();
      if (!rawHref || rawHref.startsWith("#") || rawHref.toLowerCase().startsWith("javascript:")) return;

      let destination: URL;
      try {
        destination = new URL(anchor.href, window.location.href);
      } catch {
        return;
      }

      // Work-owned navigation remains inside Work. Everything else belongs to
      // the outer Garden shell or to a separate browser context.
      if (destination.origin === window.location.origin) return;
      if (!["http:", "https:", "mailto:", "tel:"].includes(destination.protocol)) return;

      event.preventDefault();
      window.parent.postMessage(
        {
          type: "garden:external-navigation",
          href: destination.toString(),
          target: destination.origin === parentOrigin ? "garden" : "external",
        },
        parentOrigin,
      );
    };

    document.addEventListener("click", onDocumentClick, true);
    return () => document.removeEventListener("click", onDocumentClick, true);
  }, []);

  return null;
}

export const links: LinksFunction = () => {
  const iconLinks = gardenMode
    ? [
        { rel: "icon", type: "image/svg+xml", href: gardenMark },
        { rel: "shortcut icon", href: gardenMark },
        { rel: "manifest", href: "/garden.webmanifest.json" },
      ]
    : [
        { rel: "icon", type: "image/png", sizes: "32x32", href: favicon32 },
        { rel: "icon", type: "image/png", sizes: "16x16", href: favicon16 },
        { rel: "shortcut icon", href: faviconIco },
        { rel: "manifest", href: "/site.webmanifest.json" },
        { rel: "apple-touch-icon", href: icon512 },
        { rel: "apple-touch-icon", sizes: "180x180", href: icon180 },
        { rel: "apple-touch-icon", sizes: "512x512", href: icon512 },
        { rel: "manifest", href: "/manifest.json" },
      ];

  return [
    ...iconLinks,
    { rel: "stylesheet", href: globalStyles },
  ];
};

export function Layout({ children }: { children: ReactNode }) {
  const isSessionRecorderEnabled = parseInt(process.env.VITE_ENABLE_SESSION_RECORDER || "0");

  return (
    <html lang="en" suppressHydrationWarning data-garden-work={gardenMode ? "true" : undefined}>
      <head>
        <meta charSet="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content={gardenMode ? "#40562E" : "#fff"} />
        <meta name="application-name" content={gardenMode ? "The Garden Work" : "Plane"} />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <meta name="apple-mobile-web-app-title" content={gardenMode ? "The Garden Work" : SITE_NAME} />
        <meta name="format-detection" content="telephone=no" />
        <meta name="mobile-web-app-capable" content="yes" />
        <Meta />
        <Links />
      </head>
      <body suppressHydrationWarning>
        <div id="context-menu-portal" />
        <div id="editor-portal" />
        <ThemeProvider
          themes={gardenMode ? ["light"] : ["light", "dark", "light-contrast", "dark-contrast", "custom"]}
          defaultTheme={gardenMode ? "light" : "system"}
          forcedTheme={gardenMode ? "light" : undefined}
        >
          {children}
        </ThemeProvider>
        <Scripts />
        {!!isSessionRecorderEnabled && process.env.VITE_SESSION_RECORDER_KEY && (
          <Script id="clarity-tracking">
            {`(function(c,l,a,r,i,t,y){
              c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};
              t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;
              y=l.getElementsByTagName(r)[0];if(y){y.parentNode.insertBefore(t,y);}
          })(window, document, "clarity", "script", "${process.env.VITE_SESSION_RECORDER_KEY}");`}
          </Script>
        )}
      </body>
    </html>
  );
}

export const meta: Route.MetaFunction = () => {
  const metadata = [
    { title: APP_TITLE },
    { name: "description", content: APP_DESCRIPTION },
    { property: "og:title", content: APP_TITLE },
    { property: "og:description", content: APP_DESCRIPTION },
  ];

  if (gardenMode) {
    if (gardenWorkUrl) metadata.push({ property: "og:url", content: gardenWorkUrl });
    metadata.push(
      { property: "og:image", content: gardenMark },
      { property: "og:image:alt", content: "The Garden Work" },
      { name: "keywords", content: "The Garden, staff operations, projects, tasks, planning, work management" },
    );
    return metadata;
  }

  return [
    ...metadata,
    { property: "og:url", content: "https://app.plane.so/" },
    { property: "og:image", content: ogImage },
    { property: "og:image:width", content: "1200" },
    { property: "og:image:height", content: "630" },
    { property: "og:image:alt", content: "Plane - Modern project management" },
    {
      name: "keywords",
      content:
        "software development, plan, ship, software, accelerate, code management, release management, project management, work item tracking, agile, scrum, kanban, collaboration",
    },
    { name: "twitter:site", content: "@planepowers" },
    { name: "twitter:card", content: "summary_large_image" },
    { name: "twitter:image", content: ogImage },
    { name: "twitter:image:width", content: "1200" },
    { name: "twitter:image:height", content: "630" },
    { name: "twitter:image:alt", content: "Plane - Modern project management" },
  ];
};

export default function Root() {
  return (
    <AppProvider>
      <GardenEmbeddedNavigationBridge />
      <div className={cn("relative flex h-screen w-full flex-col overflow-hidden bg-canvas", "desktop-app-container")}>
        <main className="relative h-full w-full overflow-hidden">
          <Outlet />
        </main>
      </div>
    </AppProvider>
  );
}

export function HydrateFallback() {
  const { resolvedTheme } = useTheme();

  // React Router's SPA mode pre-renders HydrateFallback into index.html and then
  // hydrates that exact markup in the browser. Garden previously rendered an
  // empty div during pre-rendering but a spinner on the first browser render,
  // which guarantees React hydration errors #418/#423 on every page load.
  // Garden has a forced light theme and a theme-independent mark, so render the
  // same fallback on both sides and let hydration start from identical HTML.
  if (gardenMode) {
    return (
      <div className="relative flex h-screen w-full items-center justify-center bg-canvas">
        <LogoSpinner />
      </div>
    );
  }

  if (typeof window === "undefined" || resolvedTheme === undefined) return <div />;

  return (
    <div className="relative flex h-screen w-full items-center justify-center bg-canvas">
      <LogoSpinner />
    </div>
  );
}

export function ErrorBoundary({ error }: Route.ErrorBoundaryProps) {
  if (import.meta.env.PROD && isStaleAssetError(error)) recoverFromStaleAsset();

  return <CustomErrorComponent error={error} />;
}

