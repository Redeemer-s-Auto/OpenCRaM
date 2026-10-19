/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { ExternalLink } from "lucide-react";
import type { TCustomField, TCustomFieldValue } from "@plane/types";
import { Checkbox, CustomSearchSelect, Input, TextArea } from "@plane/ui";
import { cn, renderFormattedPayloadDate } from "@plane/utils";
// components
import { DateDropdown } from "@/components/dropdowns/date";
import { MemberDropdown } from "@/components/dropdowns/member/dropdown";
// local
import { formatCustomFieldValue, formatMoney, parseMoney, parseNumber, toLocalDateTimeInput } from "./helpers";
import { RelationInput } from "./relation-input";

/** A new label typed on a card. The server turns it into an option. */
export type TNewLabel = { name: string };
export type TCustomFieldInputValue = TCustomFieldValue | (string | TNewLabel)[];

type Props = {
  field: TCustomField;
  value: TCustomFieldValue | undefined;
  onChange: (value: TCustomFieldInputValue) => void | Promise<void>;
  projectId: string;
  disabled?: boolean;
  /** "sidebar" for the card panel, "cell" for the table */
  variant?: "sidebar" | "cell";
};

const textClass = "text-body-xs-regular";

/** Text box that saves on blur or Enter and reverts on Escape. */
function CommitInput(props: {
  initial: string;
  placeholder: string;
  disabled?: boolean;
  inputMode?: "text" | "decimal" | "url";
  validate?: (text: string) => boolean;
  onCommit: (text: string) => void;
  className?: string;
}) {
  const { initial, placeholder, disabled, inputMode = "text", validate, onCommit, className } = props;
  const [text, setText] = useState(initial);
  const [invalid, setInvalid] = useState(false);
  useEffect(() => setText(initial), [initial]);

  const commit = () => {
    if (text === initial) return setInvalid(false);
    if (validate && !validate(text)) return setInvalid(true);
    setInvalid(false);
    onCommit(text);
  };

  return (
    <Input
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") {
          setText(initial);
          setInvalid(false);
        }
      }}
      inputMode={inputMode === "url" ? "url" : inputMode}
      placeholder={placeholder}
      disabled={disabled}
      hasError={invalid}
      mode="true-transparent"
      className={cn("w-full rounded-sm px-2 py-1 hover:bg-layer-transparent-hover", textClass, className)}
    />
  );
}

