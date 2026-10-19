/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { observer } from "mobx-react";
import { Lock, Plus, Search, X } from "lucide-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { cn } from "@plane/utils";
// hooks
import { useProject } from "@/hooks/store/use-project";
// services
import type { TItemShare, TItemSharing, TShareLevel, TShareTargetType, TSharingItem } from "@/services/sharing.service";
import { sharingService } from "@/services/sharing.service";

const LEVELS: { value: TShareLevel; i18n: string }[] = [
  { value: 5, i18n: "sharing.level_view" },
  { value: 10, i18n: "sharing.level_comment" },
  { value: 15, i18n: "sharing.level_edit" },
];

const TYPE_LABEL: Record<TShareTargetType, string> = {
  member: "sharing.type_member",
  project: "sharing.type_project",
  group: "sharing.type_group",
  workspace: "sharing.type_workspace",
};

type Props = {
  item: TSharingItem;
  /** True when the signed-in user created the item (owner for pages). */
  isCreator?: boolean;
  className?: string;
};

function initials(name: string | undefined) {
  if (!name) return "?";
  const parts = name.trim().split(/\s+/);
  return (parts[0][0] + (parts[1]?.[0] ?? "")).toUpperCase();
}

function shareKey(share: Pick<TItemShare, "target_type" | "target_id">) {
  return `${share.target_type}:${share.target_id ?? ""}`;
}

/** Badge shape per target: people round, departments square, everyone wide. */
function TargetBadge({ share }: { share: Pick<TItemShare, "target_type" | "name" | "avatar"> }) {
  if (share.target_type === "member" && share.avatar)
    return <img src={share.avatar} alt="" className="size-7 flex-shrink-0 rounded-full object-cover" />;
  return (
    <span
      aria-hidden="true"
      className={cn(
        "grid size-7 flex-shrink-0 place-items-center bg-layer-3 text-caption-md-medium text-secondary",
        share.target_type === "member" || share.target_type === "group" ? "rounded-full" : "rounded-md"
      )}
    >
      {share.target_type === "workspace" ? "ALL" : initials(share.name)}
    </span>
  );
}

