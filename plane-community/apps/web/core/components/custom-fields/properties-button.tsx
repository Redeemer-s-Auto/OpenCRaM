/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { ArrowDown, ArrowUp, Eye, EyeOff, ListChecks, Plus, Settings } from "lucide-react";
import { EUserPermissions, EUserPermissionsLevel, ISSUE_DISPLAY_PROPERTIES } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { IIssueDisplayProperties, TCustomField } from "@plane/types";
import { EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
import { cn } from "@plane/utils";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";
import { useUserPermissions } from "@/hooks/store/user";
// local
import { CARD_FACE_LAYOUTS, cardFaceDisplayKey, isCustomFieldOnCardFace } from "./card-face-fields";
import { getFieldDetails, isSeenField } from "./helpers";
import { CustomFieldFormModal } from "./settings/field-form-modal";
import { customFieldDisplayKey, isCustomFieldColumnShown } from "./spreadsheet-columns";

type Props = {
  workspaceSlug: string;
  projectId: string;
  /** Current layout; decides which show/hide key a custom field uses (card face or table column). */
  layout: string | undefined;
  displayProperties: IIssueDisplayProperties;
  /** Built-in properties the current layout offers (layoutDisplayFiltersOptions.display_properties). */
  displayPropertiesToRender?: (keyof IIssueDisplayProperties)[];
  handleUpdate: (updatedDisplayProperties: Partial<IIssueDisplayProperties>) => void;
  cycleViewDisabled?: boolean;
  moduleViewDisabled?: boolean;
  /** "header" for the board header (text hides on narrow widths), "mobile" for the phone bar. */
  variant?: "header" | "mobile";
};

const errorMessage = (error: unknown) => {
  if (!error || typeof error !== "object") return "Something went wrong. Try again.";
  const values = Object.values(error as Record<string, unknown>).flat();
  const first = values.find((v) => typeof v === "string");
  return (first as string) ?? "Something went wrong. Try again.";
};

/**
 * "Properties" in the board header: one list of every property of the board, built-in and custom,
 * to show or hide on the list, rename, reorder and add. Show/hide writes the same display
 * properties as the Display dropdown, so the two stay in sync.
 */
export const PropertiesButton = observer(function PropertiesButton(props: Props) {
  const { workspaceSlug, projectId, variant = "header" } = props;
  const [open, setOpen] = useState(false);
  if (!workspaceSlug || !projectId) return null;

  return (
    <>
      <PropertiesModal {...props} isOpen={open} onClose={() => setOpen(false)} />
      {variant === "mobile" ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Properties"
          title="Properties"
          className="flex min-h-11 min-w-11 items-center justify-center border-l border-subtle text-secondary"
        >
          <ListChecks className="size-4" />
        </button>
      ) : (
        <Button variant="secondary" size="lg" onClick={() => setOpen(true)} aria-label="Properties" title="Properties">
          <ListChecks className="size-3.5" />
          <span className="hidden @4xl:inline">Properties</span>
        </Button>
      )}
    </>
  );
});