export const CustomFieldValueInput = observer(function CustomFieldValueInput(props: Props) {
  const { field, value, onChange, projectId, disabled = false, variant = "sidebar" } = props;
  const placeholder = variant === "cell" ? "" : `Add ${field.name.toLowerCase()}`;
  const buttonContainerClassName = variant === "cell" ? "w-full h-full text-left" : "w-full text-left h-7.5";
  const [newLabel, setNewLabel] = useState("");

  if (field.field_type === "relation") {
    return (
      <RelationInput
        field={field}
        value={value}
        onChange={(cards) => onChange(cards)}
        projectId={projectId}
        disabled={disabled}
        variant={variant}
      />
    );
  }

  // Formulas and rollups are worked out by the server: show the result, no editing.
  if (field.field_type === "formula" || field.field_type === "rollup") {
    const text = formatCustomFieldValue(field, value);
    return (
      <span
        className={cn("block w-full truncate px-2 py-1", textClass, !text && "text-placeholder")}
        title={field.field_type === "formula" ? field.settings?.expression : text}
      >
        {text || (variant === "cell" ? "" : "Empty")}
      </span>
    );
  }

  switch (field.field_type) {
    case "text":
      return (
        <CommitInput
          initial={(value as string) ?? ""}
          placeholder={placeholder}
          disabled={disabled}
          onCommit={(text) => onChange(text.trim() === "" ? null : text)}
        />
      );

    case "long_text":
      return (
        <TextArea
          defaultValue={(value as string) ?? ""}
          key={(value as string) ?? ""}
          placeholder={placeholder}
          disabled={disabled}
          mode="true-transparent"
          rows={variant === "cell" ? 1 : 3}
          onBlur={(e) => {
            const text = e.target.value;
            if (text !== ((value as string) ?? "")) onChange(text.trim() === "" ? null : text);
          }}
          className={cn("w-full rounded-sm px-2 py-1 hover:bg-layer-transparent-hover", textClass)}
        />
      );

    case "number":
      return (
        <CommitInput
          initial={value === null || value === undefined ? "" : String(value)}
          placeholder={placeholder}
          disabled={disabled}
          inputMode="decimal"
          validate={(text) => parseNumber(text) !== undefined}
          onCommit={(text) => onChange(parseNumber(text) ?? null)}
        />
      );

    case "money":
      return (
        <CommitInput
          initial={formatMoney(value as number | null)}
          placeholder={variant === "cell" ? "" : "$0.00"}
          disabled={disabled}
          inputMode="decimal"
          validate={(text) => parseMoney(text) !== undefined}
          onCommit={(text) => onChange(parseMoney(text) ?? null)}
        />
      );

    case "url":
      return (
        <div className="flex w-full items-center gap-1">
          <CommitInput
            initial={(value as string) ?? ""}
            placeholder={variant === "cell" ? "" : "https://"}
            disabled={disabled}
            inputMode="url"
            onCommit={(text) => onChange(text.trim() === "" ? null : text.trim())}
          />
          {typeof value === "string" && value && (
            <a
              href={value}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0 text-tertiary hover:text-primary"
              aria-label="Open link"
            >
              <ExternalLink className="size-3.5" />
            </a>
          )}
        </div>
      );

    case "checkbox":
      return (
        <div className="flex h-7.5 items-center px-2">
          <Checkbox
            checked={value === true}
            disabled={disabled}
            onChange={(e) => onChange(e.target.checked)}
            aria-label={field.name}
          />
        </div>
      );

    case "date":
      if (field.settings?.include_time) {
        return (
          <input
            type="datetime-local"
            value={toLocalDateTimeInput(value as string)}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value ? new Date(e.target.value).toISOString() : null)}
            className={cn(
              "w-full rounded-sm bg-transparent px-2 py-1 hover:bg-layer-transparent-hover",
              textClass,
              !value && "text-placeholder"
            )}
          />
        );
      }
      return (
        <DateDropdown
          value={(value as string) ?? null}
          onChange={(date) => onChange(date ? renderFormattedPayloadDate(date) ?? null : null)}
          placeholder={placeholder}
          disabled={disabled}
          buttonVariant="transparent-with-text"
          className="group w-full grow"
          buttonContainerClassName={buttonContainerClassName}
          buttonClassName={cn(textClass, !value && "text-placeholder")}
          hideIcon
          clearIconClassName="h-3 w-3 hidden group-hover:inline"
        />
      );

    case "select": {
      const options = field.options.map((o) => ({
        value: o.id,
        query: o.name,
        content: <OptionChip name={o.name} color={o.color} />,
      }));
      return (
        <CustomSearchSelect
          value={(value as string) ?? null}
          onChange={(next: string | null) => onChange(next === value ? null : next)}
          options={options}
          disabled={disabled}
          label={
            value ? (
              <OptionChip
                name={field.options.find((o) => o.id === value)?.name ?? ""}
                color={field.options.find((o) => o.id === value)?.color ?? ""}
              />
            ) : (
              <span className="text-placeholder">{placeholder}</span>
            )
          }
          className="w-full"
          buttonClassName={cn("w-full justify-between border-none px-2", textClass)}
          noChevron={variant === "cell"}
        />
      );
    }

    case "multi_select":
    case "label": {
      const selected = (Array.isArray(value) ? value : []) as string[];
      const options = field.options.map((o) => ({
        value: o.id,
        query: o.name,
        content: <OptionChip name={o.name} color={o.color} />,
      }));
      const addLabel = () => {
        const name = newLabel.trim();
        if (!name) return;
        setNewLabel("");
        const existing = field.options.find((o) => o.name.toLowerCase() === name.toLowerCase());
        if (existing) {
          if (!selected.includes(existing.id)) onChange([...selected, existing.id]);
          return;
        }
        onChange([...selected, { name }]);
      };
      return (
        <div className="flex w-full flex-col gap-1">
          <CustomSearchSelect
            value={selected}
            onChange={(next: string[]) => onChange(next)}
            options={options}
            multiple
            disabled={disabled}
            label={
              selected.length ? (
                <span className="flex flex-wrap gap-1">
                  {selected.map((id) => {
                    const option = field.options.find((o) => o.id === id);
                    return option ? <OptionChip key={id} name={option.name} color={option.color} /> : null;
                  })}
                </span>
              ) : (
                <span className="text-placeholder">{placeholder}</span>
              )
            }
            className="w-full"
            buttonClassName={cn("w-full justify-between border-none px-2", textClass)}
            noChevron={variant === "cell"}
          />
          {field.field_type === "label" && variant === "sidebar" && !disabled && (
            <Input
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addLabel();
                }
              }}
              onBlur={addLabel}
              placeholder="New tag, then Enter"
              mode="true-transparent"
              className={cn("w-full rounded-sm px-2 py-1 hover:bg-layer-transparent-hover", textClass)}
            />
          )}
        </div>
      );
    }

    case "person": {
      const ids = (Array.isArray(value) ? value : []) as string[];
      if (field.settings?.multiple) {
        return (
          <MemberDropdown
            value={ids}
            onChange={(next) => onChange(next)}
            projectId={projectId}
            multiple
            disabled={disabled}
            placeholder={placeholder}
            buttonVariant={ids.length > 1 ? "transparent-without-text" : "transparent-with-text"}
            className="group w-full grow"
            buttonContainerClassName={buttonContainerClassName}
            buttonClassName={cn(textClass, "justify-between", !ids.length && "text-placeholder")}
            hideIcon={ids.length === 0}
          />
        );
      }
      return (
        <MemberDropdown
          value={ids[0] ?? null}
          onChange={(next) => onChange(next ? [next] : null)}
          projectId={projectId}
          multiple={false}
          disabled={disabled}
          placeholder={placeholder}
          buttonVariant="transparent-with-text"
          className="group w-full grow"
          buttonContainerClassName={buttonContainerClassName}
          buttonClassName={cn(textClass, "justify-between", !ids.length && "text-placeholder")}
          hideIcon={ids.length === 0}
        />
      );
    }

    default:
      return <span className={textClass}>{formatCustomFieldValue(field, value)}</span>;
  }
});

export function OptionChip(props: { name: string; color: string }) {
  const { name, color } = props;
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 truncate rounded-sm border border-subtle px-1.5 py-0.5">
      <span
        className="size-2 shrink-0 rounded-full"
        style={{ backgroundColor: color || "var(--color-text-tertiary, #9ca3af)" }}
      />
      <span className="truncate">{name}</span>
    </span>
  );
}
