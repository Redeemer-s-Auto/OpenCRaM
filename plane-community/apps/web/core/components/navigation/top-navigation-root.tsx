/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// components
import { observer } from "mobx-react";
import { useParams, usePathname } from "next/navigation";
import { cn } from "@plane/utils";
import { TopNavPowerK } from "@/components/navigation";
import { HelpMenuRoot } from "@/components/workspace/sidebar/help-section/root";
import { UserMenuRoot } from "@/components/workspace/sidebar/user-menu-root";
import { WorkspaceMenuRoot } from "@/components/workspace/sidebar/workspace-menu-root";
import { useAppRailPreferences } from "@/hooks/use-navigation-preferences";
import { Tooltip } from "@plane/propel/tooltip";
import { AppSidebarItem } from "@/components/sidebar/sidebar-item";
import { InboxIcon } from "@plane/propel/icons";
import { BrandMark } from "@/components/common/brand-mark";
import { GardenWorkIcon, showGardenIcons } from "@/components/common/garden-work-icon";
import { gardenOrgName } from "@/lib/garden-config";
import useSWR from "swr";
import { useWorkspaceNotifications } from "@/hooks/store/notifications";
import { useAppTheme } from "@/hooks/store/use-app-theme";
import { IconButton } from "@plane/propel/icon-button";
import { Menu as MenuIcon } from "lucide-react";
// local imports
import { StarUsOnGitHubLink } from "@/app/(all)/[workspaceSlug]/(projects)/star-us-link";
import { useAfterFirstContent } from "@/lib/first-content";

export const TopNavigationRoot = observer(function TopNavigationRoot() {
  // router
  const { workspaceSlug } = useParams();
  const pathname = usePathname();

  // store hooks
  const { unreadNotificationsCount, getUnreadNotificationsCount } = useWorkspaceNotifications();
  const { preferences } = useAppRailPreferences();
  const { sidebarCollapsed, toggleSidebar } = useAppTheme();

  const showLabel = preferences.displayMode === "icon_with_label";
  // Phones: the sidebar is a slide-in menu, opened from here. Settings and the inbox draw no sidebar.
  const hasDrawer = !pathname.includes(`/${workspaceSlug}/settings`) && !pathname.includes("/notifications/");
  // Only an "open" button: while the menu is open, a tap outside it (this bar included) closes it.
  const showMenuButton = hasDrawer && sidebarCollapsed !== false;

  // Fetch notification count (after the first cards: the badge is not needed to draw them)
  const isAfterFirstContent = useAfterFirstContent();
  useSWR(
    workspaceSlug && isAfterFirstContent ? "WORKSPACE_UNREAD_NOTIFICATION_COUNT" : null,
    workspaceSlug && isAfterFirstContent ? () => getUnreadNotificationsCount(workspaceSlug.toString()) : null
  );

  // Calculate notification count
  const isMentionsEnabled = unreadNotificationsCount.mention_unread_notifications_count > 0;
  const totalNotifications = isMentionsEnabled
    ? unreadNotificationsCount.mention_unread_notifications_count
    : unreadNotificationsCount.total_unread_notifications_count;

  return (
    <div
      data-garden-surface="topbar"
      className={cn("z-[27] flex min-h-10 w-full items-center bg-canvas px-3.5 transition-all duration-300", {
        "px-2": !showLabel,
      })}
    >
      {/* Workspace Menu */}
      <div className="flex flex-1 items-center gap-3 shrink-0">
        {showMenuButton && (
          <IconButton
            size="base"
            variant="ghost"
            icon={MenuIcon}
            className="md:hidden"
            aria-label="Open menu"
            onClick={() => toggleSidebar(false)}
          />
        )}
        {/* Phones: the logo and the search box pushed the inbox, help and profile buttons off a 375 px screen. */}
        <span className="hidden md:contents">
          <BrandMark />
        </span>
        {showGardenIcons ? <span className="garden-work-brand"><GardenWorkIcon className="size-5" /><span>{gardenOrgName}<span className="garden-work-brand-subtitle">WORKSPACE</span></span></span> : null}
        <WorkspaceMenuRoot variant="top-navigation" />
      </div>
      {/* Power K Search */}
      <div className="hidden shrink-0 md:block">
        <TopNavPowerK />
      </div>
      {/* Additional Actions */}
      <div className="flex flex-1 shrink-0 items-center justify-end gap-1">
        <Tooltip tooltipContent="Inbox" position="bottom">
          <AppSidebarItem
            variant="link"
            item={{
              href: `/${workspaceSlug?.toString()}/notifications/`,
              icon: (
                <div className="relative">
                  {showGardenIcons ? <GardenWorkIcon name="inbox" className="size-5" /> : <InboxIcon className="size-5" />}
                  {totalNotifications > 0 && (
                    <span className="absolute top-0 right-0 size-2 rounded-full bg-danger-primary" />
                  )}
                </div>
              ),
              isActive: pathname?.includes("/notifications/"),
            }}
          />
        </Tooltip>
        <HelpMenuRoot />
        <StarUsOnGitHubLink />
        <div className="flex size-8 items-center justify-center rounded-md hover:bg-layer-1-hover">
          <UserMenuRoot />
        </div>
      </div>
    </div>
  );
});
