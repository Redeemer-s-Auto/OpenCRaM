/**
 * Copyright (c) 2026 The Garden contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 *
 * The look of the web app, chosen at build time.
 *
 * VITE_BRAND_THEME   "garden" (default) keeps The Garden look unchanged.
 *                    "hub" uses a neutral hub look: red accent, light and dark mode
 *                    (tokens in packages/tailwind-config/hub.css).
 * VITE_BRAND_NAME    Name shown next to the logo in the top bar (hub theme), e.g. "Shop Notes".
 * VITE_BRAND_LOGO_URL Logo image URL (hub theme). Served by the deployment, never committed.
 * VITE_BRAND_ICON_URL Browser-tab icon URL (hub theme). Falls back to the logo URL.
 *
 * Only the hub theme reads the name/logo/icon values, so a Garden build is unchanged
 * whatever they are set to.
 */

export type BrandTheme = "garden" | "hub";

export type BrandConfig = {
  theme: BrandTheme;
  isHub: boolean;
  /** Short brand name for the top bar; empty when not set. */
  name: string;
  /** Logo URL; empty when not set. */
  logoUrl: string;
  /** Favicon URL; empty when neither icon nor logo is set. */
  iconUrl: string;
  /** Name used in product sentences ("Most things start with a project in X."). */
  productName: string;
};

type Env = Record<string, string | undefined>;

const clean = (value: string | undefined) => (value || "").trim();

/** Only http(s) or same-site absolute paths are accepted, so a typo cannot inject a javascript: URL. */
function cleanUrl(value: string | undefined): string {
  const url = clean(value);
  if (!url) return "";
  if (url.startsWith("/") && !url.startsWith("//")) return url;
  return /^https?:\/\//i.test(url) ? url : "";
}

export function resolveBrand(env: Env, appName = ""): BrandConfig {
  const theme: BrandTheme = clean(env.VITE_BRAND_THEME).toLowerCase() === "hub" ? "hub" : "garden";
  if (theme === "garden") {
    // The Garden strings were written as "Garden Work"; keep them exactly.
    return { theme, isHub: false, name: "", logoUrl: "", iconUrl: "", productName: "Garden Work" };
  }
  const name = clean(env.VITE_BRAND_NAME);
  const logoUrl = cleanUrl(env.VITE_BRAND_LOGO_URL);
  const iconUrl = cleanUrl(env.VITE_BRAND_ICON_URL) || logoUrl;
  return { theme, isHub: true, name, logoUrl, iconUrl, productName: name || clean(appName) || "Notes" };
}

const env = process.env;
const gardenAppName = clean(env.VITE_GARDEN_APP_NAME) || `${clean(env.VITE_GARDEN_ORG_NAME) || "The Garden"} Work`;

export const brand = resolveBrand(env, gardenAppName);
export const brandTheme = brand.theme;
export const isHubTheme = brand.isHub;
