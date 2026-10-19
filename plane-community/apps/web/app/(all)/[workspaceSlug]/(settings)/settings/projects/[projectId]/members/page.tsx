/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { ProjectMemberList } from "@/components/project/member-list";
import { ProjectSettingsMemberDefaults } from "@/components/project/project-settings-member-defaults";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { SettingsHeading } from "@/components/settings/heading";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";
// local imports
import type { Route } from "./+types/page";
import { MembersProjectSettingsHeader } from "./header";

import { gardenAccessUrl, gardenAdminConfigured, gardenAdminName, gardenLocalProjectMembers, gardenMode, gardenOrgName } from "@/lib/garden-config";

function MembersSettingsPage({ params }: Route.ComponentProps) {
  // router
  const { workspaceSlug, projectId } = params;
  // plane hooks
  const { t } = useTranslation();
  // store hooks
  const { currentProjectDetails } = useProject();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  // derived values
  const pageTitle = currentProjectDetails?.name ? `${currentProjectDetails?.name} - Members` : undefined;
  const isProjectMemberOrAdmin = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.PROJECT
  );
  const isWorkspaceAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const canPerformProjectMemberActions = isProjectMemberOrAdmin || isWorkspaceAdmin;

  if (gardenMode && !gardenLocalProjectMembers) {
    return (
      <SettingsContentWrapper header={<MembersProjectSettingsHeader />} hugging>
        <PageHead title={pageTitle} />
        <section className="flex size-full items-start justify-center p-8">
          <div className="w-full max-w-2xl rounded-xl border border-subtle bg-layer-2 p-6">
            <h4 className="text-h3-medium text-primary">Project access is managed by {gardenOrgName}</h4>
            <p className="mt-2 text-body-sm-regular text-tertiary">
              Project membership and roles are projected from {gardenOrgName} roles, departments, and access policy. Change access in {gardenAdminName} instead of maintaining a second member list here.
            </p>
            {gardenAdminConfigured && (
              <a
                href={gardenAccessUrl}
                target="_top"
                className="mt-4 inline-flex rounded-md bg-accent-primary px-4 py-2 text-body-sm-medium text-on-color hover:opacity-90"
              >
                Open People & Access
              </a>
            )}
          </div>
        </section>
      </SettingsContentWrapper>
    );
  }

  if (workspaceUserInfo && !canPerformProjectMemberActions) {
    return <NotAuthorizedView section="settings" isProjectView className="h-auto" />;
  }

  return (
    <SettingsContentWrapper header={<MembersProjectSettingsHeader />} hugging>
      <PageHead title={pageTitle} />
      <SettingsHeading title={t("common.members")} />
      <ProjectSettingsMemberDefaults projectId={projectId} workspaceSlug={workspaceSlug} />
      <ProjectMemberList projectId={projectId} workspaceSlug={workspaceSlug} />
    </SettingsContentWrapper>
  );
}

export default observer(MembersSettingsPage);
