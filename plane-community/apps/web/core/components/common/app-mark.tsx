/**
 * Copyright (c) 2026 The Garden contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 *
 * The app's mark on full-page screens (loading, not ready, error, invitations, new workspace).
 * Garden theme: the Garden mark. Hub theme: the deployment's logo (VITE_BRAND_LOGO_URL), or nothing.
 */
import gardenMark from "@/app/assets/garden-mark.svg?url";
import { cn } from "@plane/utils";
import { brand } from "@/lib/brand-config";
import { gardenAppName } from "@/lib/garden-config";

type Props = {
  /** Classes for the square Garden mark, e.g. "h-20 w-20". */
  gardenClassName: string;
  /** Classes for the hub logo, which is usually wide, e.g. "h-16". */
  hubClassName: string;
};

export function AppMark({ gardenClassName, hubClassName }: Props) {
  if (brand.isHub) {
    if (!brand.logoUrl) return null;
    return (
      <img
        src={brand.logoUrl}
        className={cn("brand-logo-dark-safe w-auto object-contain", hubClassName)}
        alt={brand.name || gardenAppName}
      />
    );
  }
  return <img src={gardenMark} className={cn("object-contain", gardenClassName)} alt={gardenAppName} />;
}
