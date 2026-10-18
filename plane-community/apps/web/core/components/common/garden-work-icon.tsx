/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import type { SVGProps } from "react";
export const isGardenWork = process.env.VITE_GARDEN_AUTH_ENABLED === "1";
export function GardenWorkIcon({ name = "garden", ...props }: SVGProps<SVGSVGElement> & { name?: "garden" | "inbox" | "settings" }) {
  return <svg {...props} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {name === "garden" ? <><path d="M12 21V11M12 14C5 14 3 8 3 4c6 0 9 3 9 8M12 11c0-6 4-8 9-8 0 5-3 9-9 9M5 21h14"/></> : name === "inbox" ? <><path d="M4 5h16l2 12v3H2v-3L4 5ZM2 15h6l2 3h4l2-3h6M8 9h8M10 12h4"/></> : <><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.5 5.5l3 3M15.5 15.5l3 3M5.5 18.5l3-3M15.5 8.5l3-3"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/></>}
  </svg>;
}
