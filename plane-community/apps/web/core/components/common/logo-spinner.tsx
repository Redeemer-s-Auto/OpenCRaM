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

import { brand } from "@/lib/brand-config";
import { gardenAppName, gardenMode } from "@/lib/garden-config";

export function LogoSpinner() {
  const { resolvedTheme } = useTheme();

  // Hub theme: the deployment's logo, or a plain pulsing dot when none is set.
  if (brand.isHub) {
    return (
      <div className="flex items-center justify-center" aria-label={`${brand.productName} is loading`}>
        {brand.logoUrl ? (
          <img
            src={brand.logoUrl}
            alt={brand.name || brand.productName}
            className="brand-logo-dark-safe h-10 w-auto animate-pulse object-contain sm:h-14"
          />
        ) : (
          <span className="size-3 animate-pulse rounded-full bg-accent-primary" />
        )}
      </div>
    );
  }

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
