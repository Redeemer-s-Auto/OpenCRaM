/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import type { TCustomField, TCustomFieldValue } from "@plane/types";
import { cn } from "@plane/utils";
// components
import { CustomFieldValueInput } from "@/components/custom-fields/value-input";
// services
import type { TInlineViewCard, TInlineViewResult } from "@/services/inline-view.service";
// local
import type { TViewConfig } from "./types";
import { PRIORITY_OPTIONS } from "./types";

export type TCardPatch = {
  name?: string;
  state_id?: string;
  priority?: string;
  target_date?: string | null;
  custom_fields?: Record<string, unknown>;
};

export type TLayoutProps = {
  data: TInlineViewResult;
  config: TViewConfig;
  editable: boolean;
  workspaceSlug: string;
  onPatch: (card: TInlineViewCard, patch: TCardPatch) => Promise<void>;
};

const cardHref = (workspaceSlug: string, card: TInlineViewCard) =>
  `/${workspaceSlug}/browse/${card.project_identifier}-${card.sequence_id}/`;

/** Fields shown for a card: the ones the block picked, else the first few of its board. */
export const shownFields = (data: TInlineViewResult, config: TViewConfig, projectId: string): TCustomField[] => {
  const all = data.projects[projectId]?.fields ?? [];
  if (config.fields) return all.filter((field) => config.fields?.includes(field.id));
  return all.slice(0, 3);
};

/** Fields to offer in the block menu: every field of every board in the result. */
export const allFields = (data: TInlineViewResult): TCustomField[] =>
  Object.values(data.projects).flatMap((project) => project.fields);

function Name(props: {
  card: TInlineViewCard;
  workspaceSlug: string;
  editable: boolean;
  onPatch: TLayoutProps["onPatch"];
}) {
  const { card, workspaceSlug, editable, onPatch } = props;
  const [text, setText] = useState<string | null>(null);
  if (text === null)
    return (
      <span className="flex min-w-0 items-center gap-1.5">
        <a
          href={cardHref(workspaceSlug, card)}
          className="truncate text-body-xs-medium hover:underline"
          title={card.name}
        >
          {card.name || "Untitled"}
        </a>
        {editable && (
          <button
            type="button"
            className="shrink-0 text-11 text-tertiary hover:text-secondary"
            onClick={() => setText(card.name)}
            aria-label="Rename"
          >
            edit
          </button>
        )}
      </span>
    );
  const commit = () => {
    const next = text.trim();
    setText(null);
    if (next && next !== card.name) void onPatch(card, { name: next });
  };
  return (
    <input
      autoFocus
      className="w-full rounded-sm border border-subtle bg-transparent px-1.5 py-0.5 text-body-xs-regular"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") commit();
        if (e.key === "Escape") setText(null);
      }}
    />
  );
}

function StateCell(props: {
  card: TInlineViewCard;
  data: TInlineViewResult;
  editable: boolean;
  onPatch: TLayoutProps["onPatch"];
}) {
  const { card, data, editable, onPatch } = props;
  const states = data.projects[card.project_id]?.states ?? [];
  const current = states.find((s) => s.id === card.state_id);
  if (!editable) return <span className="text-body-xs-regular">{current?.name ?? ""}</span>;
  return (
    <select
      className="w-full rounded-sm bg-transparent px-1 py-0.5 text-body-xs-regular hover:bg-layer-transparent-hover"
      value={card.state_id ?? ""}
      onChange={(e) => void onPatch(card, { state_id: e.target.value })}
    >
      {states.map((s) => (
        <option key={s.id} value={s.id}>
          {s.name}
        </option>
      ))}
    </select>
  );
}

function PriorityCell(props: { card: TInlineViewCard; editable: boolean; onPatch: TLayoutProps["onPatch"] }) {
  const { card, editable, onPatch } = props;
  const value = card.priority ?? "none";
  if (!editable) return <span className="text-body-xs-regular capitalize">{value}</span>;
  return (
    <select
      className="w-full rounded-sm bg-transparent px-1 py-0.5 text-body-xs-regular hover:bg-layer-transparent-hover"
      value={value}
      onChange={(e) => void onPatch(card, { priority: e.target.value })}
    >
      {PRIORITY_OPTIONS.map((p) => (
        <option key={p.key} value={p.key}>
          {p.label}
        </option>
      ))}
    </select>
  );
}

