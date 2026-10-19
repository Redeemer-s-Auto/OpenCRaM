/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { Repeat } from "lucide-react";
import { Tooltip } from "@plane/propel/tooltip";
// local
import { formatRunTime } from "./helpers";
import { useRepeatingIssues } from "./use-repeating-issues";

type Props = {
  workspaceSlug: string | undefined;
  projectId: string | null | undefined;
  issueId: string;
  isMobile?: boolean;
};

/** Small repeat icon on board and list cards whose card has a repeat rule. */
export function RepeatBadge(props: Props) {
  const { workspaceSlug, projectId, issueId, isMobile = false } = props;
  const repeating = useRepeatingIssues(workspaceSlug, projectId);
  if (!repeating.has(issueId)) return null;
  const next = repeating.get(issueId);
  const label = next ? `Repeats. Next copy ${formatRunTime(next)}` : "Repeats";
  return (
    <Tooltip tooltipHeading="Repeating card" tooltipContent={label} isMobile={isMobile}>
      <span
        className="flex h-5 flex-shrink-0 items-center justify-center rounded-sm border-[0.5px] border-strong px-1.5"
        aria-label={label}
      >
        <Repeat className="size-3 text-secondary" strokeWidth={2} />
      </span>
    </Tooltip>
  );
}
