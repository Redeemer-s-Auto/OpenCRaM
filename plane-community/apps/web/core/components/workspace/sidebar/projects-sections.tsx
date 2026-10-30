/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

// Sidebar sections: Private, Teamspaces (one group per teamspace the person belongs to), then
// the workspace projects. The server works out `section` and `teamspace_detail` per board and
// a board inside another board always follows its parent, so only the tree's top level is split.

import type { ReactNode } from "react";
import { observer } from "mobx-react";
// plane imports
import { useLocalStorage } from "@plane/hooks";
import { ChevronRightIcon } from "@plane/propel/icons";
import { IconButton } from "@plane/propel/icon-button";
import type { TPartialProject } from "@plane/types";
import { cn } from "@plane/utils";

export type TSidebarTeamspaceGroup = {
  id: string;
  name: string;
  position: number;
  /** Top-level boards of this teamspace, in sidebar order. */
  rootIds: string[];
};

export type TSidebarProjectSections = {
  privateIds: string[];
  /** Ordered by position, then name. Only teamspaces that hold at least one visible board. */
  teamspaces: TSidebarTeamspaceGroup[];
  workspaceIds: string[];
};

/** Split the tree's top-level ids (already in sidebar order) into the three sections. */
export const groupSidebarRoots = (
  rootIds: string[],
  getProject: (projectId: string) => TPartialProject | undefined
): TSidebarProjectSections => {
  const privateIds: string[] = [];
  const workspaceIds: string[] = [];
  const byTeamspace = new Map<string, TSidebarTeamspaceGroup>();
  rootIds.forEach((projectId) => {
    const project = getProject(projectId);
    const detail = project?.teamspace_detail;
    if (project?.section === "private") privateIds.push(projectId);
    else if (project?.section === "teamspace" && detail) {
      const group = byTeamspace.get(detail.id);
      if (group) group.rootIds.push(projectId);
      else {
        byTeamspace.set(detail.id, {
          id: detail.id,
          name: detail.name,
          position: detail.position,
          rootIds: [projectId],
        });
      }
    } else workspaceIds.push(projectId);
  });
  const teamspaces = Array.from(byTeamspace.values()).sort(
    (a, b) => a.position - b.position || a.name.localeCompare(b.name)
  );
  return { privateIds, teamspaces, workspaceIds };
};

type TSidebarSectionProps = {
  /** Used for the open/closed memory in localStorage. */
  storageKey: string;
  title: string;
  /** Rendered on the right of the header while hovered (e.g. an add button). */
  actions?: ReactNode;
  children: ReactNode;
};

/** A collapsible sidebar section styled like the "Projects" header. Starts open. */
export const SidebarProjectSection = observer(function SidebarProjectSection(props: TSidebarSectionProps) {
  const { storageKey, title, actions, children } = props;
  const { storedValue, setValue } = useLocalStorage<boolean>(storageKey, true);
  const isOpen = storedValue !== false;
  return (
    <div className="flex flex-col">
      <div className="group flex w-full items-center justify-between rounded-sm px-2 py-1.5 text-placeholder hover:bg-layer-transparent-hover">
        <button
          type="button"
          className="flex w-full items-center gap-1 text-left text-13 font-semibold whitespace-nowrap text-placeholder"
          onClick={() => setValue(!isOpen)}
          aria-expanded={isOpen}
          aria-label={isOpen ? `Close ${title}` : `Open ${title}`}
        >
          <span className="text-13 font-semibold">{title}</span>
        </button>
        <div className="flex items-center gap-1">
          {actions}
          <IconButton
            variant="ghost"
            size="sm"
            icon={ChevronRightIcon}
            onClick={() => setValue(!isOpen)}
            className="text-placeholder"
            iconClassName={cn("transition-transform", { "rotate-90": isOpen })}
            aria-label={isOpen ? `Close ${title}` : `Open ${title}`}
          />
        </div>
      </div>
      {isOpen && <div className="flex flex-col gap-0.5">{children}</div>}
    </div>
  );
});

type TSidebarTeamspaceGroupProps = {
  workspaceSlug: string;
  teamspace: TSidebarTeamspaceGroup;
  children: ReactNode;
};

/** One teamspace inside the "Teamspaces" section: its name, a chevron, and its boards indented under it. */
export const SidebarTeamspaceGroup = observer(function SidebarTeamspaceGroup(props: TSidebarTeamspaceGroupProps) {
  const { workspaceSlug, teamspace, children } = props;
  const { storedValue, setValue } = useLocalStorage<boolean>(
    `sidebar_teamspace_open_${workspaceSlug}_${teamspace.id}`,
    true
  );
  const isOpen = storedValue !== false;
  return (
    <div className="flex flex-col">
      <button
        type="button"
        onClick={() => setValue(!isOpen)}
        aria-expanded={isOpen}
        aria-label={isOpen ? `Close ${teamspace.name}` : `Open ${teamspace.name}`}
        className="group/teamspace flex w-full items-center gap-1.5 rounded-md px-2 py-1.5 text-left text-13 font-medium text-secondary hover:bg-layer-transparent-hover"
      >
        <span className="grid size-4 flex-shrink-0 place-items-center rounded-sm text-placeholder">
          <ChevronRightIcon
            className={cn("size-3 transition-transform", {
              "rotate-90": isOpen,
            })}
          />
        </span>
        <span className="truncate">{teamspace.name}</span>
      </button>
      {isOpen && <div className="flex flex-col gap-0.5 pl-3">{children}</div>}
    </div>
  );
});
