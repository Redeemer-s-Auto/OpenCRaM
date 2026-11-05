/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// types
import type { TLogoProps } from "@plane/types";
// helpers
import { cn } from "@plane/utils";

type Props = {
  className?: string;
  logo: TLogoProps;
};

export function ProjectLogo(props: Props) {
  const { className, logo } = props;

  if (logo.in_use === "icon" && logo.icon)
    return (
      <span
        style={{
          color: logo.icon.color,
        }}
        className={cn("material-symbols-rounded text-14", className)}
      >
        {logo.icon.name}
      </span>
    );

  if (logo.in_use === "letter" && logo.letter?.text)
    return (
      <span
        style={{
          color: logo.letter.color || "#ffffff",
          backgroundColor: logo.letter.background || "#7a7a7a",
          fontSize: 11,
        }}
        className={cn("inline-grid size-4 place-items-center rounded-sm leading-none font-semibold", className)}
      >
        {logo.letter.text.trim().slice(0, 1)}
      </span>
    );

  if (logo.in_use === "emoji" && logo.emoji)
    return (
      <span className={cn("text-14", className)}>
        {logo.emoji.value?.split("-").map((emoji) => String.fromCodePoint(parseInt(emoji, 10)))}
      </span>
    );

  return <span />;
}
