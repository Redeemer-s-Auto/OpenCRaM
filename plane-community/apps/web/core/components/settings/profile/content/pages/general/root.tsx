/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { CircleUserRound, ExternalLink, RefreshCw } from "lucide-react";
import { useTranslation } from "@plane/i18n";
import { getFileURL } from "@plane/utils";
// components
import { PageHead } from "@/components/core/page-title";
// hooks
import { useUser } from "@/hooks/store/user";
// local imports
import { GeneralProfileSettingsForm } from "./form";

const gardenMode = process.env.VITE_GARDEN_AUTH_ENABLED === "1";
const gardenAdminUrl = process.env.VITE_GARDEN_ADMIN_URL || "https://gardenchurch.web.app/admin";

function gardenProfileUrl() {
  try {
    return new URL("/profile", gardenAdminUrl).toString();
  } catch {
    return "https://gardenchurch.web.app/profile";
  }
}

function gardenDisplayEmail(email: string | null | undefined) {
  const normalized = email?.trim();
  if (!normalized || normalized.toLowerCase().endsWith("@garden.invalid")) return null;
  return normalized;
}

export const GeneralProfileSettings = observer(function GeneralProfileSettings() {
  const { t } = useTranslation();
  // store hooks
  const { data: currentUser, userProfile } = useUser();

  if (!currentUser) return null;

  if (gardenMode) {
    const name = currentUser.display_name || [currentUser.first_name, currentUser.last_name].filter(Boolean).join(" ") || "Garden User";
    const avatar = currentUser.avatar_url;
    const email = gardenDisplayEmail(currentUser.email);
    return (
      <>
        <PageHead title="Garden profile" />
        <div className="flex w-full flex-col gap-5">
          <div className="rounded-xl border border-subtle bg-surface-1 p-5 shadow-raised-100">
            <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex min-w-0 items-center gap-4">
                <div className="flex size-16 shrink-0 items-center justify-center overflow-hidden rounded-xl bg-layer-1">
                  {avatar ? (
                    <img src={getFileURL(avatar)} alt={name} className="size-full object-cover" />
                  ) : (
                    <CircleUserRound className="size-10 text-secondary" />
                  )}
                </div>
                <div className="min-w-0">
                  <div className="truncate text-18 font-semibold text-primary">{name}</div>
                  {email ? <div className="truncate text-13 text-secondary">{email}</div> : null}
                  <div className="mt-1 flex items-center gap-1.5 text-11 font-medium text-accent-primary">
                    <RefreshCw className="size-3" />
                    Synced from The Garden
                  </div>
                </div>
              </div>
              <a
                href={gardenProfileUrl()}
                target="_top"
                className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-md bg-accent-primary px-4 py-2 text-13 font-medium text-on-color transition-colors hover:bg-accent-secondary"
              >
                Edit Garden profile
                <ExternalLink className="size-3.5" />
              </a>
            </div>
          </div>
          <div className="rounded-xl border border-subtle bg-layer-1 p-4 text-13 leading-5 text-secondary">
            Your name, display name, profile photo, email, and Work account status are managed by The Garden. Changes made in your Garden profile sync into Work automatically, so your identity stays consistent across staff systems.
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <PageHead title={`${t("profile.label")} - ${t("general_settings")}`} />
      <GeneralProfileSettingsForm user={currentUser} profile={userProfile.data} />
    </>
  );
});
