/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { Eye, EyeOff, ListChecks, MoreHorizontal } from "lucide-react";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { IProjectView } from "@plane/types";
import { CustomMenu } from "@plane/ui";
import { cn } from "@plane/utils";
// hooks
import { useProjectView } from "@/hooks/store/use-project-view";
import { useUser, useUserPermissions } from "@/hooks/store/user";
import { useAppRouter } from "@/hooks/use-app-router";

/** localStorage key of the last tab a person picked on a board ("all" or a view id). */
export const lastViewTabKey = (projectId: string) => `view-tab:${projectId}`;

const ALL_TAB = "all";

const readLastTab = (projectId: string): string | null => {
  try {
    return window.localStorage.getItem(lastViewTabKey(projectId));
  } catch {
    return null;
  }
};

const writeLastTab = (projectId: string, value: string) => {
  try {
    window.localStorage.setItem(lastViewTabKey(projectId), value);
  } catch {
    // private mode or storage off: the tab bar still works, it just forgets
  }
};

/** Tabs in the order the views were made (the task-list set: Active, Completed, then Checked; All is drawn last). */
const byBoardOrder = (a: IProjectView, b: IProjectView) =>
  (a.sort_order ?? 0) - (b.sort_order ?? 0) || String(a.created_at).localeCompare(String(b.created_at));

type Props = {
  workspaceSlug: string;
  projectId: string;
  /** The open saved view; undefined on the board's own work-items page ("All"). */
  activeViewId?: string;
};

/**
 * A row of tabs above a board: "All" plus the board's saved views, so a person can switch
 * between (for a task list) Active, Completed and the hidden Checked view. Scrolls sideways
 * on a phone. The last pick is remembered per board; opening the board goes back to it.
 */
export const ProjectViewTabs = observer(function ProjectViewTabs(props: Props) {
  const { workspaceSlug, projectId, activeViewId } = props;
  // router
  const router = useAppRouter();
  // store hooks
  const { getProjectViews, updateView, addTaskListViews } = useProjectView();
  const { data: currentUser } = useUser();
  const { allowPermissions } = useUserPermissions();
  // derived values
  const views = [...(getProjectViews(projectId) ?? [])].sort(byBoardOrder);
  const shown = views.filter((view) => !view.is_hidden || view.id === activeViewId);
  const hidden = views.filter((view) => view.is_hidden);
  const activeView = activeViewId ? views.find((view) => view.id === activeViewId) : undefined;
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT, workspaceSlug, projectId);
  const canToggleActive = !!activeView && (isAdmin || activeView.owned_by === currentUser?.id);
  const boardPath = `/${workspaceSlug}/projects/${projectId}`;
  const viewPath = (viewId: string) => `${boardPath}/views/${viewId}`;

  // Remember the open tab, and on the board's own page go back to the remembered view once.
  const redirected = useRef<string | null>(null);
  useEffect(() => {
    if (activeViewId) {
      writeLastTab(projectId, activeViewId);
      return;
    }
    if (redirected.current === projectId || views.length === 0) return;
    redirected.current = projectId;
    const last = readLastTab(projectId);
    if (last && last !== ALL_TAB && views.some((view) => view.id === last)) router.replace(viewPath(last));
    // views.length is enough: the list is loaded with the board
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeViewId, projectId, views.length]);

  if (views.length === 0) return null;

  const handleToggleHidden = async () => {
    if (!activeView) return;
    try {
      await updateView(workspaceSlug, projectId, activeView.id, { is_hidden: !activeView.is_hidden });
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not change the view", message: "Try again." });
    }
  };

  const handleAddTaskListViews = async () => {
    try {
      const result = await addTaskListViews(workspaceSlug, projectId);
      const made = result.created.length;
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: made ? "Task list views added" : "Task list views already here",
        message: made
          ? `${result.created.join(", ")} and the "${result.field.name}" checkbox are ready.`
          : "Active, Completed and Checked were already set up; their filters were refreshed.",
      });
      const active = result.views.find((view) => view.name === "Active");
      if (active) router.push(viewPath(active.id));
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not add the views", message: "Try again." });
    }
  };

  const tabClass = (active: boolean) =>
    cn(
      "flex h-8 flex-shrink-0 items-center gap-1.5 whitespace-nowrap rounded-md border px-3 text-13 font-medium transition-colors",
      active
        ? "border-strong bg-layer-1 text-primary"
        : "border-transparent text-tertiary hover:bg-layer-transparent-hover hover:text-primary"
    );

  return (
    <div className="flex w-full flex-shrink-0 items-center gap-1 border-b border-subtle bg-surface-1 px-2 md:px-3">
      <div
        className="horizontal-scrollbar scrollbar-sm flex min-w-0 flex-1 items-center gap-1 overflow-x-auto py-1.5"
        role="tablist"
        aria-label="Views"
      >
        {shown.map((view) => {
          const active = view.id === activeViewId;
          return (
            <Link
              key={view.id}
              href={viewPath(view.id)}
              className={tabClass(active)}
              role="tab"
              aria-selected={active}
              onClick={() => writeLastTab(projectId, view.id)}
            >
              {view.is_hidden && <EyeOff className="size-3.5 flex-shrink-0" aria-label="Hidden view" />}
              <span className="max-w-40 truncate">{view.name}</span>
            </Link>
          );
        })}
        {/* All is the last tab: the board's own page, no filter */}
        <Link
          href={`${boardPath}/issues`}
          className={tabClass(!activeViewId)}
          role="tab"
          aria-selected={!activeViewId}
          onClick={() => writeLastTab(projectId, ALL_TAB)}
        >
          All
        </Link>
      </div>
      <CustomMenu
        customButton={
          <span
            className="flex size-8 items-center justify-center rounded-md text-tertiary hover:bg-layer-transparent-hover hover:text-primary"
            aria-label="More views"
          >
            <MoreHorizontal className="size-4" />
          </span>
        }
        buttonClassName="flex-shrink-0"
        placement="bottom-end"
        closeOnSelect
      >
        <p className="px-1 pb-1 text-11 font-medium text-tertiary">Hidden views</p>
        {hidden.length === 0 && (
          <CustomMenu.MenuItem disabled>
            <span className="text-placeholder">None hidden</span>
          </CustomMenu.MenuItem>
        )}
        {hidden.map((view) => (
          <CustomMenu.MenuItem key={view.id} onClick={() => router.push(viewPath(view.id))}>
            <span className="flex items-center gap-2">
              <EyeOff className="size-3.5 flex-shrink-0" />
              <span className="truncate">{view.name}</span>
            </span>
          </CustomMenu.MenuItem>
        ))}
        {(canToggleActive || isAdmin) && <hr className="my-1 border-subtle" />}
        {canToggleActive && activeView && (
          <CustomMenu.MenuItem onClick={() => void handleToggleHidden()}>
            <span className="flex items-center gap-2">
              {activeView.is_hidden ? <Eye className="size-3.5" /> : <EyeOff className="size-3.5" />}
              {activeView.is_hidden ? "Show this view in the tabs" : "Hide this view from the tabs"}
            </span>
          </CustomMenu.MenuItem>
        )}
        {isAdmin && (
          <CustomMenu.MenuItem onClick={() => void handleAddTaskListViews()}>
            <span className="flex items-center gap-2">
              <ListChecks className="size-3.5" />
              <span>
                <span className="block">Add task list views</span>
                <span className="block text-11 text-tertiary">Active, Completed, Checked, All + a Seen box</span>
              </span>
            </span>
          </CustomMenu.MenuItem>
        )}
      </CustomMenu>
    </div>
  );
});
