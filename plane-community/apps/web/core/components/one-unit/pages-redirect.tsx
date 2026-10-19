/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useEffect } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { EIssueFilterType } from "@plane/constants";
import { EIssueLayoutTypes, EIssuesStoreType } from "@plane/types";
import { Loader } from "@plane/ui";
import { useIssues } from "@/hooks/store/use-issues";
import { useAppRouter } from "@/hooks/use-app-router";

/**
 * Plane Pages are retired (a card is the page). Old Pages links land on the project's
 * cards in the "Page list" layout. The Pages data itself is kept.
 */
export const PagesRedirect = observer(function PagesRedirect() {
  const router = useAppRouter();
  const { workspaceSlug, projectId } = useParams();
  const { issuesFilter } = useIssues(EIssuesStoreType.PROJECT);

  useEffect(() => {
    if (!workspaceSlug || !projectId) return;
    const slug = workspaceSlug.toString();
    const project = projectId.toString();
    let cancelled = false;
    const go = async () => {
      try {
        await issuesFilter.fetchFilters(slug, project);
        await issuesFilter.updateFilters(slug, project, EIssueFilterType.DISPLAY_FILTERS, {
          layout: EIssueLayoutTypes.PAGE_LIST,
        });
      } catch {
        // the cards still open in the last layout used
      }
      if (!cancelled) router.replace(`/${slug}/projects/${project}/issues/`);
    };
    void go();
    return () => {
      cancelled = true;
    };
  }, [workspaceSlug, projectId, issuesFilter, router]);

  return (
    <Loader className="space-y-3 p-5">
      <Loader.Item height="30px" width="40%" />
      <Loader.Item height="15px" width="60%" />
    </Loader>
  );
});

/** The Pages feature switch is hidden; its settings link opens the project's other features. */
export function PagesSettingsRedirect() {
  const router = useAppRouter();
  const { workspaceSlug, projectId } = useParams();
  useEffect(() => {
    if (workspaceSlug && projectId)
      router.replace(`/${workspaceSlug.toString()}/settings/projects/${projectId.toString()}/features/cycles/`);
  }, [workspaceSlug, projectId, router]);
  return null;
}

export default PagesRedirect;
