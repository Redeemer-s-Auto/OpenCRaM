/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { ArrowDown, ArrowUp, Plus, X } from "lucide-react";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TCustomField, TCustomFieldOption, TCustomFieldType } from "@plane/types";
import { Checkbox, EModalPosition, EModalWidth, Input, ModalCore } from "@plane/ui";
import { cn } from "@plane/utils";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";
// local
import { CUSTOM_FIELD_TYPES, DEFAULT_OPTION_COLORS, OPTION_FIELD_TYPES } from "../helpers";

type Props = {
  isOpen: boolean;
  onClose: () => void;
  workspaceSlug: string;
  projectId: string;
  /** Field to edit. Leave out to add a new field. */
  field?: TCustomField | null;
};

type TDraftOption = Omit<TCustomFieldOption, "id"> & { id?: string };

const errorMessage = (error: unknown) => {
  if (!error || typeof error !== "object") return "Something went wrong. Try again.";
  const values = Object.values(error as Record<string, unknown>).flat();
  const first = values.find((v) => typeof v === "string");
  return (first as string) ?? "Something went wrong. Try again.";
};

export const CustomFieldFormModal = observer(function CustomFieldFormModal(props: Props) {
  const { isOpen, onClose, workspaceSlug, projectId, field } = props;
  const { createField, updateField } = useCustomField();
  const isEdit = !!field;

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [fieldType, setFieldType] = useState<TCustomFieldType>("text");
  const [options, setOptions] = useState<TDraftOption[]>([]);
  const [includeTime, setIncludeTime] = useState(false);
  const [multiple, setMultiple] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    setName(field?.name ?? "");
    setDescription(field?.description ?? "");
    setFieldType(field?.field_type ?? "text");
    setOptions(field?.options ?? []);
    setIncludeTime(!!field?.settings?.include_time);
    setMultiple(!!field?.settings?.multiple);
  }, [isOpen, field]);

  const hasOptions = OPTION_FIELD_TYPES.includes(fieldType);
  const removedOptions = isEdit ? (field?.options ?? []).filter((o) => !options.some((d) => d.id === o.id)) : [];

  const moveOption = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= options.length) return;
    const next = [...options];
    [next[index], next[target]] = [next[target], next[index]];
    setOptions(next);
  };

  const handleSubmit = async () => {
    if (!name.trim()) {
      setToast({ type: TOAST_TYPE.ERROR, title: "Name needed", message: "Give the field a name." });
      return;
    }
    if (fieldType === "select" || fieldType === "multi_select") {
      if (!options.some((o) => o.name.trim())) {
        setToast({ type: TOAST_TYPE.ERROR, title: "Options needed", message: "Add at least one option." });
        return;
      }
    }
    const settings: TCustomField["settings"] = {};
    if (fieldType === "date") settings.include_time = includeTime;
    if (fieldType === "person") settings.multiple = multiple;
    const payload: Partial<TCustomField> = {
      name: name.trim(),
      description: description.trim(),
      settings,
      ...(hasOptions
        ? { options: options.filter((o) => o.name.trim()).map((o) => ({ ...o, name: o.name.trim() })) as TCustomFieldOption[] }
        : {}),
    };
    setSaving(true);
    try {
      if (isEdit && field) await updateField(workspaceSlug, projectId, field.id, payload);
      else await createField(workspaceSlug, projectId, { ...payload, field_type: fieldType });
      setToast({ type: TOAST_TYPE.SUCCESS, title: isEdit ? "Field saved" : "Field added", message: name.trim() });
      onClose();
    } catch (error) {
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not save the field", message: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.TOP} width={EModalWidth.XL}>
      <div className="flex flex-col gap-4 p-5">
        <h3 className="text-h5-medium text-primary">{isEdit ? "Edit field" : "Add a field"}</h3>

        <label className="flex flex-col gap-1">
          <span className="text-body-xs-medium text-secondary">Name</span>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="For example: Call-back date"
            maxLength={255}
            autoFocus
          />
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-body-xs-medium text-secondary">Description (optional)</span>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What goes here" />
        </label>

        <div className="flex flex-col gap-1">
          <span className="text-body-xs-medium text-secondary">Type</span>
          {isEdit ? (
            <p className="text-body-xs-regular text-tertiary">
              {CUSTOM_FIELD_TYPES.find((t) => t.type === fieldType)?.label}. The type cannot change after a field is
              made.
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {CUSTOM_FIELD_TYPES.map((type) => (
                <button
                  key={type.type}
                  type="button"
                  onClick={() => setFieldType(type.type)}
                  title={type.hint}
                  className={cn(
                    "flex items-center gap-2 rounded-md border px-2 py-1.5 text-left text-body-xs-regular",
                    fieldType === type.type
                      ? "border-accent-strong bg-accent-subtle text-primary"
                      : "border-subtle text-secondary hover:bg-layer-1"
                  )}
                >
                  <type.icon className="size-4 shrink-0" />
                  {type.label}
                </button>
              ))}
            </div>
          )}
          <p className="text-caption-md-regular text-tertiary">
            {CUSTOM_FIELD_TYPES.find((t) => t.type === fieldType)?.hint}
          </p>
        </div>

        {fieldType === "date" && (
          <label className="flex items-center gap-2 text-body-xs-regular text-secondary">
            <Checkbox checked={includeTime} onChange={(e) => setIncludeTime(e.target.checked)} />
            Also store a time
          </label>
        )}

        {fieldType === "person" && (
          <label className="flex items-center gap-2 text-body-xs-regular text-secondary">
            <Checkbox checked={multiple} onChange={(e) => setMultiple(e.target.checked)} />
            Allow more than one person
          </label>
        )}

        {hasOptions && (
          <div className="flex flex-col gap-2">
            <span className="text-body-xs-medium text-secondary">
              {fieldType === "label" ? "Starting tags (people can add more on a card)" : "Options"}
            </span>
            {options.map((option, index) => (
              <div key={option.id ?? `new-${index}`} className="flex items-center gap-2">
                <input
                  type="color"
                  value={option.color || DEFAULT_OPTION_COLORS[index % DEFAULT_OPTION_COLORS.length]}
                  onChange={(e) =>
                    setOptions(options.map((o, i) => (i === index ? { ...o, color: e.target.value } : o)))
                  }
                  className="size-6 shrink-0 cursor-pointer rounded-sm border border-subtle bg-transparent"
                  aria-label="Option color"
                />
                <Input
                  value={option.name}
                  onChange={(e) => setOptions(options.map((o, i) => (i === index ? { ...o, name: e.target.value } : o)))}
                  placeholder={`Option ${index + 1}`}
                  className="grow"
                />
                <button type="button" onClick={() => moveOption(index, -1)} aria-label="Move up" className="text-tertiary hover:text-primary">
                  <ArrowUp className="size-3.5" />
                </button>
                <button type="button" onClick={() => moveOption(index, 1)} aria-label="Move down" className="text-tertiary hover:text-primary">
                  <ArrowDown className="size-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => setOptions(options.filter((_, i) => i !== index))}
                  aria-label="Remove option"
                  className="text-tertiary hover:text-danger-primary"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            ))}
            <Button
              variant="ghost"
              size="base"
              prependIcon={<Plus />}
              className="self-start"
              onClick={() =>
                setOptions([
                  ...options,
                  { name: "", color: DEFAULT_OPTION_COLORS[options.length % DEFAULT_OPTION_COLORS.length] },
                ])
              }
            >
              Add option
            </Button>
            {removedOptions.length > 0 && (
              <p className="rounded-md bg-danger-subtle px-2 py-1.5 text-caption-md-regular text-danger-secondary">
                Saving removes {removedOptions.map((o) => `"${o.name}"`).join(", ")}. Cards that use{" "}
                {removedOptions.length > 1 ? "these options" : "this option"} lose that value.
              </p>
            )}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" size="lg" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="lg" loading={saving} onClick={handleSubmit}>
            {isEdit ? "Save" : "Add field"}
          </Button>
        </div>
      </div>
    </ModalCore>
  );
});
