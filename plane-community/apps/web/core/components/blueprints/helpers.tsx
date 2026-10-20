/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { LayoutTemplate } from "lucide-react";
import { Logo } from "@plane/propel/emoji-icon-picker";
import type { TLogoProps } from "@plane/types";
// services
import type { TBlueprintSummary } from "@/services/blueprint.service";

/** The blueprint's icon, or a generic one when it has none. */
export function BlueprintIcon({ logo, size = 16 }: { logo?: TLogoProps | Record<string, never>; size?: number }) {
  if (logo && "in_use" in logo && logo.in_use) return <Logo logo={logo as TLogoProps} size={size} />;
  return <LayoutTemplate className="shrink-0 text-tertiary" style={{ width: size, height: size }} />;
}

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** "6 fields, 4 states, 2 views, 1 template, 3 sample cards" */
export const describeSummary = (summary: TBlueprintSummary): string => {
  const parts = [
    plural(summary.fields, "field"),
    plural(summary.states, "state"),
    summary.labels ? plural(summary.labels, "label") : null,
    summary.views ? plural(summary.views, "view") : null,
    summary.templates ? plural(summary.templates, "card template") : null,
    summary.sample_cards ? plural(summary.sample_cards, "sample card") : null,
  ];
  return parts.filter(Boolean).join(", ");
};

/** Save a blueprint document as "<name>.blueprint.json". */
export const downloadBlueprint = (name: string, document: unknown) => {
  const blob = new Blob([JSON.stringify(document, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = window.document.createElement("a");
  link.href = url;
  link.download = `${name.replace(/[^A-Za-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "blueprint"}.blueprint.json`;
  window.document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
