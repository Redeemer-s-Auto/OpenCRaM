/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { SlidersHorizontal } from "lucide-react";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
// components
import { IssueActivityBlockComponent, IssueLink } from "./";

type TIssueCustomFieldActivity = { activityId: string; showIssue?: boolean; ends: "top" | "bottom" | undefined };

/** "set Amount to $1,214.00" / "cleared Amount". The server stores display text. */
export const IssueCustomFieldActivity = observer(function IssueCustomFieldActivity(props: TIssueCustomFieldActivity) {
  const { activityId, showIssue = true, ends } = props;
  const {
    activity: { getActivityById },
  } = useIssueDetail();
  const { getFieldById } = useCustomField();

  const activity = getActivityById(activityId);
  if (!activity) return <></>;

  const field = activity.new_identifier ? getFieldById(activity.new_identifier) : undefined;
  // Relation changes name no cards (who is linked differs per viewer).
  const isRelation = field?.field_type === "relation" || !!activity.comment?.startsWith("updated the linked cards in ");
  const fieldName =
    (isRelation && (field?.name || activity.comment?.replace(/^updated the linked cards in /, ""))) ||
    (activity.new_identifier && getFieldById(activity.new_identifier)?.name) ||
    activity.comment?.replace(/^updated /, "").replace(/ to$/, "") ||
    "a field";

  return (
    <IssueActivityBlockComponent
      icon={<SlidersHorizontal size={14} className="text-secondary" aria-hidden="true" />}
      activityId={activityId}
      ends={ends}
    >
      <>
        {isRelation ? `changed the linked cards in ${fieldName}` : activity.new_value ? `set ${fieldName} to ` : `cleared ${fieldName}`}
        {!isRelation && activity.new_value && <span className="font-medium text-primary">{activity.new_value}</span>}
        {showIssue && (activity.new_value && !isRelation ? ` for ` : ` on `)}
        {showIssue && <IssueLink activityId={activityId} />}.
      </>
    </IssueActivityBlockComponent>
  );
});
