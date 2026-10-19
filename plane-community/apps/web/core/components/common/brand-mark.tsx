/**
 * Copyright (c) 2026 The Garden contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 *
 * The logo and name at the left of the top bar in the hub theme
 * (VITE_BRAND_LOGO_URL, VITE_BRAND_NAME; see lib/brand-config.ts).
 */
import { brand } from "@/lib/brand-config";

export function BrandMark() {
  if (!brand.isHub || (!brand.logoUrl && !brand.name)) return null;
  return (
    <span className="brand-mark">
      {brand.logoUrl ? (
        <img src={brand.logoUrl} alt={brand.name || "Logo"} />
      ) : (
        // No logo set: a red initial tile, like the hub's top bar.
        <i className="brand-initial" aria-hidden="true">
          {brand.name.charAt(0).toUpperCase()}
        </i>
      )}
      {brand.name ? <span>{brand.name}</span> : null}
    </span>
  );
}
