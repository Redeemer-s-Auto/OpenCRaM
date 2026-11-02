/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import type { TLogoProps } from "@plane/types";
// lib
import { brand } from "@/lib/brand-config";
import type { TTabIconKind } from "@/lib/tab-icon";
import { logoToTabIcon, setTabIcon } from "@/lib/tab-icon";

type PageHeadTitleProps = {
  title?: string;
  description?: string;
  /** The board's or page's icon for the browser tab; none = the app icon. */
  logo?: TLogoProps | null;
  /** Built-in icon set the logo's icon name comes from: boards use Material, pages use Lucide. */
  logoKind?: TTabIconKind;
};

/** "<page name> - Notes" on the hub theme, so a narrow tab still shows which page it is. */
export function tabTitle(title: string) {
  return brand.tabName ? `${title} - ${brand.tabName}` : title;
}

export function PageHead(props: PageHeadTitleProps) {
  const { title, logo, logoKind = "material" } = props;
  const logoKey = logo?.in_use ? JSON.stringify(logo) : "";

  useEffect(() => {
    if (title) {
      document.title = tabTitle(title);
    }
  }, [title]);

  useEffect(() => {
    let current = true;
    if (!logoKey) {
      setTabIcon(null);
    } else {
      void logoToTabIcon(JSON.parse(logoKey) as TLogoProps, logoKind).then((href) => {
        if (current) setTabIcon(href);
      });
    }
    return () => {
      current = false;
      // Leaving the page: back to the app icon (the next page sets its own right after).
      setTabIcon(null);
    };
  }, [logoKey, logoKind]);

  return null;
}
