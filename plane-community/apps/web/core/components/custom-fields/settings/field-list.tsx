/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { ArchiveRestore, ArrowDown, ArrowUp, Pencil, Trash2 } from "lucide-react";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TCustomField } from "@plane/types";
import { Loader } from "@plane/ui";
// components
import { SettingsHeading } from "@/components/settings/heading";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";
import { useUserPermissions } from "@/hooks/store/user";
// local
import { getFieldTypeDetails } from "../helpers";
import { OptionChip } from "../value-input";
import { DeleteCustomFieldModal } from "./delete-field-modal";
import { CustomFieldFormModal } from "./field-form-modal";

export const ProjectSettingsCustomFieldList = observer(function ProjectSettingsCustomFieldList() {
  const { workspaceSlug: routerWorkspaceSlug, projectId: routerProjectId } = useParams();
  const workspaceSlug = routerWorkspaceSlug?.toString() ?? "";
  const projectId = routerProjectId?.toString() ?? "";
  const { getProjectFields, getArchivedProjectFields, moveField, restoreField } = useCustomField();
  const { allowPermissions } = useUserPermissions();
  const isAdmin = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TCustomField | null>(null);
  const [deleting, setDeleting] = useState<TCustomField | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  const fields = getProjectFields(projectId);
  const archived = getArchivedProjectFields(projectId);

  const move = async (field: TCustomField, direction: "up" | "down") => {
    try {
      await moveField(workspaceSlug, projectId, field.id, direction);
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not move the field", message: "Try again." });
    }
  };

  return (
    <>
      <CustomFieldFormModal
        isOpen={formOpen}
        onClose={() => {
          setFormOpen(false);
          setEditing(null);
        }}
        workspaceSlug={workspaceSlug}
        projectId={projectId}
        field={editing}
      />
      <DeleteCustomFieldModal
        field={deleting}
        onClose={() => setDeleting(null)}
        workspaceSlug={workspaceSlug}
        projectId={projectId}
      />

      <SettingsHeading
        title="Custom fields"
        description="Add your own fields to the cards on this board. They show on each card and as table columns."
        control={
          isAdmin && (
            <Button variant="primary" size="lg" onClick={() => setFormOpen(true)}>
              Add field
            </Button>
          )
        }
      />

      <div className="mt-6 flex flex-col">
        {fields === undefined ? (
          <Loader className="space-y-3">
            <Loader.Item height="42px" />
            <Loader.Item height="42px" />
          </Loader>
        ) : fields.length === 0 ? (
          <div className="rounded-md border border-dashed border-subtle px-4 py-8 text-center">
            <p className="text-body-sm-medium text-primary">No custom fields yet</p>
            <p className="mt-1 text-body-xs-regular text-tertiary">
              {isAdmin ? "Add a field, for example a date, a dollar amount, or a dropdown." : "An admin can add fields."}
            </p>
          </div>
        ) : (
          fields.map((field, index) => {
            const type = getFieldTypeDetails(field.field_type);
            return (
              <div
                key={field.id}
                className="group flex items-center gap-3 border-b border-subtle px-2 py-2.5 last:border-b-0"
              >
                <type.icon className="size-4 shrink-0 text-tertiary" />
                <div className="flex min-w-0 grow flex-col">
                  <span className="truncate text-body-sm-medium text-primary">{field.name}</span>
                  <span className="truncate text-caption-md-regular text-tertiary">
                    {type.label}
                    {field.description ? ` · ${field.description}` : ""}
                  </span>
                  {field.options.length > 0 && (
                    <span className="mt-1 flex flex-wrap gap-1 text-caption-md-regular">
                      {field.options.slice(0, 8).map((o) => (
                        <OptionChip key={o.id} name={o.name} color={o.color} />
                      ))}
                      {field.options.length > 8 && <span className="text-tertiary">+{field.options.length - 8}</span>}
                    </span>
                  )}
                </div>
                {isAdmin && (
                  <div className="flex shrink-0 items-center gap-1 opacity-60 group-hover:opacity-100">
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
                    <IconButton
                      label="Edit"
                      onClick={() => {
                        setEditing(field);
                        setFormOpen(true);
                      }}
                    >
                      <Pencil className="size-3.5" />
                    </IconButton>
                    <IconButton label="Delete or archive" onClick={() => setDeleting(field)}>
                      <Trash2 className="size-3.5" />
                    </IconButton>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {archived.length > 0 && (
        <div className="mt-8">
          <button
            type="button"
            className="text-body-xs-medium text-secondary hover:text-primary"
            onClick={() => setShowArchived(!showArchived)}
          >
            {showArchived ? "Hide" : "Show"} archived fields ({archived.length})
          </button>
          {showArchived && (
            <div className="mt-2 flex flex-col">
              {archived.map((field) => (
                <div key={field.id} className="flex items-center gap-3 border-b border-subtle px-2 py-2 last:border-b-0">
                  <span className="grow truncate text-body-sm-regular text-tertiary">{field.name}</span>
                  {isAdmin && (
                    <>
                      <Button
                        variant="ghost"
                        size="base"
                        prependIcon={<ArchiveRestore />}
                        onClick={() => restoreField(workspaceSlug, projectId, field.id)}
                      >
                        Restore
                      </Button>
                      <IconButton label="Delete" onClick={() => setDeleting(field)}>
                        <Trash2 className="size-3.5" />
                      </IconButton>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
});

function IconButton(props: { label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  const { label, onClick, disabled, children } = props;
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className="grid size-6 place-items-center rounded-sm text-tertiary hover:bg-layer-1 hover:text-primary disabled:opacity-30"
    >
      {children}
    </button>
  );
}
