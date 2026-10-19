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
import type { TCustomField, TCustomFieldOption, TCustomFieldRollupFunction, TCustomFieldType } from "@plane/types";
import { Checkbox, EModalPosition, EModalWidth, Input, ModalCore } from "@plane/ui";
import { cn } from "@plane/utils";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";
import { useProject } from "@/hooks/store/use-project";
// local
import {
  CUSTOM_FIELD_TYPES,
  DEFAULT_OPTION_COLORS,
  FORMULA_RESULT_TYPES,
  OPTION_FIELD_TYPES,
  ROLLUP_BUILT_INS,
  ROLLUP_FUNCTIONS,
  fitsRollup,
  isLinkedField,
} from "../helpers";

const BUILT_IN_PROPS = ["Title", "State", "Priority", "Start date", "Due date", "Created"];
const FORMULA_EXAMPLES = [
  'prop("Amount") * 1.0825',
  'if(prop("Approved"), "Yes", "No")',
  'dateAdd(prop("Call-back"), 7, "days")',
  'concat(prop("Year"), " ", prop("Make"), " ", prop("Model"))',
];

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
  const { createField, updateField, getProjectFields, fetchProjectFields } = useCustomField();
  const { joinedProjectIds, getProjectById } = useProject();
  const otherFields = (getProjectFields(projectId) ?? []).filter((f) => f.id !== field?.id);
  const isEdit = !!field;

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [fieldType, setFieldType] = useState<TCustomFieldType>("text");
  const [options, setOptions] = useState<TDraftOption[]>([]);
  const [includeTime, setIncludeTime] = useState(false);
  const [multiple, setMultiple] = useState(false);
  const [expression, setExpression] = useState("");
  const [resultType, setResultType] = useState<NonNullable<TCustomField["settings"]["result_type"]>>("number");
  const [saving, setSaving] = useState(false);
  // relation
  const [targetProjectId, setTargetProjectId] = useState("");
  const [twoWay, setTwoWay] = useState(false);
  const [mirrorName, setMirrorName] = useState("");
  // rollup
  const [relationFieldId, setRelationFieldId] = useState("");
  const [rollupFunction, setRollupFunction] = useState<TCustomFieldRollupFunction>("count");
  const [targetFieldId, setTargetFieldId] = useState("");

  useEffect(() => {
    if (!isOpen) return;
    setName(field?.name ?? "");
    setDescription(field?.description ?? "");
    setFieldType(field?.field_type ?? "text");
    setOptions(field?.options ?? []);
    setIncludeTime(!!field?.settings?.include_time);
    setMultiple(!!field?.settings?.multiple);
    setExpression(field?.settings?.expression ?? "");
    setResultType(field?.settings?.result_type ?? "number");
    setTargetProjectId(field?.settings?.target_project_id ?? "");
    setTwoWay(!!field?.settings?.two_way);
    setMirrorName("");
    setRelationFieldId(field?.settings?.relation_field_id ?? "");
    setRollupFunction(field?.settings?.function ?? "count");
    setTargetFieldId(field?.settings?.target_field_id ?? "");
  }, [isOpen, field]);

  const isMirror = !!field?.settings?.is_mirror;
  const relationFields = otherFields.filter((f) => f.field_type === "relation");
  const rollupRelation = relationFields.find((f) => f.id === relationFieldId);
  const rollupBoardId = rollupRelation?.settings?.target_project_id;
  const rollupNeeds = ROLLUP_FUNCTIONS.find((f) => f.value === rollupFunction)?.needs ?? "none";
  const rollupBoardFields = rollupBoardId ? getProjectFields(rollupBoardId) : undefined;
  // Fields on the linked board, for the rollup property picker.
  useEffect(() => {
    if (isOpen && fieldType === "rollup" && rollupBoardId && !rollupBoardFields)
      void fetchProjectFields(workspaceSlug, rollupBoardId).catch(() => undefined);
  }, [isOpen, fieldType, rollupBoardId, rollupBoardFields, workspaceSlug, fetchProjectFields]);
  const rollupTargets = [
    ...ROLLUP_BUILT_INS.filter((b) => rollupNeeds === "any" || (rollupNeeds === "date" && b.kind === "date")).map(
      (b) => ({ value: b.value, label: b.label })
    ),
    ...(rollupBoardFields ?? [])
      .filter((f) => fitsRollup(f, rollupNeeds))
      .map((f) => ({ value: f.id, label: f.name })),
  ];

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
    if (fieldType === "formula") {
      if (!expression.trim()) {
        setToast({ type: TOAST_TYPE.ERROR, title: "Formula needed", message: "Type a formula." });
        return;
      }
      settings.expression = expression.trim();
      settings.result_type = resultType;
    }
    if (fieldType === "relation") {
      if (!targetProjectId) {
        setToast({ type: TOAST_TYPE.ERROR, title: "Board needed", message: "Pick the board to link to." });
        return;
      }
      if (!isEdit) settings.target_project_id = targetProjectId;
      settings.two_way = isMirror ? true : twoWay;
      if (twoWay && mirrorName.trim()) settings.mirror_name = mirrorName.trim();
    }
    if (fieldType === "rollup") {
      if (!relationFieldId) {
        setToast({ type: TOAST_TYPE.ERROR, title: "Relation needed", message: "Pick a relation field." });
        return;
      }
      if (rollupNeeds !== "none" && !targetFieldId) {
        setToast({ type: TOAST_TYPE.ERROR, title: "Property needed", message: "Pick what to roll up." });
        return;
      }
      settings.relation_field_id = relationFieldId;
      settings.function = rollupFunction;
      settings.target_field_id = rollupNeeds === "none" ? null : targetFieldId;
    }
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
      // A two-way relation adds (or removes) a field on the other board.
      if (fieldType === "relation" && targetProjectId && targetProjectId !== projectId)
        await fetchProjectFields(workspaceSlug, targetProjectId).catch(() => undefined);
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

        {fieldType === "formula" && (
          <div className="flex flex-col gap-2">
            <span className="text-body-xs-medium text-secondary">Formula</span>
            <textarea
              value={expression}
              onChange={(e) => setExpression(e.target.value)}
              rows={3}
              spellCheck={false}
              placeholder='prop("Amount") * 1.0825'
              className="w-full rounded-md border border-subtle bg-transparent px-2 py-1.5 font-mono text-body-xs-regular"
            />
            <div className="flex flex-wrap items-center gap-1 text-caption-md-regular">
              <span className="text-tertiary">Insert:</span>
              {[...otherFields.filter((f) => !isLinkedField(f)).map((f) => f.name), ...BUILT_IN_PROPS].map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => setExpression((prev) => `${prev}prop("${name}")`)}
                  className="rounded-sm border border-subtle px-1.5 py-0.5 text-secondary hover:bg-layer-1"
                >
                  {name}
                </button>
              ))}
            </div>
            <label className="flex items-center gap-2 text-body-xs-regular text-secondary">
              Result shows as
              <select
                value={resultType}
                onChange={(e) => setResultType(e.target.value as typeof resultType)}
                className="rounded-md border border-subtle bg-transparent px-2 py-1 text-body-xs-regular"
              >
                {FORMULA_RESULT_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </select>
            </label>
            <details className="text-caption-md-regular text-tertiary">
              <summary className="cursor-pointer">Examples and functions</summary>
              <ul className="mt-1 list-disc pl-4 font-mono">
                {FORMULA_EXAMPLES.map((example) => (
                  <li key={example}>
                    <button type="button" className="text-left hover:text-primary" onClick={() => setExpression(example)}>
                      {example}
                    </button>
                  </li>
                ))}
              </ul>
              <p className="mt-1">
                Math: + - * / %, round, floor, ceil, abs, min, max, sum. Logic: if, and, or, not, empty, ==, !=, &gt;,
                &lt;. Text: concat, contains, length, upper, lower, format. Dates: dateAdd, dateSubtract, dateBetween,
                year, month, day (units: days, weeks, months, years, hours, minutes). Money fields count in dollars.
              </p>
            </details>
          </div>
        )}

        {fieldType === "relation" && (
          <div className="flex flex-col gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-body-xs-medium text-secondary">Links to cards on</span>
              {isEdit ? (
                <p className="text-body-xs-regular text-tertiary">
                  {getProjectById(targetProjectId)?.name ?? "A board you are not on"}. The board cannot change after a
                  relation is made.
                </p>
              ) : (
                <select
                  value={targetProjectId}
                  onChange={(e) => setTargetProjectId(e.target.value)}
                  className="rounded-md border border-subtle bg-transparent px-2 py-1.5 text-body-xs-regular"
                >
                  <option value="">Pick a board</option>
                  {joinedProjectIds.map((id) => (
                    <option key={id} value={id}>
                      {getProjectById(id)?.name}
                      {id === projectId ? " (this board)" : ""}
                    </option>
                  ))}
                </select>
              )}
            </label>
            {isMirror ? (
              <p className="text-caption-md-regular text-tertiary">
                This is the other side of a two-way relation. Links made here show on the other board too.
              </p>
            ) : (
              <label className="flex items-center gap-2 text-body-xs-regular text-secondary">
                <Checkbox checked={twoWay} onChange={(e) => setTwoWay(e.target.checked)} />
                Two-way: also show the links on the other board
              </label>
            )}
            {twoWay && !isMirror && !field?.settings?.mirror_field_id && (
              <label className="flex flex-col gap-1">
                <span className="text-body-xs-medium text-secondary">
                  Name of the field on the other board (optional)
                </span>
                <Input
                  value={mirrorName}
                  onChange={(e) => setMirrorName(e.target.value)}
                  placeholder="Uses this board's name"
                  maxLength={255}
                />
              </label>
            )}
            {isEdit && !isMirror && field?.settings?.two_way && !twoWay && (
              <p className="rounded-md bg-danger-subtle px-2 py-1.5 text-caption-md-regular text-danger-secondary">
                Saving removes the field on the other board. The links stay on this side.
              </p>
            )}
          </div>
        )}

        {fieldType === "rollup" && (
          <div className="flex flex-col gap-2">
            <label className="flex flex-col gap-1">
              <span className="text-body-xs-medium text-secondary">Relation</span>
              <select
                value={relationFieldId}
                onChange={(e) => {
                  setRelationFieldId(e.target.value);
                  setTargetFieldId("");
                }}
                className="rounded-md border border-subtle bg-transparent px-2 py-1.5 text-body-xs-regular"
              >
                <option value="">{relationFields.length ? "Pick a relation field" : "Add a relation field first"}</option>
                {relationFields.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-body-xs-medium text-secondary">Calculate</span>
              <select
                value={rollupFunction}
                onChange={(e) => {
                  setRollupFunction(e.target.value as TCustomFieldRollupFunction);
                  setTargetFieldId("");
                }}
                className="rounded-md border border-subtle bg-transparent px-2 py-1.5 text-body-xs-regular"
              >
                {ROLLUP_FUNCTIONS.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>
            </label>
            {rollupNeeds !== "none" && (
              <label className="flex flex-col gap-1">
                <span className="text-body-xs-medium text-secondary">Of this property on the linked cards</span>
                <select
                  value={targetFieldId}
                  onChange={(e) => setTargetFieldId(e.target.value)}
                  disabled={!rollupRelation}
                  className="rounded-md border border-subtle bg-transparent px-2 py-1.5 text-body-xs-regular"
                >
                  <option value="">{rollupTargets.length ? "Pick a property" : "No property fits"}</option>
                  {rollupTargets.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <p className="text-caption-md-regular text-tertiary">
              Worked out for each person from the linked cards they can see.
            </p>
          </div>
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
