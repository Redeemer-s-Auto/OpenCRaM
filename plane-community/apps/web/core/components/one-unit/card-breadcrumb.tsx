/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useEffect, useState } from "react";
import { Breadcrumbs } from "@plane/ui";
import { BreadcrumbLink } from "@/components/common/breadcrumb-link";
import type { TCardAncestor } from "@/services/card-tree.service";
import { cardTreeService } from "@/services/card-tree.service";

/** Fetch the cards above a card (root first). The server already cuts the chain at the first hidden card. */
export function useCardAncestors(workspaceSlug: string | undefined, issueId: string | undefined, parentId?: string | null) {
  const [ancestors, setAncestors] = useState<TCardAncestor[]>([]);
  useEffect(() => {
    let cancelled = false;
    if (!workspaceSlug || !issueId || !parentId) {
      setAncestors([]);
      return;
    }
    cardTreeService
      .breadcrumb(workspaceSlug, issueId)
      .then((rows) => !cancelled && setAncestors(rows))
      .catch(() => !cancelled && setAncestors([]));
    return () => {
      cancelled = true;
    };
  }, [workspaceSlug, issueId, parentId]);
  return ancestors;
}

/** Breadcrumb items for the parent chain, each linking to that card's full page. */
export function cardAncestorCrumbs(workspaceSlug: string, ancestors: TCardAncestor[]) {
  return ancestors.map((ancestor) => {
    const identifier = `${ancestor.project_identifier}-${ancestor.sequence_id}`;
    return (
      <Breadcrumbs.Item
        key={ancestor.id}
        component={
          <BreadcrumbLink
            label={ancestor.name || identifier}
            href={`/${workspaceSlug}/browse/${identifier}/`}
            icon={<span className="block size-2 rounded-full" style={{ backgroundColor: ancestor.state_color ?? undefined }} />}
          />
        }
      />
    );
  });
}
