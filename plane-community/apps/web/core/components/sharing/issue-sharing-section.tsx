/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { observer } from "mobx-react";
import { Lock } from "lucide-react";
// plane imports
import { useTranslation } from "@plane/i18n";
// hooks
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { useUser } from "@/hooks/store/user";
// local imports
import { SharingPanel } from "./sharing-panel";

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
};

/** "Permissions" section for the work item sidebar (full page and peek view). */
export const IssueSharingSection = observer(function IssueSharingSection(props: Props) {
  const { workspaceSlug, projectId, issueId } = props;
  const { t } = useTranslation();
  const { data: currentUser } = useUser();
  const {
    issue: { getIssueById },
  } = useIssueDetail();
  const issue = getIssueById(issueId);
  if (!issue) return null;

  return (
    <section className="mt-5 mb-4 border-t border-subtle-1 pt-4" aria-label={t("sharing.title")}>
      <h5 className="mb-3 flex items-center gap-1.5 text-body-xs-medium">
        <Lock className="size-3.5" />
        {t("sharing.title")}
      </h5>
      <SharingPanel
        item={{ kind: "issue", workspaceSlug, projectId, itemId: issueId }}
        isCreator={!!currentUser?.id && currentUser.id === issue.created_by}
      />
    </section>
  );
});
