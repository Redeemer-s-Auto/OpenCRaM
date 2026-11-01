/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { GANTT_TIMELINE_TYPE } from "@plane/types";
// components
import { ProjectAccessRestriction } from "@/components/auth-screens/project/project-access-restriction";
import {
  PROJECT_DETAILS,
  PROJECT_ME_INFORMATION,
  PROJECT_LABELS,
  PROJECT_CUSTOM_FIELDS,
  PROJECT_MEMBERS,
  PROJECT_MEMBER_PREFERENCES,
  PROJECT_STATES,
  PROJECT_ESTIMATES,
  PROJECT_ALL_CYCLES,
  PROJECT_MODULES,
  PROJECT_VIEWS,
  PROJECT_INTAKE_STATE,
} from "@plane/constants";
// hooks
import { useProjectEstimates } from "@/hooks/store/estimates";
import { useCycle } from "@/hooks/store/use-cycle";
import { useCustomField } from "@/hooks/store/use-custom-field";
import { useLabel } from "@/hooks/store/use-label";
import { useMember } from "@/hooks/store/use-member";
import { useModule } from "@/hooks/store/use-module";
import { useProject } from "@/hooks/store/use-project";
import { useProjectState } from "@/hooks/store/use-project-state";
import { useProjectView } from "@/hooks/store/use-project-view";
import { useUser, useUserPermissions } from "@/hooks/store/user";
import { useTimeLineChart } from "@/hooks/use-timeline-chart";

interface IProjectAuthWrapper {
  workspaceSlug: string;
  projectId: string;
  children: ReactNode;
  isLoading?: boolean;
}

