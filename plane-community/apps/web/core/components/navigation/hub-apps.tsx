/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 *
 * The hub's apps, drawn two ways:
 * - HubAppRailItems: icon + label in the narrow app rail on the far left (computers and tablets).
 * - HubAppsDrawerList: 44px rows at the top of the slide-in menu on phones, with Home first and
 *   Sign out last, so both are one tap away where the rail is hidden.
 */

import { observer } from "mobx-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { LogOut } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { cn } from "@plane/utils";
// components
import { AppSidebarItem } from "@/components/sidebar/sidebar-item";
// hooks
import { useAppTheme } from "@/hooks/store/use-app-theme";
import { useUser } from "@/hooks/store/user";
// lib
import { isHubTheme } from "@/lib/brand-config";
import { HUB_APPS } from "@/lib/hub-apps";
import type { THubApp } from "@/lib/hub-apps";

/** Same look as AppSidebarItem's link, but a plain anchor: the other apps are on another site. */
const railItemClassName = "group flex flex-col gap-0.5 items-center justify-center text-tertiary";

/** The current app links inside the app (no reload); every other app is a full page change. */
const useAppHref = () => {
  const { workspaceSlug } = useParams();
  return (app: THubApp) => (app.isCurrent && workspaceSlug ? `/${workspaceSlug.toString()}/` : app.href);
};

export const HubAppRailItems = observer(function HubAppRailItems(props: { showLabel: boolean }) {
  const { showLabel } = props;
  const hrefOf = useAppHref();
  return (
    <>
      {HUB_APPS.map((app) => {
        const content = (
          <>
            <AppSidebarItem.Icon icon={<app.icon className="size-5" />} highlight={app.isCurrent} />
            {showLabel && <AppSidebarItem.Label label={app.label} highlight={app.isCurrent} />}
          </>
        );
        if (app.isCurrent)
          return (
            <Link key={app.id} href={hrefOf(app)} className={railItemClassName} aria-current="page" title={app.label}>
              {content}
            </Link>
          );
        return (
          <a key={app.id} href={app.href} className={railItemClassName} title={app.label}>
            {content}
          </a>
        );
      })}
    </>
  );
});

const drawerRowClassName =
  "flex min-h-11 w-full items-center gap-2.5 rounded-md px-2 text-13 font-medium text-secondary hover:bg-layer-transparent-hover";

export const HubAppsDrawerList = observer(function HubAppsDrawerList() {
  const { t } = useTranslation();
  const hrefOf = useAppHref();
  const { signOut } = useUser();
  const { toggleSidebar } = useAppTheme();

  if (!isHubTheme) return null;

  const handleSignOut = () => {
    signOut().catch(() =>
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("auth.sign_out.toast.error.title"),
        message: t("auth.sign_out.toast.error.message"),
      })
    );
  };

  return (
    <nav aria-label="Apps" className="flex flex-col gap-0.5 border-b border-subtle pb-2 md:hidden">
      {HUB_APPS.map((app) =>
        app.isCurrent ? (
          <Link
            key={app.id}
            href={hrefOf(app)}
            aria-current="page"
            onClick={() => toggleSidebar(true)}
            className={cn(drawerRowClassName, "bg-layer-transparent-selected text-primary")}
          >
            <app.icon className="size-4 flex-shrink-0" />
            <span className="truncate">{app.label}</span>
          </Link>
        ) : (
          <a key={app.id} href={app.href} className={drawerRowClassName}>
            <app.icon className="size-4 flex-shrink-0" />
            <span className="truncate">{app.label}</span>
          </a>
        )
      )}
      <button type="button" onClick={handleSignOut} className={cn(drawerRowClassName, "text-danger-primary")}>
        <LogOut className="size-4 flex-shrink-0" />
        <span>{t("sign_out")}</span>
      </button>
    </nav>
  );
});
