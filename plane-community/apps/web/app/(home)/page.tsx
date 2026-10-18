/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
// components
import { AuthBase } from "@/components/auth-screens/auth-base";
// helpers
import { EAuthModes, EPageTypes } from "@/helpers/authentication.helper";
// layouts
import DefaultLayout from "@/layouts/default-layout";
// wrappers
import { AuthenticationWrapper } from "@/lib/wrappers/authentication-wrapper";

const gardenAuthEnabled = process.env.VITE_GARDEN_AUTH_ENABLED === "1";
const gardenAdminUrl = (process.env.VITE_GARDEN_ADMIN_URL || "").replace(/\/$/, "");

function gardenAdminOrigin() {
  try {
    return new URL(gardenAdminUrl).origin;
  } catch {
    return "https://gardenchurch.web.app";
  }
}

function HomePage() {
  React.useEffect(() => {
    if (!gardenAuthEnabled || !gardenAdminUrl) return;

    // Garden Work normally runs inside /admin/work. If the embedded Work app
    // ever falls back to its root route, navigating the iframe itself to
    // /admin/work recursively embeds Admin -> Work -> Admin -> Work forever.
    // Ask the existing outer Admin shell to re-establish the Work session
    // instead. Only top-level visits to the Work hostname redirect to Admin.
    if (window.parent !== window) {
      window.parent.postMessage({ type: "garden:work-relaunch" }, gardenAdminOrigin());
      return;
    }

    window.location.replace(`${gardenAdminUrl}/work`);
  }, []);

  if (gardenAuthEnabled) {
    return (
      <DefaultLayout>
        <div className="flex min-h-screen items-center justify-center px-6 text-center">
          <div>
            <p className="text-lg font-medium text-primary">Opening The Garden Work</p>
            <p className="mt-2 text-sm text-secondary">Returning to your Garden staff session…</p>
          </div>
        </div>
      </DefaultLayout>
    );
  }

  return (
    <DefaultLayout>
      <AuthenticationWrapper pageType={EPageTypes.NON_AUTHENTICATED}>
        <AuthBase authType={EAuthModes.SIGN_IN} />
      </AuthenticationWrapper>
    </DefaultLayout>
  );
}

export default HomePage;