export const SharingPanel = observer(function SharingPanel(props: Props) {
  const { item, isCreator = false, className } = props;
  const { t } = useTranslation();
  const { getProjectById } = useProject();
  const projectName = getProjectById(item.projectId)?.name ?? "";
  // state
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  // data
  const swrKey = `SHARING_${item.kind}_${item.itemId}`;
  const { data, mutate } = useSWR(swrKey, () => sharingService.getSharing(item), { revalidateOnFocus: false });
  const canManage = !!data?.can_manage;

  const save = async (next: TItemSharing) => {
    const previous = data;
    setIsSaving(true);
    await mutate({ ...next, can_manage: canManage }, false);
    try {
      const saved = await sharingService.updateSharing(item, {
        restricted: next.restricted,
        shares: next.restricted ? next.shares.map(({ target_type, target_id, level }) => ({ target_type, target_id, level })) : [],
      });
      await mutate(saved, false);
    } catch {
      await mutate(previous, false);
      setToast({ type: TOAST_TYPE.ERROR, title: t("error"), message: t("sharing.save_error") });
    } finally {
      setIsSaving(false);
    }
  };

  if (!data) return <div className={cn("h-24 animate-pulse rounded-md bg-layer-1", className)} />;

  const shares = data.shares;
  const setRestricted = (restricted: boolean) => {
    if (restricted === data.restricted) return;
    void save({ restricted, shares: restricted ? shares : [] });
  };
  const setLevel = (share: TItemShare, level: TShareLevel) =>
    void save({ restricted: true, shares: shares.map((s) => (shareKey(s) === shareKey(share) ? { ...s, level } : s)) });
  const removeShare = (share: TItemShare) =>
    void save({ restricted: true, shares: shares.filter((s) => shareKey(s) !== shareKey(share)) });
  const addShare = (share: TItemShare) => {
    if (shares.some((s) => shareKey(s) === shareKey(share))) return;
    void save({ restricted: true, shares: [...shares, share] });
  };

  const kindQuestion = item.kind === "issue" ? t("sharing.who_can_see_work_item") : t("sharing.who_can_see_page");

  return (
    <div className={cn("flex flex-col gap-3", isSaving && "opacity-80", className)}>
      <fieldset className="flex flex-col gap-2" disabled={!canManage}>
        <legend className="mb-2 text-body-xs-regular text-tertiary">{kindQuestion}</legend>
        {[
          { value: false, title: t("sharing.department_mode", { project: projectName }), hint: t("sharing.department_mode_hint") },
          { value: true, title: t("sharing.restricted_mode"), hint: t("sharing.restricted_mode_hint") },
        ].map((option) => (
          <label
            key={String(option.value)}
            className={cn(
              "flex cursor-pointer items-start gap-2.5 rounded-md border p-2.5",
              data.restricted === option.value ? "border-accent-strong bg-accent-subtle" : "border-subtle",
              !canManage && "cursor-default"
            )}
          >
            <input
              type="radio"
              name={`sharing-mode-${item.itemId}`}
              className="mt-0.5 accent-[var(--color-accent-primary)]"
              checked={data.restricted === option.value}
              onChange={() => setRestricted(option.value)}
            />
            <span className="flex flex-col">
              <span className="text-body-xs-medium text-primary">{option.title}</span>
              <span className="text-caption-md-regular text-tertiary">{option.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>

      {data.restricted && (
        <>
          <ul className="flex flex-col divide-y divide-subtle-1 rounded-md border border-subtle">
            {shares.length === 0 && <li className="p-2.5 text-caption-md-regular text-tertiary">{t("sharing.nobody_yet")}</li>}
            {shares.map((share) => (
              <li key={shareKey(share)} className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 p-2.5">
                <TargetBadge share={share} />
                <span className="flex min-w-0 flex-grow basis-28 flex-col">
                  <span className="truncate text-body-xs-medium text-primary">
                    {share.target_type === "workspace" ? t("sharing.everybody") : share.name}
                  </span>
                  <span className="text-caption-md-regular text-tertiary">{t(TYPE_LABEL[share.target_type])}</span>
                </span>
                <select
                  aria-label={`${t("sharing.title")}: ${share.name ?? ""}`}
                  className="rounded-sm border border-subtle bg-layer-2 px-1.5 py-1 text-caption-md-regular text-secondary disabled:opacity-70"
                  value={share.level}
                  disabled={!canManage}
                  onChange={(e) => setLevel(share, Number(e.target.value) as TShareLevel)}
                >
                  {LEVELS.map((level) => (
                    <option key={level.value} value={level.value}>
                      {t(level.i18n)}
                    </option>
                  ))}
                </select>
                {canManage && (
                  <button
                    type="button"
                    aria-label={`${t("sharing.remove")} ${share.name ?? ""}`}
                    className="grid size-6 place-items-center rounded-sm text-tertiary hover:bg-layer-1 hover:text-primary"
                    onClick={() => removeShare(share)}
                  >
                    <X className="size-3.5" />
                  </button>
                )}
              </li>
            ))}
          </ul>

          {canManage && (
            <div className="relative">
              <button
                type="button"
                className="flex items-center gap-1.5 rounded-md border border-dashed border-strong px-2.5 py-1.5 text-body-xs-medium text-secondary hover:bg-layer-1"
                onClick={() => setIsPickerOpen((open) => !open)}
                aria-expanded={isPickerOpen}
              >
                <Plus className="size-3.5" />
                {t("sharing.add")}
              </button>
              {isPickerOpen && (
                <SharePicker
                  workspaceSlug={item.workspaceSlug}
                  existing={shares}
                  onPick={(share) => {
                    addShare(share);
                    setIsPickerOpen(false);
                  }}
                  onClose={() => setIsPickerOpen(false)}
                />
              )}
            </div>
          )}
        </>
      )}

      <p className="flex items-start gap-1.5 rounded-md bg-layer-1 p-2.5 text-caption-md-regular text-secondary">
        <Lock className="mt-0.5 size-3 flex-shrink-0" />
        <span>
          {isCreator ? t("sharing.always_note_creator") : t("sharing.always_note_other")}
          {!canManage && ` ${t("sharing.read_only")}`}
        </span>
      </p>
    </div>
  );
});

type PickerProps = {
  workspaceSlug: string;
  existing: TItemShare[];
  onPick: (share: TItemShare) => void;
  onClose: () => void;
};

function SharePicker(props: PickerProps) {
  const { workspaceSlug, existing, onPick, onClose } = props;
  const { t } = useTranslation();
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  // debounce the search box
  useEffect(() => {
    const timer = setTimeout(() => setQuery(search), 200);
    return () => clearTimeout(timer);
  }, [search]);

  // close on outside click
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [onClose]);

  const { data } = useSWR(`SHARE_TARGETS_${workspaceSlug}_${query}`, () =>
    sharingService.searchTargets(workspaceSlug, query)
  );
  const taken = useMemo(() => new Set(existing.map(shareKey)), [existing]);

  const sections: { title: string; rows: TItemShare[] }[] = data
    ? [
        {
          title: t("sharing.groups"),
          rows: data.groups.map((g) => ({ target_type: "group", target_id: g.id, name: g.name, level: 5 })),
        },
        {
          title: t("sharing.departments"),
          rows: data.projects.map((p) => ({ target_type: "project", target_id: p.id, name: p.name, level: 5 })),
        },
        {
          title: t("sharing.people"),
          rows: data.people.map((p) => ({ target_type: "member", target_id: p.id, name: p.name, avatar: p.avatar, level: 5 })),
        },
        {
          title: t("sharing.everyone"),
          rows: query ? [] : [{ target_type: "workspace", target_id: null, name: t("sharing.everybody"), level: 5 }],
        },
      ]
    : [];
  const visibleSections = sections
    .map((section) => ({ ...section, rows: section.rows.filter((row) => !taken.has(shareKey(row))) }))
    .filter((section) => section.rows.length > 0);

  return (
    <div
      ref={ref}
      role="dialog"
      aria-label={t("sharing.add")}
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
      className="absolute left-0 right-0 top-full z-20 mt-1 flex max-h-80 flex-col overflow-hidden rounded-md border border-subtle bg-surface-1 shadow-raised-200"
    >
      <label className="flex items-center gap-2 border-b border-subtle px-2.5 py-2">
        <Search className="size-3.5 text-tertiary" />
        <input
          autoFocus
          className="w-full bg-transparent text-body-xs-regular text-primary outline-none placeholder:text-placeholder"
          placeholder={t("sharing.search_placeholder")}
          aria-label={t("sharing.search_placeholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </label>
      <div className="overflow-y-auto p-1">
        {data && visibleSections.length === 0 && (
          <p className="p-2.5 text-caption-md-regular text-tertiary">{t("sharing.no_results")}</p>
        )}
        {visibleSections.map((section) => (
          <div key={section.title}>
            <p className="px-2 pb-1 pt-2 text-caption-sm-medium uppercase tracking-wide text-tertiary">{section.title}</p>
            {section.rows.map((row) => (
              <button
                type="button"
                key={shareKey(row)}
                className="flex w-full items-center gap-2.5 rounded-sm px-2 py-1.5 text-left hover:bg-layer-1"
                onClick={() => onPick(row)}
              >
                <TargetBadge share={row} />
                <span className="truncate text-body-xs-medium text-primary">{row.name}</span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
