/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef, useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { ImageIcon } from "lucide-react";
import type { IIssueDisplayProperties, TIssue } from "@plane/types";
import { ControlLink } from "@plane/ui";
import { cn, generateWorkItemLink, getFileURL } from "@plane/utils";
// components
import { formatCustomFieldValue, getFieldTypeDetails } from "@/components/custom-fields/helpers";
import { isCustomFieldColumnShown, useSpreadsheetCustomFields } from "@/components/custom-fields/spreadsheet-columns";
import { IssueIdentifier } from "@/components/issues/issue-detail/issue-identifier";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useProject } from "@/hooks/store/use-project";
import useIssuePeekOverviewRedirection from "@/hooks/use-issue-peek-overview-redirection";
import { usePlatformOS } from "@/hooks/use-platform-os";
// local imports
import type { TRenderQuickActions } from "../list/list-view-types";
import { IssueProperties } from "../properties/all-properties";
// card shortcuts: a shortcut card shows its target's live title
import { ShortcutAwareTitle } from "@/components/card-links/shortcut-title";

type Props = {
  issue: TIssue & { cover_image?: string | null };
  displayProperties: IIssueDisplayProperties;
  quickActions: TRenderQuickActions;
  updateIssue: ((projectId: string | null, issueId: string, data: Partial<TIssue>) => Promise<void>) | undefined;
  isReadOnly: boolean;
};

/** One gallery tile: cover image, title, built-in properties, then custom fields. */
export const GalleryCard = observer(function GalleryCard(props: Props) {
  const { issue, displayProperties, quickActions, updateIssue, isReadOnly } = props;
  const { workspaceSlug } = useParams();
  const cardRef = useRef<HTMLDivElement>(null);
  const [coverFailed, setCoverFailed] = useState(false);
  const { isMobile } = usePlatformOS();
  const { getProjectIdentifierById } = useProject();
  const { getUserDetails } = useMember();
  const { handleRedirection } = useIssuePeekOverviewRedirection(false);
  const customFields = useSpreadsheetCustomFields();

  const workItemLink = generateWorkItemLink({
    workspaceSlug: workspaceSlug?.toString(),
    projectId: issue.project_id,
    issueId: issue.id,
    projectIdentifier: getProjectIdentifierById(issue.project_id),
    sequenceId: issue.sequence_id,
    isArchived: !!issue.archived_at,
  });

  const cover = issue.cover_image && !coverFailed ? getFileURL(issue.cover_image) : undefined;
  const shownFields = customFields
    .filter((field) => isCustomFieldColumnShown(displayProperties, field.id))
    .map((field) => ({
      field,
      text: formatCustomFieldValue(
        field,
        issue.custom_fields?.[field.id],
        (userId) => getUserDetails(userId)?.display_name
      ),
    }))
    .filter((row) => row.text)
    .slice(0, 6);

  return (
    <div
      ref={cardRef}
      className="group/gallery-card relative flex flex-col overflow-hidden rounded-lg border border-subtle bg-layer-2 shadow-raised-100 transition-shadow hover:shadow-raised-200"
    >
      <ControlLink
        href={workItemLink}
        onClick={() => handleRedirection(workspaceSlug?.toString(), issue, isMobile)}
        disabled={!!issue.tempId}
        className="flex flex-col"
      >
        <div className="relative aspect-[16/9] w-full overflow-hidden bg-layer-1">
          {cover ? (
            <img
              src={cover}
              alt=""
              loading="lazy"
              onError={() => setCoverFailed(true)}
              className="size-full object-cover"
            />
          ) : (
            <div className="grid size-full place-items-center text-placeholder">
              <ImageIcon className="size-6" />
            </div>
          )}
        </div>
        <div className="flex flex-col gap-1 px-3 pt-2.5">
          {issue.project_id && (
            <IssueIdentifier
              issueId={issue.id}
              projectId={issue.project_id}
              size="xs"
              variant="tertiary"
              displayProperties={displayProperties}
            />
          )}
          <span className="line-clamp-2 text-body-sm-medium text-primary">
            <ShortcutAwareTitle
              workspaceSlug={workspaceSlug?.toString()}
              projectId={issue.project_id}
              issueId={issue.id}
              name={issue.name}
            />
          </span>
        </div>
      </ControlLink>

      {shownFields.length > 0 && (
        <dl className="flex flex-col gap-0.5 px-3 pt-1.5 text-caption-md-regular">
          {shownFields.map(({ field, text }) => {
            const Icon = getFieldTypeDetails(field.field_type).icon;
            return (
              <div key={field.id} className="flex min-w-0 items-center gap-1.5 text-secondary" title={field.name}>
                <Icon className="size-3 shrink-0 text-placeholder" />
                <dt className="sr-only">{field.name}</dt>
                <dd className="truncate">{text}</dd>
              </div>
            );
          })}
        </dl>
      )}

      <IssueProperties
        className="flex flex-wrap items-center gap-2 px-3 pt-2 pb-3 whitespace-nowrap text-tertiary"
        issue={issue}
        displayProperties={displayProperties}
        activeLayout="Kanban"
        updateIssue={updateIssue}
        isReadOnly={isReadOnly}
      />

      <div
        className={cn("absolute top-2 right-2 rounded-md bg-layer-2/90", {
          "hidden group-hover/gallery-card:block": !isMobile,
        })}
      >
        {quickActions({ issue, parentRef: cardRef })}
      </div>
    </div>
  );
});
