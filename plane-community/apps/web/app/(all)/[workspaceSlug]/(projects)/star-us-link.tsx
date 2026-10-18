/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTheme } from "next-themes";
import { useTranslation } from "@plane/i18n";
import githubBlackImage from "@/app/assets/logos/github-black.png?url";
import githubWhiteImage from "@/app/assets/logos/github-white.png?url";

const gardenMode = process.env.VITE_GARDEN_AUTH_ENABLED === "1";

export function StarUsOnGitHubLink() {
  const { t } = useTranslation();
  const { resolvedTheme } = useTheme();

  // Garden Work is a church-owned staff product. Keep upstream source and
  // licensing intact, but do not surface upstream promotional UI to staff.
  if (gardenMode) return null;

  const imageSrc = resolvedTheme === "dark" ? githubWhiteImage : githubBlackImage;

  return (
    <a
      aria-label={t("home.star_us_on_github")}
      className="flex flex-shrink-0 items-center gap-1.5 rounded-sm bg-layer-2 px-3 py-1.5"
      href="https://github.com/makeplane/plane"
      target="_blank"
      rel="noopener noreferrer"
    >
      <img src={imageSrc} className="h-4 w-4 object-contain" alt="GitHub Logo" aria-hidden="true" />
      <span className="hidden text-11 font-medium sm:hidden md:block">{t("home.star_us_on_github")}</span>
    </a>
  );
}
