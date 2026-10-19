/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useEffect, useMemo, useState } from "react";
import { observer } from "mobx-react";
import { X } from "lucide-react";
import useSWR from "swr";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { cn } from "@plane/utils";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { CountChip } from "@/components/common/count-chip";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
// hooks
import { useMember } from "@/hooks/store/use-member";
import { useWorkspace } from "@/hooks/store/use-workspace";
import { useUserPermissions } from "@/hooks/store/user";
// services
import type { TAccessGroup } from "@/services/sharing.service";
import { sharingService } from "@/services/sharing.service";
// local imports
import type { Route } from "./+types/page";
import { GroupsWorkspaceSettingsHeader } from "./header";

type TDraft = { id: string | null; name: string; description: string; member_ids: string[] };

const EMPTY_DRAFT: TDraft = { id: null, name: "", description: "", member_ids: [] };

const WorkspaceGroupsSettingsPage = observer(function WorkspaceGroupsSettingsPage({ params }: Route.ComponentProps) {
  const { workspaceSlug } = params;
  const { t } = useTranslation();
  const { currentWorkspace } = useWorkspace();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const {
    getUserDetails,
    workspace: { workspaceMemberIds },
  } = useMember();
  // state
  const [draft, setDraft] = useState<TDraft | null>(null);
  const [personSearch, setPersonSearch] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  // data
  const { data: groups, mutate } = useSWR(`ACCESS_GROUPS_${workspaceSlug}`, () =>
    sharingService.listGroups(workspaceSlug)
  );
  // derived values
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  const isMember = allowPermissions([EUserPermissions.ADMIN, EUserPermissions.MEMBER], EUserPermissionsLevel.WORKSPACE);
  const pageTitle = currentWorkspace?.name ? `${currentWorkspace.name} - ${t("sharing.groups_title")}` : undefined;
  const nameOf = (userId: string) => {
    const user = getUserDetails(userId);
    return user?.display_name || user?.first_name || "";
  };
  const addablePeople = useMemo(() => {
    if (!draft) return [];
    const query = personSearch.trim().toLowerCase();
    return (workspaceMemberIds ?? [])
      .filter((id) => !draft.member_ids.includes(id))
      .filter((id) => !query || nameOf(id).toLowerCase().includes(query))
      .slice(0, 8);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft, personSearch, workspaceMemberIds]);

  useEffect(() => setPersonSearch(""), [draft?.id]);

  if (workspaceUserInfo && !isMember) return <NotAuthorizedView section="settings" className="h-auto" />;

  const save = async () => {
    if (!draft) return;
    setIsSaving(true);
    try {
      const body = { name: draft.name, description: draft.description, member_ids: draft.member_ids };
      if (draft.id) await sharingService.updateGroup(workspaceSlug, draft.id, body);
      else await sharingService.createGroup(workspaceSlug, body);
      await mutate();
      setDraft(null);
    } catch (error) {
      const message = (error as { error?: string } | undefined)?.error ?? t("something_went_wrong_please_try_again");
      setToast({ type: TOAST_TYPE.ERROR, title: t("error"), message });
    } finally {
      setIsSaving(false);
    }
  };

  const remove = async (groupId: string) => {
    try {
      await sharingService.deleteGroup(workspaceSlug, groupId);
      await mutate();
      setDraft(null);
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: t("error"), message: t("something_went_wrong_please_try_again") });
    }
  };

  return (
    <SettingsContentWrapper header={<GroupsWorkspaceSettingsHeader />} hugging>
      <PageHead title={pageTitle} />
      <section className="flex size-full flex-wrap gap-6">
        <div className="flex min-w-0 flex-col gap-4" style={{ flex: "999 1 480px" }}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h4 className="flex items-center gap-2 text-h5-medium text-primary">
                {t("sharing.groups_title")}
                {groups && <CountChip count={groups.length} className="h-5" />}
              </h4>
              <p className="mt-1 max-w-xl text-body-xs-regular text-tertiary">{t("sharing.groups_description")}</p>
            </div>
            {isAdmin && (
              <Button variant="primary" size="lg" onClick={() => setDraft({ ...EMPTY_DRAFT })}>
                {t("sharing.new_group")}
              </Button>
            )}
          </div>
          {!isAdmin && <p className="text-caption-md-regular text-tertiary">{t("sharing.admins_only")}</p>}
          <div className="overflow-x-auto rounded-md border border-subtle">
            <table className="w-full text-left text-body-xs-regular">
              <thead className="bg-layer-1 text-caption-md-medium text-tertiary">
                <tr>
                  <th className="px-4 py-2.5 font-medium">{t("name")}</th>
                  <th className="px-4 py-2.5 font-medium">{t("sharing.people")}</th>
                  <th className="px-4 py-2.5 font-medium">{t("sharing.shared_items")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-subtle-1">
                {groups?.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-4 py-4 text-tertiary">
                      {t("sharing.no_groups")}
                    </td>
                  </tr>
                )}
                {groups?.map((group: TAccessGroup) => (
                  <tr key={group.id} className={cn(draft?.id === group.id && "bg-accent-subtle")}>
                    <td className="px-4 py-3">
                      {isAdmin ? (
                        <button
                          type="button"
                          className="text-body-xs-medium text-primary hover:underline"
                          onClick={() =>
                            setDraft({
                              id: group.id,
                              name: group.name,
                              description: group.description,
                              member_ids: group.member_ids,
                            })
                          }
                        >
                          {group.name}
                        </button>
                      ) : (
                        <span className="text-body-xs-medium text-primary">{group.name}</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-secondary">{group.member_count}</td>
                    <td className="px-4 py-3 text-secondary">{group.shared_item_count ?? 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {isAdmin && draft && (
          <aside className="flex flex-col gap-4 rounded-md border border-subtle bg-layer-1 p-5" style={{ flex: "1 1 320px", maxWidth: 420 }}>
            <h5 className="text-body-sm-medium text-primary">{draft.id ? t("sharing.edit_group") : t("sharing.new_group")}</h5>
            <label className="flex flex-col gap-1.5 text-caption-md-regular text-tertiary">
              {t("sharing.group_name")}
              <input
                className="rounded-md border border-subtle bg-layer-2 px-3 py-2 text-body-xs-regular text-primary outline-none focus:border-accent-strong"
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </label>
            <label className="flex flex-col gap-1.5 text-caption-md-regular text-tertiary">
              {t("sharing.group_description")}
              <input
                className="rounded-md border border-subtle bg-layer-2 px-3 py-2 text-body-xs-regular text-primary outline-none focus:border-accent-strong"
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              />
            </label>
            <div className="flex flex-col gap-2">
              <p className="text-caption-md-regular text-tertiary">{t("sharing.group_people")}</p>
              {draft.member_ids.map((id) => (
                <div key={id} className="flex items-center gap-2 rounded-md border border-subtle bg-layer-2 px-2.5 py-1.5">
                  <span className="flex-grow truncate text-body-xs-regular text-primary">{nameOf(id)}</span>
                  <button
                    type="button"
                    aria-label={`${t("sharing.remove")} ${nameOf(id)}`}
                    className="grid size-6 place-items-center rounded-sm text-tertiary hover:bg-layer-1 hover:text-primary"
                    onClick={() => setDraft({ ...draft, member_ids: draft.member_ids.filter((m) => m !== id) })}
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              ))}
              <input
                className="rounded-md border border-dashed border-strong bg-layer-2 px-3 py-2 text-body-xs-regular text-primary outline-none placeholder:text-placeholder"
                placeholder={t("sharing.add_person")}
                aria-label={t("sharing.add_person")}
                value={personSearch}
                onChange={(e) => setPersonSearch(e.target.value)}
              />
              {personSearch && (
                <div className="flex flex-col rounded-md border border-subtle bg-layer-2 p-1">
                  {addablePeople.length === 0 && (
                    <span className="p-2 text-caption-md-regular text-tertiary">{t("sharing.no_results")}</span>
                  )}
                  {addablePeople.map((id) => (
                    <button
                      type="button"
                      key={id}
                      className="rounded-sm px-2 py-1.5 text-left text-body-xs-regular text-primary hover:bg-layer-1"
                      onClick={() => {
                        setDraft({ ...draft, member_ids: [...draft.member_ids, id] });
                        setPersonSearch("");
                      }}
                    >
                      {nameOf(id)}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="flex flex-wrap gap-2 pt-2">
              <Button variant="primary" size="lg" onClick={save} disabled={isSaving || !draft.name.trim()}>
                {t("save")}
              </Button>
              <Button variant="secondary" size="lg" onClick={() => setDraft(null)}>
                {t("cancel")}
              </Button>
              {draft.id && (
                <Button variant="error-outline" size="lg" onClick={() => remove(draft.id!)}>
                  {t("sharing.delete_group")}
                </Button>
              )}
            </div>
          </aside>
        )}
      </section>
    </SettingsContentWrapper>
  );
});

export default WorkspaceGroupsSettingsPage;