export const ProjectAuthWrapper = observer(function ProjectAuthWrapper(props: IProjectAuthWrapper) {
  const { workspaceSlug, projectId, children, isLoading: isParentLoading = false } = props;
  // states
  const [isJoiningProject, setIsJoiningProject] = useState(false);
  // store hooks
  const { fetchUserProjectInfo, allowPermissions, getProjectRoleByWorkspaceSlugAndProjectId } = useUserPermissions();
  const { fetchProjectDetails, getProjectById } = useProject();
  const { joinProject } = useUserPermissions();
  const { fetchAllCycles } = useCycle();
  const { fetchModulesSlim, fetchModules } = useModule();
  const { initGantt } = useTimeLineChart(GANTT_TIMELINE_TYPE.MODULE);
  const { fetchViews } = useProjectView();
  const {
    project: { fetchProjectMembers, fetchProjectUserProperties },
  } = useMember();
  const { fetchProjectStates, fetchProjectIntakeState } = useProjectState();
  const { data: currentUserData } = useUser();
  const { fetchProjectLabels } = useLabel();
  const { fetchProjectFields } = useCustomField();
  const { getProjectEstimates } = useProjectEstimates();
  // derived values
  const hasPermissionToCurrentProject = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER, EUserPermissions.GUEST],
    EUserPermissionsLevel.PROJECT,
    workspaceSlug,
    projectId
  );
  const currentProjectRole = getProjectRoleByWorkspaceSlugAndProjectId(workspaceSlug, projectId);
  const isWorkspaceAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE, workspaceSlug);
  // Cycles and modules are off on almost every board. Their lists are the slowest calls of a board load
  // (about 0.3-2.5 s each on the 2-CPU server) and nothing on a board shows them while the feature is off,
  // so fetch them only when the board has the feature on. Turning it on later fills in the key and fetches.
  const projectDetails = getProjectById(projectId);
  const isCycleEnabled = !!projectDetails?.cycle_view;
  const isModuleEnabled = !!projectDetails?.module_view;
  // Initialize module timeline chart
  useEffect(() => {
    initGantt();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // fetching project details
  const { isLoading: isProjectDetailsLoading, error: projectDetailsError } = useSWR(
    PROJECT_DETAILS(workspaceSlug, projectId),
    () => fetchProjectDetails(workspaceSlug, projectId)
  );
  // fetching user project member information
  const { isLoading: isProjectMeLoading } = useSWR(PROJECT_ME_INFORMATION(workspaceSlug, projectId), () =>
    fetchUserProjectInfo(workspaceSlug, projectId)
  );
  // The keys below carry the project role. While the role is still unknown (undefined) they would
  // fetch once with "_undefined" and again when the role lands: wait for it (or for the me-call to
  // finish, whatever it says) so each list is fetched once.
  const isRoleSettled = currentProjectRole !== undefined || !isProjectMeLoading;
  const ready = (key: string) => (isRoleSettled ? key : null);
  // fetching project member preferences
  useSWR(
    currentUserData?.id ? ready(PROJECT_MEMBER_PREFERENCES(projectId, currentProjectRole)) : null,
    currentUserData?.id ? () => fetchProjectUserProperties(workspaceSlug, projectId) : null,
    { revalidateIfStale: false, revalidateOnFocus: false }
  );
  // fetching project labels
  useSWR(ready(PROJECT_LABELS(projectId, currentProjectRole)), () => fetchProjectLabels(workspaceSlug, projectId), {
    revalidateIfStale: false,
    revalidateOnFocus: false,
  });
  // fetching project custom fields
  useSWR(
    ready(PROJECT_CUSTOM_FIELDS(projectId, currentProjectRole)),
    () => fetchProjectFields(workspaceSlug, projectId),
    { revalidateIfStale: false, revalidateOnFocus: false }
  );
  // fetching project members
  useSWR(ready(PROJECT_MEMBERS(projectId, currentProjectRole)), () => fetchProjectMembers(workspaceSlug, projectId), {
    revalidateIfStale: false,
    revalidateOnFocus: false,
  });
  // fetching project states
  useSWR(ready(PROJECT_STATES(projectId, currentProjectRole)), () => fetchProjectStates(workspaceSlug, projectId), {
    revalidateIfStale: false,
    revalidateOnFocus: false,
  });
  // fetching project intake state
  useSWR(
    ready(PROJECT_INTAKE_STATE(projectId, currentProjectRole)),
    () => fetchProjectIntakeState(workspaceSlug, projectId),
    { revalidateIfStale: false, revalidateOnFocus: false }
  );
  // fetching project estimates
  useSWR(
    ready(PROJECT_ESTIMATES(projectId, currentProjectRole)),
    () => getProjectEstimates(workspaceSlug, projectId),
    { revalidateIfStale: false, revalidateOnFocus: false }
  );
  // fetching project cycles
  useSWR(
    isCycleEnabled ? ready(PROJECT_ALL_CYCLES(projectId, currentProjectRole)) : null,
    () => fetchAllCycles(workspaceSlug, projectId),
    { revalidateIfStale: false, revalidateOnFocus: false }
  );
  // fetching project modules
  useSWR(
    isModuleEnabled ? ready(PROJECT_MODULES(projectId, currentProjectRole)) : null,
    async () => {
      await Promise.all([fetchModulesSlim(workspaceSlug, projectId), fetchModules(workspaceSlug, projectId)]);
    },
    { revalidateIfStale: false, revalidateOnFocus: false }
  );
  // fetching project views
  useSWR(ready(PROJECT_VIEWS(projectId, currentProjectRole)), () => fetchViews(workspaceSlug, projectId), {
    revalidateIfStale: false,
    revalidateOnFocus: false,
  });

  // handle join project
  const handleJoinProject = () => {
    setIsJoiningProject(true);
    joinProject(workspaceSlug, projectId).finally(() => setIsJoiningProject(false));
  };

  const isProjectLoading = (isParentLoading || isProjectDetailsLoading) && !projectDetailsError;

  if (isProjectLoading) return null;

  if (!isProjectLoading && hasPermissionToCurrentProject === false) {
    return (
      <ProjectAccessRestriction
        errorStatusCode={projectDetailsError?.status}
        isWorkspaceAdmin={isWorkspaceAdmin}
        handleJoinProject={handleJoinProject}
        isJoinButtonDisabled={isJoiningProject}
      />
    );
  }

  return <>{children}</>;
});
