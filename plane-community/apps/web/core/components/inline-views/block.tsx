/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
import type { TInlineViewRenderProps } from "@plane/editor";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TCustomField } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useProject } from "@/hooks/store/use-project";
// services
import { CustomFieldService } from "@/services/issue/custom_field.service";
import { IssueService } from "@/services/issue/issue.service";
import { InlineViewService } from "@/services/inline-view.service";
import type { TInlineViewCard, TInlineViewQuery, TInlineViewSource } from "@/services/inline-view.service";
// local
import { useInlineViewHost } from "./host-context";
import { BoardLayout, GalleryLayout, ListLayout, TableLayout, allFields } from "./layouts";
import type { TCardPatch, TLayoutProps } from "./layouts";
import { LAYOUTS, PRIORITY_OPTIONS } from "./types";
import type { TViewConfig, TViewLayout } from "./types";

const viewService = new InlineViewService();
const issueService = new IssueService();
const fieldService = new CustomFieldService();

const sourceLabel = (source: TInlineViewSource | undefined, projectName: string | undefined) => {
  if (!source) return "Pick where the cards come from";
  if (source.type === "project") return projectName ?? "Board";
  if (source.type === "children") return "Sub-cards";
  return "Linked cards";
};

const chip = (on: boolean) =>
  cn(
    "rounded-full border px-2 py-0.5 text-11",
    on ? "border-accent-primary bg-accent-primary/10 text-accent-primary" : "border-subtle text-secondary"
  );

