/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { ExternalLink, Mail, Phone } from "lucide-react";
import type { TCustomField, TCustomFieldValue } from "@plane/types";
import { Checkbox, CustomSearchSelect, Input, TextArea } from "@plane/ui";
import { cn, renderFormattedPayloadDate } from "@plane/utils";
// components
import { DateDropdown } from "@/components/dropdowns/date";
import { MemberDropdown } from "@/components/dropdowns/member/dropdown";
// local
import { AuditValue } from "./audit-value";
import {
  formatCustomFieldValue,
  formatMoney,
  isAuditField,
  parseMoney,
  parseNumber,
  toLocalDateTimeInput,
} from "./helpers";
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

// Same rules as the server, loosely: the server has the final say.
const PHONE_PATTERN = /^\+?[\d\s().-]{7,}(?:\s*(?:x|ext\.?|#)\s*\d{1,8})?$/i;
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Text box that saves on blur or Enter and reverts on Escape. */
function CommitInput(props: {
  initial: string;
  placeholder: string;
  disabled?: boolean;
  inputMode?: "text" | "decimal" | "url" | "tel" | "email";
  /** shown after the text when the box is not being typed in, like a % sign */
  suffix?: string;
  validate?: (text: string) => boolean;
  onCommit: (text: string) => void;
  className?: string;
}) {
  const { initial, placeholder, disabled, inputMode = "text", validate, onCommit, className, suffix } = props;
  const [text, setText] = useState(initial);
  const [invalid, setInvalid] = useState(false);
  useEffect(() => setText(initial), [initial]);

  const commit = () => {
    if (text === initial) return setInvalid(false);
    if (validate && !validate(text)) return setInvalid(true);
    setInvalid(false);
    onCommit(text);
  };

  const input = (
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
  if (!suffix) return input;
  return (
    <div className="flex w-full items-center">
      {input}
      {text !== "" && <span className={cn("shrink-0 pr-2 text-tertiary", textClass)}>{suffix}</span>}
    </div>
  );
}

/**
 * A multi-line text box. The shared TextArea is always controlled (it shows its own empty value when
 * none is passed), so the text is held here and saved when the box loses focus.
 */
function LongTextInput(props: {
  initial: string;
  placeholder: string;
  disabled: boolean;
  rows: number;
  className?: string;
  onCommit: (text: string) => void;
}) {
  const { initial, placeholder, disabled, rows, className, onCommit } = props;
  const [text, setText] = useState(initial);
  useEffect(() => setText(initial), [initial]);
  return (
    <TextArea
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => {
        if (text !== initial) onCommit(text);
      }}
      placeholder={placeholder}
      disabled={disabled}
      mode="true-transparent"
      rows={rows}
      className={className}
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

  // Created / last edited fields come from the card: show them, no editing.
  if (isAuditField(field)) return <AuditValue field={field} value={value} variant={variant} />;

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
    case "text": {
      const format = field.settings?.format;
      if (format === "phone" || format === "email") {
        const text = typeof value === "string" ? value : "";
        return (
          <div className="flex w-full items-center gap-1">
            <CommitInput
              initial={text}
              placeholder={variant === "cell" ? "" : format === "phone" ? "(512) 555-0134" : "name@example.com"}
              disabled={disabled}
              inputMode={format === "phone" ? "tel" : "email"}
              validate={(entered) => entered.trim() === "" || (format === "phone" ? PHONE_PATTERN : EMAIL_PATTERN).test(entered.trim())}
              onCommit={(entered) => onChange(entered.trim() === "" ? null : entered.trim())}
            />
            {text && (
              <a
                href={format === "phone" ? `tel:${text.replace(/[^\d+]/g, "")}` : `mailto:${text}`}
                className="shrink-0 text-tertiary hover:text-primary"
                aria-label={format === "phone" ? "Call" : "Write an email"}
              >
                {format === "phone" ? <Phone className="size-3.5" /> : <Mail className="size-3.5" />}
              </a>
            )}
          </div>
        );
      }
      return (
        <CommitInput
          initial={(value as string) ?? ""}
          placeholder={placeholder}
          disabled={disabled}
          onCommit={(text) => onChange(text.trim() === "" ? null : text)}
        />
      );
    }

    case "long_text":
      return (
        <LongTextInput
          initial={(value as string) ?? ""}
          placeholder={placeholder}
          disabled={disabled}
          rows={variant === "cell" ? 1 : 3}
          onCommit={(text) => onChange(text.trim() === "" ? null : text)}
          className={cn("w-full rounded-sm px-2 py-1 hover:bg-layer-transparent-hover", textClass)}
        />
      );

    case "number":
      return (
        <CommitInput
          initial={value === null || value === undefined ? "" : String(value)}
          placeholder={field.settings?.format === "percent" && variant !== "cell" ? "0%" : placeholder}
          suffix={field.settings?.format === "percent" ? "%" : undefined}
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
      // The whole label is the tap target (a table cell fills its cell), not just the 16px box.
      return (
        <label
          className={cn(
            "flex items-center px-2",
            variant === "cell" ? "h-full min-h-10 w-full" : "h-7.5 min-w-10",
            disabled ? "cursor-default" : "cursor-pointer"
          )}
        >
          <Checkbox
            checked={value === true}
            disabled={disabled}
            onChange={(e) => onChange(e.target.checked)}
            aria-label={field.name}
          />
        </label>
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
