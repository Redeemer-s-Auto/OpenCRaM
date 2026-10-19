/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Plus } from "lucide-react";
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { cn } from "@plane/utils";
// hooks
import { useUserPermissions } from "@/hooks/store/user";
// local
import { CustomFieldFormModal } from "./settings/field-form-modal";

type Props = {
  workspaceSlug: string;
  projectId: string;
  /** "row" for the card side panel, "header" for the table */
  variant: "row" | "header";
};

/** "+ Add field" right on the board, so admins do not need project settings. */
export const AddCustomFieldButton = observer(function AddCustomFieldButton(props: Props) {
  const { workspaceSlug, projectId, variant } = props;
  const [open, setOpen] = useState(false);
  const { allowPermissions } = useUserPermissions();
  const isAdmin = allowPermissions(
    [EUserPermissions.ADMIN],
    EUserPermissionsLevel.PROJECT,
    workspaceSlug,
    projectId
  );
  if (!isAdmin || !workspaceSlug || !projectId) return null;

  return (
    <>
      <CustomFieldFormModal
        isOpen={open}
        onClose={() => setOpen(false)}
        workspaceSlug={workspaceSlug}
        projectId={projectId}
      />
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Add a custom field to this project"
        className={cn(
          "flex items-center gap-1.5 text-tertiary hover:text-primary",
          variant === "row" ? "h-7.5 px-0 text-body-xs-regular" : "h-full w-full justify-center px-3 text-13"
        )}
      >
        <Plus className="size-3.5 shrink-0" />
        {variant === "row" ? "Add field" : <span className="sr-only">Add field</span>}
      </button>
    </>
  );
});
