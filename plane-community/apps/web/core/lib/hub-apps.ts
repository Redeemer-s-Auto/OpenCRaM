/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 *
 * The apps of the hub, for the app rail and the phone drawer (hub theme only; a Garden build
 * never shows them). Same list and order as the hub's own side menu (hub-design src/AppShell.tsx):
 * Home, CRM, HR, Diagnostics, Notes.
 *
 * VITE_HUB_URL  The hub's address. The other apps live on paths of that address
 *               (shop-hub apps/web/.env.production: CRM at /crm/, HR at /hr/, Diagnostics at /diag).
 *               Default: https://hub.redeemersauto.com
 *
 * Which apps a person may open is known only to the hub, which keeps the answer in its own
 * browser store on its own origin, so this app cannot read it: every app is listed, and the hub
 * itself turns away a person who may not open one.
 */

import type { LucideIcon } from "lucide-react";
import { Briefcase, Home, NotebookPen, Users, Wrench } from "lucide-react";

export type THubAppId = "home" | "crm" | "hr" | "diag" | "notes";

export type THubApp = {
  id: THubAppId;
  label: string;
  /** Absolute URL of the app; the current app's entry is relative (handled in the app). */
  href: string;
  icon: LucideIcon;
  /** True for this app (Notes): drawn highlighted and linked inside the app. */
  isCurrent?: boolean;
};

const clean = (value: string | undefined) => (value || "").trim().replace(/\/$/, "");

/** Only http(s) is accepted, so a typo cannot inject a javascript: URL. */
function cleanOrigin(value: string | undefined, fallback: string): string {
  const url = clean(value);
  return /^https?:\/\//i.test(url) ? url : fallback;
}

export const hubUrl = cleanOrigin(process.env.VITE_HUB_URL, "https://hub.redeemersauto.com");

/** The hub's home page: where the Home button goes (no sign-out). */
export const hubHomeUrl = `${hubUrl}/`;

export const HUB_APPS: ReadonlyArray<THubApp> = [
  { id: "home", label: "Home", href: hubHomeUrl, icon: Home },
  { id: "crm", label: "CRM", href: `${hubUrl}/crm/`, icon: Users },
  { id: "hr", label: "HR", href: `${hubUrl}/hr/`, icon: Briefcase },
  { id: "diag", label: "Diagnostics", href: `${hubUrl}/diag`, icon: Wrench },
  { id: "notes", label: "Notes", href: "/", icon: NotebookPen, isCurrent: true },
];
