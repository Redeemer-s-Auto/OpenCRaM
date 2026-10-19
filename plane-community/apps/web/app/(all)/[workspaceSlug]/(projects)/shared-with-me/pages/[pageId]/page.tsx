/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
// components
import { PageHead } from "@/components/core/page-title";
// services
import { sharedWithMeService } from "@/services/sharing.service";
// local imports
import type { Route } from "./+types/page";

const SharedPagePage = observer(function SharedPagePage({ params }: Route.ComponentProps) {
  const { workspaceSlug, pageId } = params;
  const { t } = useTranslation();
  const { data: page, error } = useSWR(`SHARED_PAGE_${pageId}`, () => sharedWithMeService.getPage(workspaceSlug, pageId));

  if (error) return <p className="p-8 text-center text-body-sm-regular text-tertiary">{t("sharing.no_results")}</p>;
  if (!page) return <div className="m-6 h-60 animate-pulse rounded-md bg-layer-1" />;

  return (
    <>
      <PageHead title={page.name} />
      <div className="h-full w-full overflow-y-auto">
        <article className="mx-auto flex max-w-3xl flex-col gap-4 p-6">
          <p className="text-caption-md-medium text-tertiary">
            {[page.project_name, page.owned_by ? t("sharing.shared_by", { name: page.owned_by.name }) : null]
              .filter(Boolean)
              .join(" · ")}
          </p>
          <h1 className="text-h3-medium text-primary">{page.name}</h1>
          <p className="rounded-md bg-layer-1 p-2.5 text-caption-md-regular text-secondary">{t("sharing.view_only_page")}</p>
          {/* description_html is sanitized on the server (nh3) before it reaches here */}
          <div
            className="prose max-w-none text-body-sm-regular text-secondary"
            dangerouslySetInnerHTML={{ __html: page.description_html }}
          />
        </article>
      </div>
    </>
  );
});

export default SharedPagePage;
