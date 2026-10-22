/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Link } from "react-router";
import useSWR from "swr";
import { Button } from "@plane/propel/button";
import { EmojiPicker, EmojiIconPickerTypes } from "@plane/propel/emoji-icon-picker";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TLogoProps, TProject } from "@plane/types";
import { Checkbox, EModalPosition, EModalWidth, Input, ModalCore, TextArea } from "@plane/ui";
// services
import { blueprintErrorMessage, blueprintService } from "@/services/blueprint.service";
// local
import { BlueprintIcon } from "./helpers";

type TModalProps = {
  isOpen: boolean;
  onClose: () => void;
  workspaceSlug: string;
  project: TProject;
};

export const SaveBlueprintModal = observer(function SaveBlueprintModal(props: TModalProps) {
  const { isOpen, onClose, workspaceSlug, project } = props;
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [logo, setLogo] = useState<TLogoProps | undefined>(undefined);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [includeSamples, setIncludeSamples] = useState(false);
  const [includeRepeats, setIncludeRepeats] = useState(false);
  const [shared, setShared] = useState(true);
  const [saving, setSaving] = useState(false);
  const isPrivate = Boolean(project.is_private);

  useEffect(() => {
    if (!isOpen) return;
    setName(project.name ?? "");
    setDescription("");
    setLogo(project.logo_props?.in_use ? project.logo_props : undefined);
    setIncludeSamples(false);
    setIncludeRepeats(false);
    setShared(!isPrivate);
  }, [isOpen, project.name, project.logo_props, isPrivate]);

  const handleSave = async () => {
    setSaving(true);
    try {
      const blueprint = await blueprintService.saveFromBoard(workspaceSlug, {
        project_id: project.id,
        name: name.trim(),
        description: description.trim(),
        logo_props: logo,
        include_samples: includeSamples,
        include_repeat_rules: includeSamples && includeRepeats,
        is_shared: shared,
      });
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: "Blueprint saved",
        message: `${blueprint.name} (v${blueprint.version}). Find it in Workspace settings > Blueprints.`,
      });
      onClose();
    } catch (error) {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: "Could not save the blueprint",
        message: blueprintErrorMessage(error),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalCore isOpen={isOpen} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.XL}>
      <div className="flex flex-col gap-4 p-5">
        <h3 className="text-h5-medium text-primary">Save as blueprint</h3>
        <p className="text-body-xs-regular text-tertiary">
          A blueprint copies this board&apos;s design, not its cards: fields (formulas, relations and rollups too),
          states, labels, saved views, your layout and display settings, card templates, and board settings. Use it to
          start new boards the same way, or export it for another workspace.
        </p>
        <div className="flex items-end gap-2">
          <EmojiPicker
            iconType="material"
            closeOnSelect={false}
            isOpen={pickerOpen}
            handleToggle={(value: boolean) => setPickerOpen(value)}
            className="flex items-center justify-center"
            buttonClassName="flex size-9 items-center justify-center rounded-md border border-subtle bg-layer-2"
            label={<BlueprintIcon logo={logo} size={18} />}
            onChange={(val: { type?: string; value?: unknown }) => {
              if (val?.type === "emoji") setLogo({ in_use: "emoji", emoji: { value: String(val.value) } });
              else if (val?.type === "icon") setLogo({ in_use: "icon", icon: val.value as TLogoProps["icon"] });
              setPickerOpen(false);
            }}
            defaultIconColor={logo?.in_use === "icon" ? logo.icon?.color : undefined}
            defaultOpen={logo?.in_use === "emoji" ? EmojiIconPickerTypes.EMOJI : EmojiIconPickerTypes.ICON}
          />
          <label className="flex flex-grow flex-col gap-1">
            <span className="text-body-xs-medium text-secondary">Blueprint name</span>
            <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={255} autoFocus />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className="text-body-xs-medium text-secondary">Description</span>
          <TextArea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="What boards is this for?"
            className="min-h-16"
          />
        </label>
        <label className="flex items-start gap-2 text-body-xs-regular text-secondary">
          <Checkbox checked={includeSamples} onChange={(e) => setIncludeSamples(e.target.checked)} />
          <span>
            Include this board&apos;s cards as sample cards (titles, page text, field values; at most 50).
            {includeSamples && (
              <span className="mt-1 block text-danger-primary">
                Sample cards are real content from this board. Anyone who can use this blueprint can read them. An
                exported file leaves them out unless someone ticks &quot;Include sample cards&quot; when exporting; then
                anyone who gets the file can read them. Only include made-up example cards. Never include real client,
                team member, vehicle, money or shop records. Cards hidden by sharing rules are never included; people,
                mentions and images are removed.
              </span>
            )}
          </span>
        </label>
        {includeSamples && (
          <label className="ml-6 flex items-center gap-2 text-body-xs-regular text-secondary">
            <Checkbox checked={includeRepeats} onChange={(e) => setIncludeRepeats(e.target.checked)} />
            Keep repeat rules on sample cards
          </label>
        )}
        <label className="flex items-center gap-2 text-body-xs-regular text-secondary">
          <Checkbox checked={shared} onChange={(e) => setShared(e.target.checked)} />
          Everyone in the workspace can use it
        </label>
        {isPrivate && (
          <p className="text-caption-md-regular text-tertiary">
            This board is private. Boards made from the blueprint are private too. Field names and views become visible
            to whoever can use the blueprint.
          </p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" size="lg" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="lg" onClick={handleSave} disabled={saving || !name.trim()}>
            {saving ? "Saving..." : "Save blueprint"}
          </Button>
        </div>
      </div>
    </ModalCore>
  );
});

type TSectionProps = {
  workspaceSlug: string;
  project: TProject;
  canSave: boolean;
};

/** Board settings > General: "Made from blueprint X v3" and the "Save as blueprint" button. */
export const BoardBlueprintSection = observer(function BoardBlueprintSection(props: TSectionProps) {
  const { workspaceSlug, project, canSave } = props;
  const [isOpen, setIsOpen] = useState(false);
  const { data: origin } = useSWR(`BOARD_BLUEPRINT_ORIGIN_${project.id}`, () =>
    blueprintService.boardOrigin(workspaceSlug, project.id)
  );

  if (!canSave && !origin) return null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-subtle py-6">
      <div>
        <h4 className="text-body-sm-medium text-primary">Blueprint</h4>
        <p className="text-body-xs-regular text-tertiary">
          {origin ? (
            <>
              Made from blueprint{" "}
              {origin.blueprint_id ? (
                <Link className="text-primary hover:underline" to={`/${workspaceSlug}/settings/blueprints`}>
                  {origin.blueprint_name}
                </Link>
              ) : (
                <span className="text-primary">{origin.blueprint_name}</span>
              )}{" "}
              v{origin.version}.
            </>
          ) : (
            "Save this board's design to start new boards the same way."
          )}
        </p>
      </div>
      {canSave && (
        <Button variant="secondary" size="lg" onClick={() => setIsOpen(true)}>
          Save as blueprint
        </Button>
      )}
      {canSave && (
        <SaveBlueprintModal
          isOpen={isOpen}
          onClose={() => setIsOpen(false)}
          workspaceSlug={workspaceSlug}
          project={project}
        />
      )}
    </div>
  );
});