function DueCell(props: { card: TInlineViewCard; editable: boolean; onPatch: TLayoutProps["onPatch"] }) {
  const { card, editable, onPatch } = props;
  return (
    <input
      type="date"
      disabled={!editable}
      className="w-full rounded-sm bg-transparent px-1 py-0.5 text-body-xs-regular hover:bg-layer-transparent-hover disabled:opacity-100"
      value={card.target_date ?? ""}
      onChange={(e) => void onPatch(card, { target_date: e.target.value || null })}
    />
  );
}

function FieldCell(props: {
  card: TInlineViewCard;
  field: TCustomField;
  editable: boolean;
  onPatch: TLayoutProps["onPatch"];
}) {
  const { card, field, editable, onPatch } = props;
  return (
    <CustomFieldValueInput
      field={field}
      value={card.custom_fields?.[field.id] as TCustomFieldValue | undefined}
      projectId={card.project_id}
      disabled={!editable}
      variant="cell"
      onChange={(value) => onPatch(card, { custom_fields: { [field.id]: value } })}
    />
  );
}

export function TableLayout(props: TLayoutProps) {
  const { data, config, editable, workspaceSlug, onPatch } = props;
  const projectIds = [...new Set(data.results.map((card) => card.project_id))];
  const fields = projectIds.length === 1 ? shownFields(data, config, projectIds[0]) : [];
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left">
        <thead>
          <tr className="border-b border-subtle text-11 text-tertiary uppercase">
            <th className="px-2 py-1 font-medium">Name</th>
            <th className="px-2 py-1 font-medium">State</th>
            <th className="px-2 py-1 font-medium">Priority</th>
            <th className="px-2 py-1 font-medium">Due</th>
            {fields.map((field) => (
              <th key={field.id} className="px-2 py-1 font-medium">
                {field.name}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.results.map((card) => (
            <tr key={card.id} className="border-b border-subtle last:border-0">
              <td className="max-w-[18rem] px-2 py-1">
                <Name card={card} workspaceSlug={workspaceSlug} editable={editable} onPatch={onPatch} />
              </td>
              <td className="px-2 py-1">
                <StateCell card={card} data={data} editable={editable} onPatch={onPatch} />
              </td>
              <td className="px-2 py-1">
                <PriorityCell card={card} editable={editable} onPatch={onPatch} />
              </td>
              <td className="px-2 py-1">
                <DueCell card={card} editable={editable} onPatch={onPatch} />
              </td>
              {fields.map((field) => (
                <td key={field.id} className="min-w-[8rem] px-1 py-1">
                  <FieldCell card={card} field={field} editable={editable} onPatch={onPatch} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ListLayout(props: TLayoutProps) {
  const { data, editable, workspaceSlug, onPatch } = props;
  return (
    <ul className="divide-y divide-subtle">
      {data.results.map((card) => (
        <li key={card.id} className="flex items-center gap-3 px-2 py-1.5">
          <span className="w-16 shrink-0 text-11 text-tertiary">
            {card.project_identifier}-{card.sequence_id}
          </span>
          <div className="min-w-0 flex-1">
            <Name card={card} workspaceSlug={workspaceSlug} editable={editable} onPatch={onPatch} />
          </div>
          <div className="w-32 shrink-0">
            <StateCell card={card} data={data} editable={editable} onPatch={onPatch} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function GalleryLayout(props: TLayoutProps) {
  const { data, config, editable, workspaceSlug, onPatch } = props;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {data.results.map((card) => (
        <div key={card.id} className="rounded-md border border-subtle bg-layer-1 p-3">
          <Name card={card} workspaceSlug={workspaceSlug} editable={editable} onPatch={onPatch} />
          <div className="mt-2 flex flex-col gap-1">
            <StateCell card={card} data={data} editable={editable} onPatch={onPatch} />
            {shownFields(data, config, card.project_id).map((field) => (
              <div key={field.id} className="flex items-center gap-2">
                <span className="w-20 shrink-0 truncate text-11 text-tertiary">{field.name}</span>
                <div className="min-w-0 flex-1">
                  <FieldCell card={card} field={field} editable={editable} onPatch={onPatch} />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

type TColumn = { key: string; label: string; color?: string; patch: (card: TInlineViewCard) => TCardPatch | null };

/** Board columns for the chosen grouping. Cards in none of them land in "No value". */
const boardColumns = (
  data: TInlineViewResult,
  config: TViewConfig
): { columns: TColumn[]; pick: (c: TInlineViewCard) => string } => {
  const groupBy = config.group_by ?? "state";
  if (groupBy === "priority") {
    return {
      columns: PRIORITY_OPTIONS.map((p) => ({ key: p.key, label: p.label, patch: () => ({ priority: p.key }) })),
      pick: (card) => card.priority ?? "none",
    };
  }
  const field = allFields(data).find((f) => f.id === groupBy && f.field_type === "select");
  if (field) {
    const columns: TColumn[] = [
      ...field.options.map((o) => ({
        key: o.id,
        label: o.name,
        color: o.color,
        patch: () => ({ custom_fields: { [field.id]: o.id } }),
      })),
      { key: "", label: "No value", patch: () => ({ custom_fields: { [field.id]: null } }) },
    ];
    return {
      columns,
      pick: (card) => {
        const value = card.custom_fields?.[field.id];
        const option = field.options.find((o) => o.id === value || o.name === value);
        return option?.id ?? "";
      },
    };
  }
  // By state. Boards that share a state name share a column.
  const seen = new Map<string, TColumn>();
  Object.values(data.projects).forEach((project) =>
    project.states.forEach((state) => {
      if (!seen.has(state.name))
        seen.set(state.name, {
          key: state.name,
          label: state.name,
          color: state.color,
          patch: (card) => {
            const target = data.projects[card.project_id]?.states.find((s) => s.name === state.name);
            return target ? { state_id: target.id } : null;
          },
        });
    })
  );
  return {
    columns: [...seen.values()],
    pick: (card) => data.projects[card.project_id]?.states.find((s) => s.id === card.state_id)?.name ?? "",
  };
};

export function BoardLayout(props: TLayoutProps) {
  const { data, config, editable, workspaceSlug, onPatch } = props;
  const [over, setOver] = useState<string | null>(null);
  const { columns, pick } = boardColumns(data, config);
  const known = new Set(columns.map((c) => c.key));
  const cards = (key: string) => data.results.filter((card) => (known.has(pick(card)) ? pick(card) : "") === key);
  const shown = columns.filter((c) => c.key !== "" || cards("").length > 0);
  return (
    <div className="flex snap-x snap-mandatory gap-3 overflow-x-auto pb-1 md:snap-none">
      {shown.map((column) => (
        <div
          key={column.key}
          className={cn(
            "w-64 shrink-0 snap-start rounded-md bg-layer-1 p-2",
            over === column.key && "outline-accent-primary outline outline-1"
          )}
          onDragOver={(e) => {
            if (!editable) return;
            e.preventDefault();
            setOver(column.key);
          }}
          onDragLeave={() => setOver(null)}
          onDrop={(e) => {
            setOver(null);
            const card = data.results.find((c) => c.id === e.dataTransfer.getData("text/plain"));
            if (!editable || !card || pick(card) === column.key) return;
            const patch = column.patch(card);
            if (patch) void onPatch(card, patch);
          }}
        >
          <div className="mb-2 flex items-center gap-1.5 px-1 text-body-xs-medium">
            {column.color && <span className="size-2 rounded-full" style={{ backgroundColor: column.color }} />}
            {column.label}
            <span className="text-tertiary">{cards(column.key).length}</span>
          </div>
          <div className="flex flex-col gap-2">
            {cards(column.key).map((card) => (
              <div
                key={card.id}
                draggable={editable}
                onDragStart={(e) => e.dataTransfer.setData("text/plain", card.id)}
                className="rounded-md border border-subtle bg-surface-1 p-2"
              >
                <Name card={card} workspaceSlug={workspaceSlug} editable={editable} onPatch={onPatch} />
                {shownFields(data, config, card.project_id).map((field) => (
                  <div key={field.id} className="mt-1 flex items-center gap-2">
                    <span className="w-16 shrink-0 truncate text-11 text-tertiary">{field.name}</span>
                    <div className="min-w-0 flex-1">
                      <FieldCell card={card} field={field} editable={editable} onPatch={onPatch} />
                    </div>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
