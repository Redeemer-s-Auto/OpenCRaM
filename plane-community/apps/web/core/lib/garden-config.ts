/**
 * Copyright (c) 2026 The Garden contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 *
 * One place for the Garden-mode settings the web app reads at build time.
 * Every value has a default that keeps the original Garden deployment unchanged;
 * another organisation sets its own through the VITE_GARDEN_* build args.
 */

const env = process.env;

const DEFAULT_ADMIN_URL = "https://gardenchurch.web.app/admin";

export const gardenMode = env.VITE_GARDEN_AUTH_ENABLED === "1";

/** True when an admin (launcher) site is configured. Without it Work never redirects away. */
export const gardenAdminConfigured = Boolean((env.VITE_GARDEN_ADMIN_URL || "").trim());

/** The admin/launcher site that signs people in (Garden Admin, or a sign-in hub). */
export const gardenAdminUrl = (env.VITE_GARDEN_ADMIN_URL || DEFAULT_ADMIN_URL).trim().replace(/\/$/, "");

function originOf(url: string, fallback: string): string {
  try {
    return new URL(url).origin;
  } catch {
    return fallback;
  }
}

/** Origin of the admin site: the only parent Work talks to with postMessage. */
export const gardenAdminOrigin = originOf(gardenAdminUrl, "https://gardenchurch.web.app");

/** The page that signs a person in and hands them to Work. Default: <admin URL>/work. */
export const gardenLaunchUrl = (env.VITE_GARDEN_LAUNCH_URL || "").trim() || `${gardenAdminUrl}/work`;

/** Where a person edits their name, photo and email. Default: /profile on the admin site. */
export const gardenProfileUrl =
  (env.VITE_GARDEN_PROFILE_URL || "").trim() || `${gardenAdminOrigin}/profile`;

/** The organisation name shown in Work, e.g. "The Garden". */
export const gardenOrgName = (env.VITE_GARDEN_ORG_NAME || "").trim() || "The Garden";

/** The product name shown in titles and loading screens, e.g. "The Garden Work". */
export const gardenAppName = (env.VITE_GARDEN_APP_NAME || "").trim() || `${gardenOrgName} Work`;

/** What people call the admin/launcher site, e.g. "Garden Admin" or "the hub". */
export const gardenAdminName = (env.VITE_GARDEN_ADMIN_NAME || "").trim() || "Garden Admin";

/** What people call their profile on the admin site, e.g. "My Garden". */
export const gardenProfileName = (env.VITE_GARDEN_PROFILE_NAME || "").trim() || "My Garden";

/** Where admins manage who has access. Default: <admin URL>/access. */
export const gardenAccessUrl = (env.VITE_GARDEN_ACCESS_URL || "").trim() || `${gardenAdminUrl}/access`;

/**
 * Board (project) membership is managed inside Work by Work admins instead of
 * being projected from Firebase: true when GARDEN_ACCESS_MODE=roles (passed to the build as VITE_GARDEN_ACCESS_MODE).
 */
export const gardenLocalProjectMembers = (env.VITE_GARDEN_ACCESS_MODE || "").trim().toLowerCase() === "roles";
