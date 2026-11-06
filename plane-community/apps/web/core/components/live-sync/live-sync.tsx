/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

// Live sync: what one browser changes shows up in another without a reload. Plane only sends changes to
// the page editor (the live server); cards, boards and the sidebar were fetched once and never again.
// Every few seconds, while the tab is visible, this asks one cheap endpoint ``/live-stamp/`` for change
// markers and refetches only the part whose marker moved: the open board's cards, the board list, the
// page tree. It waits while the person is typing in a field, then catches up.

import { useEffect, useRef } from "react";
import { observer } from "mobx-react";
import { useParams, usePathname } from "next/navigation";
import { EIssuesStoreType } from "@plane/types";
import { loadPageTree } from "@/components/workspace/sidebar/pages-tree";
import { useIssues } from "@/hooks/store/use-issues";
import { useProject } from "@/hooks/store/use-project";
import { pageTreeService } from "@/services/page-tree.service";

const POLL_MS = 8000;

const isTyping = (): boolean => {
  const el = document.activeElement as HTMLElement | null;
  if (!el) return false;
  return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable;
};

type TStamps = { projects?: string; pages?: string; issues?: string | null };

export const LiveSync = observer(function LiveSync() {
  const { workspaceSlug, projectId } = useParams();
  const pathname = usePathname();
  const { fetchPartialProjects } = useProject();
  const { issues: projectIssues } = useIssues(EIssuesStoreType.PROJECT);
  const { issues: viewIssues } = useIssues(EIssuesStoreType.PROJECT_VIEW);
  const slug = workspaceSlug?.toString();
  const project = projectId?.toString();
  const viewMatch = /\/views\/([^/]+)/.exec(pathname ?? "");
  const viewId = viewMatch?.[1];

  // the latest values, read by the timer without restarting it
  const latest = useRef({ fetchPartialProjects, projectIssues, viewIssues, viewId });
  latest.current = { fetchPartialProjects, projectIssues, viewIssues, viewId };
  const seen = useRef<{ key: string; stamps: TStamps }>({ key: "", stamps: {} });

  useEffect(() => {
    if (!slug) return;
    let stopped = false;
    let running = false;
    const key = `${slug}:${project ?? ""}`;
    if (seen.current.key !== key) seen.current = { key, stamps: {} };

    const tick = async () => {
      if (stopped || running || document.visibilityState !== "visible" || isTyping()) return;
      running = true;
      try {
        const next = await pageTreeService.liveStamp(slug, project);
        const prev = seen.current.stamps;
        const first = prev.projects === undefined;
        const jobs: Promise<unknown>[] = [];
        let ok = true;
        if (!first && next.projects !== prev.projects) jobs.push(latest.current.fetchPartialProjects(slug));
        if (!first && next.pages !== prev.pages) loadPageTree(slug, true);
        if (!first && project && next.issues !== prev.issues) {
          const { viewId: view } = latest.current;
          const job = view
            ? latest.current.viewIssues?.fetchIssuesWithExistingPagination?.(slug, project, view, "mutation")
            : latest.current.projectIssues?.fetchIssuesWithExistingPagination?.(slug, project, "mutation");
          if (job) jobs.push(job);
        }
        if (jobs.length) {
          const results = await Promise.allSettled(jobs);
          ok = results.every((r) => r.status === "fulfilled");
        }
        // keep the old marker when a refetch failed, so the next tick tries again
        if (ok && !stopped) seen.current.stamps = next;
      } catch {
        // offline or signed out: try again next time
      } finally {
        running = false;
      }
    };

    const timer = window.setInterval(() => void tick(), POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") void tick();
    };
    document.addEventListener("visibilitychange", onVisible);
    void tick();
    return () => {
      stopped = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [slug, project]);

  return null;
});
