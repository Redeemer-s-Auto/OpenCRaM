/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTheme } from "next-themes";
// assets
import gardenMark from "@/app/assets/garden-mark.svg?url";
import LogoSpinnerDark from "@/app/assets/images/logo-spinner-dark.gif?url";
import LogoSpinnerLight from "@/app/assets/images/logo-spinner-light.gif?url";

import { gardenAppName, gardenMode } from "@/lib/garden-config";

export function LogoSpinner() {
  const { resolvedTheme } = useTheme();

  if (gardenMode) {
    return (
      <div className="flex items-center justify-center" aria-label={`${gardenAppName} is loading`}>
        <img src={gardenMark} alt={gardenAppName} className="h-8 w-8 animate-pulse object-contain sm:h-11 sm:w-11" />
      </div>
    );
  }

  const logoSrc = resolvedTheme === "dark" ? LogoSpinnerDark : LogoSpinnerLight;

  return (
    <div className="flex items-center justify-center">
      <img src={logoSrc} alt="logo" className="h-6 w-auto object-contain sm:h-11" />
    </div>
  );
}
