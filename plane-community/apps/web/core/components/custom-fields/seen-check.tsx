/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Tooltip } from "@plane/propel/tooltip";
import type { TIssue } from "@plane/types";
import { Checkbox } from "@plane/ui";
import { cn } from "@plane/utils";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";
import { usePlatformOS } from "@/hooks/use-platform-os";
// local
import { getSeenField } from "./helpers";
import { buildCustomFieldsPayload } from "./issue-properties";

/** The board's Seen checkbox field, or undefined when the board is not a task-style board. */
export const useSeenField = (projectId: string | null | undefined) => {
  const { projectId: routerProjectId } = useParams();
  const { getProjectFields } = useCustomField();
  return getSeenField(getProjectFields(projectId ?? routerProjectId?.toString()));
};

type Props = {
  issue: TIssue;
  updateIssue: ((projectId: string | null, issueId: string, data: Partial<TIssue>) => Promise<void>) | undefined;
  isReadOnly: boolean;
  className?: string;
};

/**
 * The check mark at the right end of a task list row: the board's "Seen" box, ticked by the owner
 * once a completed task has been noticed. Renders nothing on a board without the Seen field.
 * The tap target is a full row height on phones. Ticking updates the store at once (then saves), and
 * a card that no longer fits the view's filter (Completed -> Checked) leaves without a list reload.
 */
export const SeenCheck = observer(function SeenCheck(props: Props) {
  const { issue, updateIssue, isReadOnly, className } = props;
  const { isMobile } = usePlatformOS();
  const field = useSeenField(issue.project_id);
  if (!field) return null;

  const checked = issue.custom_fields?.[field.id] === true;
  const canEdit = !isReadOnly && !!updateIssue && !issue.tempId;

  return (
    <Tooltip
      tooltipContent={`${field.name}: ${checked ? "Yes" : "No"}`}
      isMobile={isMobile}
      renderByDefault={false}
    >
      {/* oxlint-disable-next-line jsx_a11y/click-events-have-key-events oxlint-disable-next-line jsx_a11y/no-static-element-interactions */}
      <label
        className={cn(
          "grid size-11 flex-shrink-0 place-items-center rounded-sm sm:size-7",
          canEdit ? "cursor-pointer hover:bg-layer-transparent-hover" : "cursor-default",
          className
        )}
        onClick={(e) => e.stopPropagation()}
        onFocus={(e) => e.stopPropagation()}
      >
        <Checkbox
          checked={checked}
          disabled={!canEdit}
          onChange={(e) => {
            // The store ticks the box at once and drops this card from a view it no longer fits.
            void updateIssue?.(
              issue.project_id,
              issue.id,
              buildCustomFieldsPayload(issue.custom_fields, field.id, e.target.checked)
            )?.catch(() => undefined);
          }}
          aria-label={field.name}
          className="size-5 sm:size-4"
        />
      </label>
    </Tooltip>
  );
});
