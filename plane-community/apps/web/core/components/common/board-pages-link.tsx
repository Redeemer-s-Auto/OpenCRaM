/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { observer } from "mobx-react";
import Link from "next/link";
import { FileText } from "lucide-react";
import { Tooltip } from "@plane/propel/tooltip";
// hooks
import { useProject } from "@/hooks/store/use-project";

type Props = { workspaceSlug: string | undefined; projectId: string | undefined };

/**
 * "Pages" in the board header. The sidebar shows a board as one row (no Work items / Views / Cards
 * under it), so the board's pages are reached from here: they open as the board's cards in the
 * page list layout (the /pages address does that since Plane Pages were retired).
 */
export const BoardPagesLink = observer(function BoardPagesLink(props: Props) {
  const { workspaceSlug, projectId } = props;
  const { getPartialProjectById } = useProject();
  const project = projectId ? getPartialProjectById(projectId) : undefined;
  if (!workspaceSlug || !projectId || !project) return null;
  return (
    <Tooltip tooltipContent="This board's pages">
      <Link
        href={`/${workspaceSlug}/projects/${projectId}/pages`}
        data-board-pages-link=""
        aria-label="Pages"
        className="flex h-7 flex-shrink-0 items-center gap-1 rounded-md border border-subtle-1 px-2 text-13 text-secondary hover:bg-layer-1"
      >
        <FileText className="size-3.5" />
        <span className="hidden @4xl:inline">Pages</span>
      </Link>
    </Tooltip>
  );
});
