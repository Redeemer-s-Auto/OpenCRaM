/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import useSWR from "swr";
import { ChevronRightIcon } from "@plane/propel/icons";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { IProjectView, TIssue } from "@plane/types";
import { Logo } from "@plane/propel/emoji-icon-picker";
import { Loader } from "@plane/ui";
import { cn } from "@plane/utils";
// components
import { SeenCheck } from "@/components/custom-fields/seen-check";
import { IssuePeekOverview } from "@/components/issues/peek-overview";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useProject } from "@/hooks/store/use-project";
import { useProjectView } from "@/hooks/store/use-project-view";
// services
import { IssueService } from "@/services/issue/issue.service";
// local
import { HUB_SECTION_LIMIT, TASK_LIST_HUB } from "./config";

const issueService = new IssueService();

/** A task list's own first tab, the same one its view tabs open first (for a task list: "Active"). */
const firstView = (views: IProjectView[] | undefined) =>
  [...(views ?? [])]
    .filter((view) => !view.is_hidden)
    .sort(
      (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || String(a.created_at).localeCompare(String(b.created_at))
    )[0];

/** A board with no views (Lift 1) shows its open cards in board order. */
const OPEN_ONLY = { state_group__in: ["backlog", "unstarted", "started"] };

type Props = { workspaceSlug: string };

// Each person's open/closed sections are remembered in this browser.
const openKey = (projectId: string) => `task-list-hub:closed:${projectId}`;
const readOpen = (projectId: string) => {
  try {
    return window.localStorage.getItem(openKey(projectId)) !== "1";
  } catch {
    return true;
  }
};
const writeOpen = (projectId: string, value: boolean) => {
  try {
    if (value) window.localStorage.removeItem(openKey(projectId));
    else window.localStorage.setItem(openKey(projectId), "1");
  } catch {
    // storage off: sections simply start open
  }
};

/**
 * The Task Lists Hub: one collapsible section per task list (config.ts), each showing that list's
 * open items in the list's own order, the same items its first tab ("Active") shows. A person
 * only gets the sections of the boards they are a member of; the server checks it again.
 */
export const TaskListHubRoot = observer(function TaskListHubRoot(props: Props) {
  const { workspaceSlug } = props;
  const { getProjectByIdentifier, joinedProjectIds } = useProject();
  const projectIds = TASK_LIST_HUB.lists
    .map((identifier) => getProjectByIdentifier(identifier)?.id)
    .filter((id): id is string => !!id && joinedProjectIds.includes(id));

  return (
    <div className="flex h-full w-full flex-col overflow-auto bg-surface-1 pb-10" data-task-list-hub="">
      {projectIds.length === 0 && (
        <p className="px-4 py-6 text-13 text-tertiary">None of the task lists are shared with you.</p>
      )}
      {projectIds.map((projectId) => (
        <HubSection key={projectId} workspaceSlug={workspaceSlug} projectId={projectId} />
      ))}
      <IssuePeekOverview />
    </div>
  );
});

const HubSection = observer(function HubSection(props: { workspaceSlug: string; projectId: string }) {
  const { workspaceSlug, projectId } = props;
  const { getPartialProjectById } = useProject();
  const { fetchViews, getProjectViews } = useProjectView();
  const { fetchProjectFields } = useCustomField();
  const { peekIssue, setPeekIssue } = useIssueDetail();
  const [open, setOpenState] = useState(() => readOpen(projectId));
  const setOpen = (value: boolean) => {
    setOpenState(value);
    writeOpen(projectId, value);
  };
  const [rows, setRows] = useState<TIssue[] | undefined>(undefined);
  const project = getPartialProjectById(projectId);
  const boardPath = `/${workspaceSlug}/projects/${projectId}`;

  // views (for the first tab's filter and order) and fields (for the Seen check), once per board
  const { data: views, error: viewsError } = useSWR(["hub-views", workspaceSlug, projectId], async () => {
    void fetchProjectFields(workspaceSlug, projectId).catch(() => undefined);
    return (await fetchViews(workspaceSlug, projectId)) ?? getProjectViews(projectId) ?? [];
  });
  const view = views ? firstView(views) : undefined;
  const filters = view ? view.rich_filters : OPEN_ONLY;
  const orderBy = (view?.display_filters?.order_by as string | undefined) || "sort_order";

  const { data, error, mutate } = useSWR(
    views ? ["hub-items", workspaceSlug, projectId, view?.id ?? "open"] : null,
    () =>
      issueService.getIssues(workspaceSlug, projectId, {
        filters: JSON.stringify(filters),
        order_by: orderBy,
        per_page: String(HUB_SECTION_LIMIT),
        cursor: `${HUB_SECTION_LIMIT}:0:0`,
      }),
    { revalidateOnFocus: false }
  );
  // Ticked rows stay in place (ticked) until the next load, so a mistaken tick can be undone right here.
  useEffect(() => {
    if (data) setRows(Array.isArray(data.results) ? (data.results as TIssue[]) : []);
  }, [data]);

  // A card opened from this section and closed again: reload, it may have changed.
  const openedHere = useRef(false);
  useEffect(() => {
    if (!peekIssue && openedHere.current) {
      openedHere.current = false;
      void mutate();
    }
  }, [peekIssue, mutate]);

  const updateIssue = async (issueProjectId: string | null, issueId: string, patch: Partial<TIssue>) => {
    if (!issueProjectId) return;
    const before = rows;
    setRows((current) => current?.map((row) => (row.id === issueId ? { ...row, ...patch } : row)));
    try {
      await issueService.patchIssue(workspaceSlug, issueProjectId, issueId, patch);
    } catch {
      setRows(before);
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not save", message: "Try again." });
    }
  };

  const total = data?.total_count ?? rows?.length ?? 0;
  const failed = !!viewsError || !!error;

  return (
    <section className="border-b border-subtle" data-hub-section={project?.identifier}>
      <div className="sticky top-0 z-[2] flex items-center gap-2 bg-layer-1 px-3 py-1.5">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          aria-label={open ? `Collapse ${project?.name}` : `Expand ${project?.name}`}
          className="grid size-6 flex-shrink-0 place-items-center rounded-sm text-tertiary hover:bg-layer-transparent-hover"
        >
          <ChevronRightIcon className={cn("size-3.5 transition-transform", { "rotate-90": open })} />
        </button>
        {project?.logo_props && <Logo logo={project.logo_props} size={16} />}
        <Link href={view ? `${boardPath}/views/${view.id}` : `${boardPath}/issues`} className="min-w-0 truncate">
          <h2 className="truncate text-16 font-semibold text-primary hover:underline">{project?.name}</h2>
        </Link>
        <span className="flex-shrink-0 text-13 text-tertiary">{data ? total : ""}</span>
      </div>
      {open && (
        <div>
          {failed && <p className="px-4 py-2 text-13 text-danger-primary">Could not load this list.</p>}
          {!failed && !rows && (
            <Loader className="space-y-1 px-4 py-2">
              <Loader.Item height="28px" />
              <Loader.Item height="28px" />
            </Loader>
          )}
          {rows?.length === 0 && <p className="px-4 py-2 text-13 text-tertiary">Nothing open.</p>}
          {rows?.map((issue) => (
            <div
              key={issue.id}
              data-hub-row={issue.id}
              className="flex min-h-11 items-center gap-1 border-b border-subtle px-2 hover:bg-layer-transparent-hover sm:min-h-9"
            >
              <SeenCheck issue={issue} updateIssue={updateIssue} isReadOnly={false} />
              <button
                type="button"
                className="min-w-0 flex-1 truncate py-1.5 pl-1 text-left text-14 text-primary"
                onClick={() => {
                  openedHere.current = true;
                  setPeekIssue({ workspaceSlug, projectId, issueId: issue.id });
                }}
              >
                {issue.name}
              </button>
            </div>
          ))}
          {total > (rows?.length ?? 0) && (
            <Link
              href={view ? `${boardPath}/views/${view.id}` : `${boardPath}/issues`}
              className="block px-4 py-2 text-13 font-medium text-accent-primary hover:underline"
            >
              Open the full list ({total})
            </Link>
          )}
        </div>
      )}
    </section>
  );
});
