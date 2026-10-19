/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { observer } from "mobx-react";
import Link from "next/link";
import { FileText, Layers } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
// components
import { PageHead } from "@/components/core/page-title";
// services
import type { TSharedRow } from "@/services/sharing.service";
import { sharedWithMeService } from "@/services/sharing.service";
// local imports
import type { Route } from "./+types/page";

const LEVEL_LABEL: Record<number, string> = { 5: "sharing.level_view", 10: "sharing.level_comment", 15: "sharing.level_edit" };

/** Members of the item's department use the normal screens; everyone else the shared view. */
function hrefFor(workspaceSlug: string, row: TSharedRow) {
  if (row.in_project) {
    return row.kind === "issue"
      ? `/${workspaceSlug}/browse/${row.identifier}/`
      : `/${workspaceSlug}/projects/${row.project_id}/pages/${row.id}/`;
  }
  return `/${workspaceSlug}/shared-with-me/${row.kind === "issue" ? "issues" : "pages"}/${row.id}`;
}

const SharedWithMePage = observer(function SharedWithMePage({ params }: Route.ComponentProps) {
  const { workspaceSlug } = params;
  const { t } = useTranslation();
  const { data: rows } = useSWR(`SHARED_WITH_ME_${workspaceSlug}`, () => sharedWithMeService.list(workspaceSlug));

  return (
    <>
      <PageHead title={t("sharing.shared_with_me")} />
      <div className="h-full w-full overflow-y-auto p-6">
        <div className="mx-auto flex max-w-4xl flex-col gap-2">
          {!rows && <div className="h-40 animate-pulse rounded-md bg-layer-1" />}
          {rows?.length === 0 && (
            <p className="rounded-md border border-subtle p-6 text-center text-body-sm-regular text-tertiary">
              {t("sharing.shared_with_me_empty")}
            </p>
          )}
          {rows && rows.length > 0 && (
            <ul className="flex flex-col divide-y divide-subtle-1 rounded-md border border-subtle">
              {rows.map((row) => {
                const Icon = row.kind === "issue" ? Layers : FileText;
                return (
                  <li key={`${row.kind}-${row.id}`}>
                    <Link
                      href={hrefFor(workspaceSlug, row)}
                      className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 hover:bg-layer-1"
                    >
                      <Icon className="size-4 flex-shrink-0 text-tertiary" aria-hidden="true" />
                      <span className="flex min-w-0 flex-grow basis-64 flex-col">
                        <span className="truncate text-body-sm-medium text-primary">{row.name}</span>
                        <span className="truncate text-caption-md-regular text-tertiary">
                          {[row.identifier, row.project_name, row.state].filter(Boolean).join(" · ")}
                          {row.shared_by ? ` · ${t("sharing.shared_by", { name: row.shared_by.name })}` : ""}
                        </span>
                      </span>
                      <span className="rounded-sm bg-layer-3 px-2 py-0.5 text-caption-md-medium text-secondary">
                        {t(LEVEL_LABEL[row.level])}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>
    </>
  );
});

export default SharedWithMePage;
