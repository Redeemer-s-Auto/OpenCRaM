/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */
import { gardenProfileName, gardenProfileUrl } from "@/lib/garden-config";

export function GardenProfileLink() {
  const href = gardenProfileUrl;
  return <div className="flex flex-col gap-3 p-4">
    <p className="text-13 text-secondary">Manage your personal information and sign-in options in {gardenProfileName}.</p>
    <a href={href} target="_top" className="inline-flex min-h-11 items-center justify-center rounded-md bg-accent-primary px-4 py-2 text-13 font-medium text-on-color">Open {gardenProfileName} profile ↗</a>
  </div>;
}