const PropertiesModal = observer(function PropertiesModal(props: Props & { isOpen: boolean; onClose: () => void }) {
  const {
    isOpen,
    onClose,
    workspaceSlug,
    projectId,
    layout,
    displayProperties,
    displayPropertiesToRender,
    handleUpdate,
    cycleViewDisabled = false,
    moduleViewDisabled = false,
  } = props;
  const { t } = useTranslation();
  const { getProjectFields, moveField } = useCustomField();
  const { allowPermissions } = useUserPermissions();
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT, workspaceSlug, projectId);
  const [addOpen, setAddOpen] = useState(false);

  const allowed = displayPropertiesToRender ?? ISSUE_DISPLAY_PROPERTIES.map((p) => p.key);
  const builtIns = ISSUE_DISPLAY_PROPERTIES.filter((p) => {
    if (!allowed.includes(p.key)) return false;
    if (p.key === "cycle") return !cycleViewDisabled;
    if (p.key === "modules") return !moduleViewDisabled;
    return true;
  });
  // Same list and order as the settings page, so move up/down matches it.
  const fields = getProjectFields(projectId) ?? [];
  const onCardFace = !!layout && CARD_FACE_LAYOUTS.includes(layout);

  const isFieldShown = (field: TCustomField) =>
    onCardFace
      ? isCustomFieldOnCardFace(displayProperties, field.id)
      : isCustomFieldColumnShown(displayProperties ?? {}, field.id);
  const toggleField = (field: TCustomField) => {
    const key = onCardFace ? cardFaceDisplayKey(field.id) : customFieldDisplayKey(field.id);
    handleUpdate({ [key]: !isFieldShown(field) });
  };

  const move = async (field: TCustomField, direction: "up" | "down") => {
    try {
      await moveField(workspaceSlug, projectId, field.id, direction);
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not move the property", message: "Try again." });
    }
  };

  return (
    <>
      <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.TOP} width={EModalWidth.XL}>
        <div className="flex max-h-[80vh] flex-col">
          <div className="flex items-center justify-between gap-3 border-b border-subtle px-5 py-4">
            <h3 className="text-h5-medium text-primary">Properties</h3>
            {isAdmin && (
              <Button variant="primary" size="base" prependIcon={<Plus />} onClick={() => setAddOpen(true)}>
                Add property
              </Button>
            )}
          </div>

          <div className="vertical-scrollbar scrollbar-sm flex flex-col overflow-y-auto px-3 py-2">
            <p className="px-2 pt-1 pb-2 text-caption-md-regular text-tertiary">
              The eye shows or hides a property on the list for this view.
            </p>

            {fields.length > 0 && <SectionLabel>Custom</SectionLabel>}
            {fields.map((field, index) => {
              const type = getFieldDetails(field);
              const seen = isSeenField(field);
              return (
                <div key={field.id} className="flex min-h-11 items-center gap-2 rounded-md px-2 hover:bg-layer-1">
                  {seen ? (
                    <span className="size-8 shrink-0" />
                  ) : (
                    <EyeToggle shown={isFieldShown(field)} onClick={() => toggleField(field)} />
                  )}
                  <type.icon className="size-4 shrink-0 text-tertiary" />
                  <div className="flex min-w-0 grow flex-col">
                    {isAdmin ? (
                      <RenameInput workspaceSlug={workspaceSlug} projectId={projectId} field={field} />
                    ) : (
                      <span className="truncate text-body-sm-medium text-primary">{field.name}</span>
                    )}
                    <span className="truncate px-1 text-caption-sm-regular text-tertiary">
                      {type.label}
                      {seen ? " · always the check at the end of a row" : ""}
                    </span>
                  </div>
                  {isAdmin && (
                    <div className="flex shrink-0 items-center">
                      <IconButton label="Move up" disabled={index === 0} onClick={() => move(field, "up")}>
                        <ArrowUp className="size-3.5" />
                      </IconButton>
                      <IconButton
                        label="Move down"
                        disabled={index === fields.length - 1}
                        onClick={() => move(field, "down")}
                      >
                        <ArrowDown className="size-3.5" />
                      </IconButton>
                    </div>
                  )}
                </div>
              );
            })}

            {builtIns.length > 0 && <SectionLabel>Built in</SectionLabel>}
            {builtIns.map((property) => {
              const shown = !!displayProperties?.[property.key];
              return (
                <div key={property.key} className="flex min-h-11 items-center gap-2 rounded-md px-2 hover:bg-layer-1">
                  <EyeToggle shown={shown} onClick={() => handleUpdate({ [property.key]: !shown })} />
                  <span className="truncate px-1 text-body-sm-regular text-primary">
                    {t(property.titleTranslationKey)}
                  </span>
                </div>
              );
            })}
          </div>

          <div className="flex items-center justify-between gap-3 border-t border-subtle px-5 py-3">
            <Link
              href={`/${workspaceSlug}/settings/projects/${projectId}/custom-fields`}
              onClick={onClose}
              className="flex items-center gap-1.5 text-body-xs-medium text-secondary hover:text-primary"
            >
              <Settings className="size-3.5" />
              Open full settings
            </Link>
            <Button variant="secondary" size="base" onClick={onClose}>
              Done
            </Button>
          </div>
        </div>
      </ModalCore>
      <CustomFieldFormModal
        isOpen={addOpen}
        onClose={() => setAddOpen(false)}
        workspaceSlug={workspaceSlug}
        projectId={projectId}
      />
    </>
  );
});

/** Inline rename of a custom field: saves on Enter or when the box loses focus; Escape undoes. */
const RenameInput = observer(function RenameInput(props: {
  workspaceSlug: string;
  projectId: string;
  field: TCustomField;
}) {
  const { workspaceSlug, projectId, field } = props;
  const { updateField } = useCustomField();
  const [name, setName] = useState(field.name);
  const [saving, setSaving] = useState(false);

  useEffect(() => setName(field.name), [field.name]);

  const save = async () => {
    const next = name.trim();
    if (!next) {
      setName(field.name);
      return;
    }
    if (next === field.name) return;
    setSaving(true);
    try {
      await updateField(workspaceSlug, projectId, field.id, { name: next });
    } catch (error) {
      setName(field.name);
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not rename", message: errorMessage(error) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <input
      value={name}
      disabled={saving}
      maxLength={255}
      aria-label={`Name of ${field.name}`}
      onChange={(e) => setName(e.target.value)}
      onBlur={save}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") {
          e.stopPropagation();
          setName(field.name);
        }
      }}
      className="w-full truncate rounded-sm border border-transparent bg-transparent px-1 py-0.5 text-body-sm-medium text-primary hover:border-subtle focus:border-strong focus:outline-none"
    />
  );
});

function EyeToggle(props: { shown: boolean; onClick: () => void }) {
  const { shown, onClick } = props;
  const label = shown ? "Hide on the list" : "Show on the list";
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={shown}
      title={label}
      onClick={onClick}
      className={cn(
        "grid size-8 shrink-0 place-items-center rounded-sm hover:bg-layer-2",
        shown ? "text-primary" : "text-placeholder"
      )}
    >
      {shown ? <Eye className="size-4" /> : <EyeOff className="size-4" />}
    </button>
  );
}

function SectionLabel(props: { children: React.ReactNode }) {
  return <p className="px-2 pt-3 pb-1 text-caption-md-medium text-tertiary">{props.children}</p>;
}

function IconButton(props: { label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  const { label, onClick, disabled, children } = props;
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="grid size-8 place-items-center rounded-sm text-tertiary hover:bg-layer-2 hover:text-primary disabled:opacity-30"
    >
      {children}
    </button>
  );
}
