/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { Pencil, Play, Trash2 } from "lucide-react";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { EModalPosition, EModalWidth, Input, Loader, ModalCore } from "@plane/ui";
// components
import { SettingsHeading } from "@/components/settings/heading";
// services
import type { TIssueTemplate, TIssueTemplateNode } from "@/services/issue/issue_template.service";
import { issueTemplateService } from "@/services/issue/issue_template.service";
// local
import { useCreateFromTemplate, useIssueTemplates } from "./use-issue-templates";

const countCards = (node: TIssueTemplateNode): number =>
  1 + (node.sub_items ?? []).reduce((sum, child) => sum + countCards(child), 0);

const subTitles = (node: TIssueTemplateNode, depth = 0): string[] =>
  (node.sub_items ?? []).flatMap((child) => [`${"  ".repeat(depth)}• ${child.name}`, ...subTitles(child, depth + 1)]);

export const ProjectSettingsTemplateList = observer(function ProjectSettingsTemplateList() {
  const { workspaceSlug: ws, projectId: pid } = useParams();
  const workspaceSlug = ws?.toString() ?? "";
  const projectId = pid?.toString() ?? "";
  const { templates, isLoading, refresh } = useIssueTemplates(workspaceSlug, projectId);
  const createFromTemplate = useCreateFromTemplate();

  const [editing, setEditing] = useState<TIssueTemplate | null>(null);
  const [deleting, setDeleting] = useState<TIssueTemplate | null>(null);

  const handleUse = async (template: TIssueTemplate) => {
    try {
      const result = await createFromTemplate(workspaceSlug, projectId, template.id);
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Card created", message: `${result.name} (${result.created_count})` });
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not use the template", message: "Try again." });
    }
  };

  return (
    <>
      <EditTemplateModal
        template={editing}
        onClose={() => setEditing(null)}
        onSaved={refresh}
        workspaceSlug={workspaceSlug}
        projectId={projectId}
      />
      <ModalCore isOpen={!!deleting} handleClose={() => setDeleting(null)} position={EModalPosition.CENTER} width={EModalWidth.MD}>
        <div className="flex flex-col gap-4 p-5">
          <h3 className="text-h5-medium text-primary">Delete &quot;{deleting?.name}&quot;?</h3>
          <p className="text-body-sm-regular text-secondary">
            Cards already made from this template stay. Only the template goes away.
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" size="lg" onClick={() => setDeleting(null)}>
              Cancel
            </Button>
            <Button
              variant="error-fill"
              size="lg"
              onClick={async () => {
                if (!deleting) return;
                await issueTemplateService.remove(workspaceSlug, projectId, deleting.id);
                setDeleting(null);
                refresh();
              }}
            >
              Delete template
            </Button>
          </div>
        </div>
      </ModalCore>

      <SettingsHeading
        title="Templates"
        description="Ready-made cards for this board. To make one, open a card's menu and pick Save as template. Use them from the new-card window."
      />

      <div className="mt-6 flex flex-col">
        {isLoading ? (
          <Loader className="space-y-3">
            <Loader.Item height="56px" />
            <Loader.Item height="56px" />
          </Loader>
        ) : templates.length === 0 ? (
          <div className="rounded-md border border-dashed border-subtle px-4 py-8 text-center">
            <p className="text-body-sm-medium text-primary">No templates yet</p>
            <p className="mt-1 text-body-xs-regular text-tertiary">
              Set up a card the way you like it, then choose Save as template from its menu.
            </p>
          </div>
        ) : (
          templates.map((template) => {
            const cards = countCards(template.data);
            const fieldCount = Object.keys(template.data.custom_fields ?? {}).length;
            return (
              <div key={template.id} className="group flex items-start gap-3 border-b border-subtle px-2 py-3 last:border-b-0">
                <div className="flex min-w-0 grow flex-col">
                  <span className="truncate text-body-sm-medium text-primary">{template.name}</span>
                  <span className="truncate text-caption-md-regular text-tertiary">
                    Card title: {template.data.name || template.name}
                    {cards > 1 ? ` · ${cards - 1} sub-card${cards > 2 ? "s" : ""}` : ""}
                    {fieldCount ? ` · ${fieldCount} field value${fieldCount > 1 ? "s" : ""}` : ""}
                    {template.description ? ` · ${template.description}` : ""}
                  </span>
                  {cards > 1 && (
                    <pre className="mt-1 font-sans text-caption-md-regular whitespace-pre-wrap text-tertiary">
                      {subTitles(template.data).join("\n")}
                    </pre>
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-1 opacity-60 group-hover:opacity-100">
                  <Button variant="ghost" size="base" prependIcon={<Play />} onClick={() => handleUse(template)}>
                    Use
                  </Button>
                  <IconButton label="Edit" onClick={() => setEditing(template)}>
                    <Pencil className="size-3.5" />
                  </IconButton>
                  <IconButton label="Delete" onClick={() => setDeleting(template)}>
                    <Trash2 className="size-3.5" />
                  </IconButton>
                </div>
              </div>
            );
          })
        )}
      </div>
    </>
  );
});

/** Edit the template's name and description, the card title, and the sub-card titles. */
const EditTemplateModal = observer(function EditTemplateModal(props: {
  template: TIssueTemplate | null;
  onClose: () => void;
  onSaved: () => void;
  workspaceSlug: string;
  projectId: string;
}) {
  const { template, onClose, onSaved, workspaceSlug, projectId } = props;
  const [draft, setDraft] = useState<TIssueTemplate | null>(null);
  const [saving, setSaving] = useState(false);
  if (template && (!draft || draft.id !== template.id)) setDraft(structuredClone(template));
  if (!template || !draft) return null;

  const setNode = (path: number[], name: string) => {
    const next = structuredClone(draft);
    let node = next.data;
    for (const index of path) node = node.sub_items[index];
    node.name = name;
    setDraft(next);
  };
  const removeNode = (path: number[]) => {
    const next = structuredClone(draft);
    let parent = next.data;
    for (const index of path.slice(0, -1)) parent = parent.sub_items[index];
    parent.sub_items.splice(path[path.length - 1], 1);
    setDraft(next);
  };
  const addNode = (path: number[]) => {
    const next = structuredClone(draft);
    let node = next.data;
    for (const index of path) node = node.sub_items[index];
    node.sub_items = [
      ...(node.sub_items ?? []),
      { name: "New sub-card", description_html: "", priority: "none", state_id: null, label_ids: [], custom_fields: {}, sub_items: [] },
    ];
    setDraft(next);
  };

  const renderSubs = (node: TIssueTemplateNode, path: number[]) =>
    (node.sub_items ?? []).map((child, index) => {
      const childPath = [...path, index];
      return (
        <div key={childPath.join("-")} className="flex flex-col gap-1" style={{ paddingLeft: path.length * 16 }}>
          <div className="flex items-center gap-2">
            <Input value={child.name} onChange={(e) => setNode(childPath, e.target.value)} className="grow" />
            {childPath.length < 2 && (
              <Button variant="ghost" size="base" onClick={() => addNode(childPath)}>
                + sub
              </Button>
            )}
            <IconButton label="Remove sub-card" onClick={() => removeNode(childPath)}>
              <Trash2 className="size-3.5" />
            </IconButton>
          </div>
          {renderSubs(child, childPath)}
        </div>
      );
    });

  const handleSave = async () => {
    setSaving(true);
    try {
      await issueTemplateService.update(workspaceSlug, projectId, draft.id, {
        name: draft.name,
        description: draft.description,
        data: draft.data,
      });
      onSaved();
      onClose();
    } catch (error) {
      const message =
        (error && typeof error === "object" && Object.values(error as Record<string, unknown>).flat().find(
          (v) => typeof v === "string"
        )) || "Try again.";
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not save", message: String(message) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalCore isOpen={!!template} handleClose={onClose} position={EModalPosition.TOP} width={EModalWidth.XL}>
      <div className="flex flex-col gap-4 p-5">
        <h3 className="text-h5-medium text-primary">Edit template</h3>
        <label className="flex flex-col gap-1">
          <span className="text-body-xs-medium text-secondary">Template name</span>
          <Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-body-xs-medium text-secondary">Description (optional)</span>
          <Input value={draft.description} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-body-xs-medium text-secondary">Card title</span>
          <Input
            value={draft.data.name}
            onChange={(e) => setDraft({ ...draft, data: { ...draft.data, name: e.target.value } })}
          />
        </label>
        <div className="flex flex-col gap-2">
          <span className="text-body-xs-medium text-secondary">Sub-cards</span>
          {renderSubs(draft.data, [])}
          <Button variant="ghost" size="base" className="self-start" onClick={() => addNode([])}>
            + Add sub-card
          </Button>
        </div>
        <p className="text-caption-md-regular text-tertiary">
          To change the page, fields or labels: make a card from this template, change it, then Save as template
          again.
        </p>
        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" size="lg" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="lg" loading={saving} onClick={handleSave}>
            Save
          </Button>
        </div>
      </div>
    </ModalCore>
  );
});

function IconButton(props: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-label={props.label}
      title={props.label}
      onClick={props.onClick}
      className="grid size-6 place-items-center rounded-sm text-tertiary hover:bg-layer-1 hover:text-primary"
    >
      {props.children}
    </button>
  );
}
