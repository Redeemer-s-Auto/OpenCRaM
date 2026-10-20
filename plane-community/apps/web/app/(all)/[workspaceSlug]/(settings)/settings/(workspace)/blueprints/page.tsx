/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useRef, useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { cn } from "@plane/utils";
// components
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { BlueprintIcon, describeSummary, downloadBlueprint } from "@/components/blueprints/helpers";
import { CountChip } from "@/components/common/count-chip";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
import { useUser, useUserPermissions } from "@/hooks/store/user";
// services
import type { TBlueprint } from "@/services/blueprint.service";
import { blueprintErrorMessage, blueprintService } from "@/services/blueprint.service";
// local imports
import type { Route } from "./+types/page";
import { BlueprintsWorkspaceSettingsHeader } from "./header";

type TDraft = { id: string; name: string; description: string; is_shared: boolean };

const inputClass =
  "rounded-md border border-subtle bg-layer-2 px-3 py-2 text-body-xs-regular text-primary outline-none focus:border-accent-strong";

const WorkspaceBlueprintsSettingsPage = observer(function WorkspaceBlueprintsSettingsPage({
  params,
}: Route.ComponentProps) {
  const { workspaceSlug } = params;
  const { currentWorkspace } = useWorkspace();
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const { data: currentUser } = useUser();
  // state
  const [draft, setDraft] = useState<TDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  // data
  const { data: blueprints, mutate } = useSWR(`BOARD_BLUEPRINTS_${workspaceSlug}`, () =>
    blueprintService.list(workspaceSlug)
  );
  const selected = blueprints?.find((b) => b.id === draft?.id);
  const { data: versions, mutate: mutateVersions } = useSWR(
    selected ? `BOARD_BLUEPRINT_VERSIONS_${selected.id}_${selected.version}` : null,
    () => blueprintService.versions(workspaceSlug, selected!.id)
  );
  // derived values
  const isMember = allowPermissions([EUserPermissions.ADMIN, EUserPermissions.MEMBER], EUserPermissionsLevel.WORKSPACE);
  const pageTitle = currentWorkspace?.name ? `${currentWorkspace.name} - Blueprints` : undefined;

  if (workspaceUserInfo && !isMember) return <NotAuthorizedView section="settings" className="h-auto" />;

  const fail = (title: string, error: unknown) =>
    setToast({ type: TOAST_TYPE.ERROR, title, message: blueprintErrorMessage(error) });

  const run = async (action: () => Promise<void>, errorTitle: string) => {
    setBusy(true);
    try {
      await action();
    } catch (error) {
      fail(errorTitle, error);
    } finally {
      setBusy(false);
    }
  };

  const open = (blueprint: TBlueprint) =>
    setDraft({
      id: blueprint.id,
      name: blueprint.name,
      description: blueprint.description,
      is_shared: blueprint.is_shared,
    });

  const save = () =>
    run(async () => {
      if (!draft || !selected) return;
      const body: Partial<TDraft> = { name: draft.name, description: draft.description };
      if (selected.created_by?.id === currentUser?.id && draft.is_shared !== selected.is_shared)
        body.is_shared = draft.is_shared;
      await blueprintService.update(workspaceSlug, draft.id, body);
      await mutate();
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Blueprint saved", message: draft.name });
    }, "Could not save the blueprint");

  const updateFromBoard = () =>
    run(async () => {
      if (!selected) return;
      const updated = await blueprintService.updateFromBoard(workspaceSlug, selected.id);
      await mutate();
      await mutateVersions();
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: `Updated to version ${updated.version}`,
        message: `Copied the design of ${selected.source_project?.name ?? "the board"} again.`,
      });
    }, "Could not update the blueprint");

  const exportFile = (blueprint: TBlueprint) =>
    run(async () => {
      const document = await blueprintService.exportDocument(workspaceSlug, blueprint.id);
      downloadBlueprint(blueprint.name, document);
    }, "Could not export the blueprint");

  const importFile = (file: File) =>
    run(async () => {
      let document: unknown;
      try {
        document = JSON.parse(await file.text());
      } catch {
        throw { error: "That file is not a blueprint (it is not valid JSON)." };
      }
      const created = await blueprintService.importDocument(workspaceSlug, document);
      await mutate();
      open(created);
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: "Blueprint imported",
        message: `${created.name}: ${describeSummary(created.summary)}`,
      });
    }, "Could not import the blueprint");

  const remove = () =>
    run(async () => {
      if (!selected) return;
      if (!window.confirm(`Delete the blueprint "${selected.name}"? Boards already made from it stay as they are.`))
        return;
      await blueprintService.remove(workspaceSlug, selected.id);
      await mutate();
      setDraft(null);
    }, "Could not delete the blueprint");

  const isCreator = selected?.created_by?.id === currentUser?.id;

  return (
    <SettingsContentWrapper header={<BlueprintsWorkspaceSettingsHeader />} hugging>
      <PageHead title={pageTitle} />
      <section className="flex size-full flex-wrap gap-6">
        <div className="flex min-w-0 flex-col gap-4" style={{ flex: "999 1 480px" }}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h4 className="flex items-center gap-2 text-h5-medium text-primary">
                Blueprints
                {blueprints && <CountChip count={blueprints.length} className="h-5" />}
              </h4>
              <p className="mt-1 max-w-xl text-body-xs-regular text-tertiary">
                A blueprint is a saved board design: its fields, workflow, labels, views, layout and card templates. Use
                one to start a new board the same way. Save one from a board&apos;s settings. Export a blueprint to
                share it with another workspace; import one someone shared with you.
              </p>
            </div>
            <div className="flex gap-2">
              <input
                ref={fileInput}
                type="file"
                accept=".json,application/json"
                className="hidden"
                aria-label="Blueprint file to import"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = "";
                  if (file) void importFile(file);
                }}
              />
              <Button variant="secondary" size="lg" disabled={busy} onClick={() => fileInput.current?.click()}>
                Import blueprint
              </Button>
            </div>
          </div>
          <div className="overflow-x-auto rounded-md border border-subtle">
            <table className="w-full text-left text-body-xs-regular">
              <thead className="bg-layer-1 text-caption-md-medium text-tertiary">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Name</th>
                  <th className="px-4 py-2.5 font-medium">Version</th>
                  <th className="px-4 py-2.5 font-medium">What it holds</th>
                  <th className="px-4 py-2.5 font-medium">Who can use it</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-subtle-1">
                {blueprints?.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-4 text-tertiary">
                      No blueprints yet. Open a board&apos;s settings and choose &quot;Save as blueprint&quot;, or
                      import a blueprint file.
                    </td>
                  </tr>
                )}
                {blueprints?.map((blueprint) => (
                  <tr key={blueprint.id} className={cn(draft?.id === blueprint.id && "bg-accent-subtle")}>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        className="flex items-center gap-2 text-left text-body-xs-medium text-primary hover:underline"
                        onClick={() => open(blueprint)}
                      >
                        <BlueprintIcon logo={blueprint.logo_props} />
                        {blueprint.name}
                      </button>
                      {blueprint.description && (
                        <p className="mt-0.5 line-clamp-2 text-caption-md-regular text-tertiary">
                          {blueprint.description}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-secondary">v{blueprint.version}</td>
                    <td className="px-4 py-3 text-secondary">{describeSummary(blueprint.summary)}</td>
                    <td className="px-4 py-3 text-secondary">{blueprint.is_shared ? "Everyone" : "Only me"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {draft && selected && (
          <aside
            className="flex flex-col gap-4 rounded-md border border-subtle bg-layer-1 p-5"
            style={{ flex: "1 1 320px", maxWidth: 440 }}
          >
            <h5 className="flex items-center gap-2 text-body-sm-medium text-primary">
              <BlueprintIcon logo={selected.logo_props} />
              {selected.name} <span className="text-tertiary">v{selected.version}</span>
            </h5>
            <p className="text-caption-md-regular text-tertiary">
              {selected.source_project ? `Made from the board ${selected.source_project.name}. ` : ""}
              {selected.created_by?.display_name ? `Saved by ${selected.created_by.display_name}.` : ""}
            </p>
            {selected.can_manage ? (
              <>
                <label className="flex flex-col gap-1.5 text-caption-md-regular text-tertiary">
                  Name
                  <input
                    className={inputClass}
                    value={draft.name}
                    maxLength={255}
                    onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                  />
                </label>
                <label className="flex flex-col gap-1.5 text-caption-md-regular text-tertiary">
                  Description
                  <textarea
                    className={cn(inputClass, "min-h-20")}
                    value={draft.description}
                    onChange={(e) => setDraft({ ...draft, description: e.target.value })}
                  />
                </label>
                {isCreator && (
                  <label className="flex items-center gap-2 text-body-xs-regular text-secondary">
                    <input
                      type="checkbox"
                      checked={draft.is_shared}
                      onChange={(e) => setDraft({ ...draft, is_shared: e.target.checked })}
                    />
                    Everyone in the workspace can use it
                  </label>
                )}
              </>
            ) : (
              <p className="text-body-xs-regular text-secondary">{selected.description || "No description."}</p>
            )}
            <div className="rounded-md border border-subtle bg-layer-2 p-3 text-caption-md-regular text-secondary">
              <p>{describeSummary(selected.summary)}</p>
              {selected.summary.is_private && <p className="mt-1">Boards made from it are private.</p>}
              {selected.summary.pick_boards.length > 0 && (
                <p className="mt-1">
                  Links to other boards: {selected.summary.pick_boards.map((p) => p.name).join(", ")}. You pick those
                  boards when you use it.
                </p>
              )}
              {selected.summary.notes.map((note) => (
                <p key={note} className="mt-1 text-tertiary">
                  {note}
                </p>
              ))}
            </div>
            <div className="flex flex-wrap gap-2">
              {selected.can_manage && (
                <Button variant="primary" size="lg" onClick={save} disabled={busy || !draft.name.trim()}>
                  Save
                </Button>
              )}
              {selected.can_update_from_board && (
                <Button variant="secondary" size="lg" onClick={updateFromBoard} disabled={busy}>
                  Update from board
                </Button>
              )}
              {selected.can_manage && (
                <Button variant="secondary" size="lg" onClick={() => exportFile(selected)} disabled={busy}>
                  Export file
                </Button>
              )}
              <Button variant="secondary" size="lg" onClick={() => setDraft(null)}>
                Close
              </Button>
              {selected.can_manage && (
                <Button variant="error-outline" size="lg" onClick={remove} disabled={busy}>
                  Delete
                </Button>
              )}
            </div>
            {selected.summary.sample_cards > 0 && selected.can_manage && (
              <p className="text-caption-md-regular text-tertiary">
                This blueprint holds {selected.summary.sample_cards} sample card(s). They stay in this workspace: an
                exported file never includes them.
              </p>
            )}
            {versions && versions.length > 0 && (
              <div className="flex flex-col gap-1">
                <p className="text-caption-md-medium text-tertiary">Versions</p>
                {versions.map((v) => (
                  <p key={v.version} className="text-caption-md-regular text-secondary">
                    v{v.version} - {v.note}
                    {v.created_by?.display_name ? ` by ${v.created_by.display_name}` : ""},{" "}
                    {new Date(v.created_at).toLocaleDateString()}
                  </p>
                ))}
              </div>
            )}
          </aside>
        )}
      </section>
    </SettingsContentWrapper>
  );
});

export default WorkspaceBlueprintsSettingsPage;