/** One live view block: its own source, layout and filter. Shows real cards; edits change the real cards. */
export const InlineViewBlock = observer(function InlineViewBlock(props: TInlineViewRenderProps) {
  const { config: savedConfig, updateConfig, deleteBlock, editable } = props;
  const host = useInlineViewHost();
  const { getPartialProjectById, joinedProjectIds } = useProject();
  // A read-only page cannot save settings, so changes stay in this tab only.
  const [localConfig, setLocalConfig] = useState<TViewConfig | null>(null);
  const config = (localConfig ?? savedConfig) as TViewConfig;
  const [showSettings, setShowSettings] = useState(!config.source);
  const [search, setSearch] = useState("");
  const [newName, setNewName] = useState("");
  const [relationFields, setRelationFields] = useState<TCustomField[]>([]);

  const save = (next: TViewConfig) => {
    if (editable) updateConfig(next as Record<string, unknown>);
    else setLocalConfig(next);
  };
  const change = (patch: Partial<TViewConfig>) => save({ ...config, ...patch });

  const workspaceSlug = host?.workspaceSlug;
  const query: TInlineViewQuery | null = config.source
    ? { source: config.source, filters: config.filters, search: search || undefined, order_by: config.order_by }
    : null;
  const { data, error, mutate } = useSWR(
    workspaceSlug && query ? ["inline-view", workspaceSlug, JSON.stringify(query)] : null,
    () => viewService.query(workspaceSlug as string, query as TInlineViewQuery),
    { keepPreviousData: true, revalidateOnFocus: true }
  );

  // Relation fields of the host card's board, for the "Linked cards" source.
  useEffect(() => {
    if (!workspaceSlug || !host?.projectId || !showSettings) return;
    fieldService
      .list(workspaceSlug, host.projectId)
      .then((fields) => setRelationFields(fields.filter((f) => f.field_type === "relation")))
      .catch(() => setRelationFields([]));
  }, [workspaceSlug, host?.projectId, showSettings]);

  const onPatch: TLayoutProps["onPatch"] = async (card: TInlineViewCard, patch: TCardPatch) => {
    if (!workspaceSlug) return;
    try {
      await issueService.patchIssue(workspaceSlug, card.project_id, card.id, patch as never);
      await mutate();
    } catch (e) {
      const message = (e as { error?: string })?.error ?? "The change was not saved.";
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not save", message });
      await mutate();
    }
  };

  const createProjectId =
    config.source?.type === "project"
      ? config.source.project_id
      : config.source?.type === "children"
        ? host?.projectId
        : undefined;
  const addCard = async () => {
    const name = newName.trim();
    if (!name || !workspaceSlug || !createProjectId) return;
    try {
      const extra: Record<string, unknown> = {};
      if (config.source?.type === "children") extra.parent_id = config.source.parent_id;
      if (config.filters?.priority?.length === 1) extra.priority = config.filters.priority[0];
      if (config.filters?.state?.length === 1) extra.state_id = config.filters.state[0];
      await issueService.createIssue(workspaceSlug, createProjectId, { name, ...extra } as never);
      setNewName("");
      await mutate();
    } catch (e) {
      const message = (e as { error?: string })?.error ?? "The card was not made.";
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not add card", message });
    }
  };

  const projects = data ? Object.values(data.projects) : [];
  const singleProject = config.source?.type === "project" ? data?.projects[config.source.project_id] : undefined;
  const stateChoices = singleProject?.states ?? projects.flatMap((p) => p.states);
  const layout: TViewLayout = config.layout ?? "table";
  const fields = data ? allFields(data) : [];
  const dropdownFields = fields.filter((f) => f.field_type === "select");
  const toggle = (list: string[] | undefined, key: string) =>
    list?.includes(key) ? list.filter((k) => k !== key) : [...(list ?? []), key];
  const layoutProps = data ? { data, config, editable: true, workspaceSlug: workspaceSlug as string, onPatch } : null;

  if (!host) return <div className="rounded-md border border-subtle p-3 text-13 text-tertiary">Live view</div>;

  return (
    <div className="rounded-lg border border-subtle bg-surface-1">
      <div className="flex flex-wrap items-center gap-2 border-b border-subtle px-3 py-2">
        {editable ? (
          <input
            className="min-w-0 flex-1 bg-transparent text-body-sm-medium outline-none placeholder:text-placeholder"
            placeholder="Untitled view"
            value={config.title ?? ""}
            onChange={(e) => change({ title: e.target.value })}
          />
        ) : (
          <span className="min-w-0 flex-1 truncate text-body-sm-medium">{config.title || "Live view"}</span>
        )}
        <span className="text-11 text-tertiary">
          {sourceLabel(
            config.source,
            getPartialProjectById(config.source?.type === "project" ? config.source.project_id : undefined)?.name
          )}
        </span>
        <div className="flex rounded-md border border-subtle">
          {LAYOUTS.map((l) => (
            <button
              key={l.key}
              type="button"
              onClick={() => change({ layout: l.key })}
              className={cn("px-2 py-0.5 text-11", layout === l.key ? "bg-layer-1 font-medium" : "text-secondary")}
            >
              {l.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="text-11 text-secondary hover:underline"
          onClick={() => setShowSettings((v) => !v)}
        >
          {showSettings ? "Done" : "Settings"}
        </button>
        {editable && (
          <button type="button" className="text-11 text-danger-primary hover:underline" onClick={deleteBlock}>
            Remove
          </button>
        )}
      </div>

      {showSettings && (
        <div className="flex flex-col gap-3 border-b border-subtle bg-layer-1 px-3 py-3 text-body-xs-regular">
          <label className="flex flex-wrap items-center gap-2">
            <span className="w-24 text-tertiary">Cards from</span>
            <select
              className="rounded-sm border border-subtle bg-surface-1 px-1.5 py-0.5"
              value={config.source?.type === "project" ? `p:${config.source.project_id}` : (config.source?.type ?? "")}
              onChange={(e) => {
                const v = e.target.value;
                if (v.startsWith("p:"))
                  change({ source: { type: "project", project_id: v.slice(2) }, filters: {}, group_by: "state" });
                else if (v === "children" && host.issueId)
                  change({ source: { type: "children", parent_id: host.issueId }, filters: {} });
                else if (v === "linked" && host.issueId && relationFields[0])
                  change({
                    source: { type: "linked", issue_id: host.issueId, field_id: relationFields[0].id },
                    filters: {},
                  });
              }}
            >
              <option value="" disabled>
                Choose...
              </option>
              {joinedProjectIds.map((id) => (
                <option key={id} value={`p:${id}`}>
                  Board: {getPartialProjectById(id)?.name}
                </option>
              ))}
              {host.issueId && <option value="children">Sub-cards of this card</option>}
              {host.issueId && relationFields.length > 0 && <option value="linked">Cards linked from this card</option>}
            </select>
            {config.source?.type === "linked" && (
              <select
                className="rounded-sm border border-subtle bg-surface-1 px-1.5 py-0.5"
                value={config.source.field_id}
                onChange={(e) =>
                  change({
                    source: {
                      type: "linked",
                      issue_id: (config.source as { issue_id: string }).issue_id,
                      field_id: e.target.value,
                    },
                  })
                }
              >
                {relationFields.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            )}
          </label>

          {layout === "board" && (
            <label className="flex flex-wrap items-center gap-2">
              <span className="w-24 text-tertiary">Columns by</span>
              <select
                className="rounded-sm border border-subtle bg-surface-1 px-1.5 py-0.5"
                value={config.group_by ?? "state"}
                onChange={(e) => change({ group_by: e.target.value })}
              >
                <option value="state">State</option>
                <option value="priority">Priority</option>
                {dropdownFields.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="flex flex-wrap items-center gap-2">
            <span className="w-24 text-tertiary">Sort by</span>
            <select
              className="rounded-sm border border-subtle bg-surface-1 px-1.5 py-0.5"
              value={config.order_by ?? "sort_order"}
              onChange={(e) => change({ order_by: e.target.value })}
            >
              <option value="sort_order">Manual order</option>
              <option value="-created_at">Newest first</option>
              <option value="created_at">Oldest first</option>
              <option value="-updated_at">Recently edited</option>
              <option value="name">Name</option>
              <option value="target_date">Due date</option>
              {fields
                .filter((f) => !["relation", "rollup"].includes(f.field_type))
                .map((f) => (
                  <option key={f.id} value={`custom_field__${f.id}`}>
                    {f.name}
                  </option>
                ))}
            </select>
          </label>

          <div className="flex flex-wrap items-center gap-1.5">
            <span className="w-24 text-tertiary">Priority</span>
            {PRIORITY_OPTIONS.map((p) => (
              <button
                key={p.key}
                type="button"
                className={chip(!!config.filters?.priority?.includes(p.key))}
                onClick={() =>
                  change({ filters: { ...config.filters, priority: toggle(config.filters?.priority, p.key) } })
                }
              >
                {p.label}
              </button>
            ))}
          </div>

          {stateChoices.length > 0 && config.source?.type === "project" && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="w-24 text-tertiary">State</span>
              {stateChoices.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  className={chip(!!config.filters?.state?.includes(s.id))}
                  onClick={() => change({ filters: { ...config.filters, state: toggle(config.filters?.state, s.id) } })}
                >
                  {s.name}
                </button>
              ))}
            </div>
          )}

          {fields.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="w-24 text-tertiary">Fields shown</span>
              {fields.map((f) => {
                const current = config.fields ?? fields.slice(0, 3).map((x) => x.id);
                return (
                  <button
                    key={f.id}
                    type="button"
                    className={chip(current.includes(f.id))}
                    onClick={() => change({ fields: toggle(current, f.id) })}
                  >
                    {f.name}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      <div className="px-2 py-2">
        {!config.source ? (
          <p className="px-1 py-2 text-body-xs-regular text-tertiary">
            Open Settings and pick where the cards come from.
          </p>
        ) : error ? (
          <p className="px-1 py-2 text-body-xs-regular text-danger-primary">This view could not be loaded.</p>
        ) : !data ? (
          <p className="px-1 py-2 text-body-xs-regular text-tertiary">Loading...</p>
        ) : (
          <>
            <div className="mb-2 flex items-center gap-2 px-1">
              <input
                className="w-40 rounded-sm border border-subtle bg-transparent px-1.5 py-0.5 text-body-xs-regular"
                placeholder="Search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              <span className="text-11 text-tertiary">
                {data.count} {data.count === 1 ? "card" : "cards"}
                {data.count > data.results.length ? `, showing ${data.results.length}` : ""}
              </span>
            </div>
            {data.results.length === 0 ? (
              <p className="px-1 py-2 text-body-xs-regular text-tertiary">No cards.</p>
            ) : (
              layoutProps && (
                <>
                  {layout === "table" && <TableLayout {...layoutProps} />}
                  {layout === "board" && <BoardLayout {...layoutProps} />}
                  {layout === "list" && <ListLayout {...layoutProps} />}
                  {layout === "gallery" && <GalleryLayout {...layoutProps} />}
                </>
              )
            )}
            {createProjectId && (
              <div className="mt-2 px-1">
                <input
                  className="w-full rounded-sm border border-dashed border-subtle bg-transparent px-2 py-1 text-body-xs-regular"
                  placeholder="+ New card (press Enter)"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void addCard();
                  }}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
});
