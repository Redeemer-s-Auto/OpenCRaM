/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TCustomField } from "@plane/types";
import { EModalPosition, EModalWidth, Input, ModalCore } from "@plane/ui";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";

type Props = {
  field: TCustomField | null;
  onClose: () => void;
  workspaceSlug: string;
  projectId: string;
};

/**
 * Deleting a field removes every value in it, on every card. The admin must type
 * the field name. Archive is offered first because it keeps the values.
 */
export const DeleteCustomFieldModal = observer(function DeleteCustomFieldModal(props: Props) {
  const { field, onClose, workspaceSlug, projectId } = props;
  const { deleteField, archiveField } = useCustomField();
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState<"delete" | "archive" | null>(null);

  useEffect(() => setTyped(""), [field]);

  if (!field) return null;

  const handleArchive = async () => {
    setBusy("archive");
    try {
      await archiveField(workspaceSlug, projectId, field.id);
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Field archived", message: `${field.name} is hidden. Values kept.` });
      onClose();
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not archive", message: "Try again." });
    } finally {
      setBusy(null);
    }
  };

  const handleDelete = async () => {
    setBusy("delete");
    try {
      await deleteField(workspaceSlug, projectId, field.id, typed);
      setToast({ type: TOAST_TYPE.SUCCESS, title: "Field deleted", message: field.name });
      onClose();
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not delete", message: "Check the name and try again." });
    } finally {
      setBusy(null);
    }
  };

  return (
    <ModalCore isOpen={!!field} handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.LG}>
      <div className="flex flex-col gap-4 p-5">
        <h3 className="text-h5-medium text-primary">Delete &quot;{field.name}&quot;?</h3>
        <p className="text-body-sm-regular text-secondary">
          This deletes the field <strong>and every value in it, on every card</strong>. It cannot be undone.
        </p>
        <p className="text-body-sm-regular text-secondary">
          To hide the field and keep the values, archive it instead. You can restore an archived field later.
        </p>
        <label className="flex flex-col gap-1">
          <span className="text-body-xs-medium text-secondary">Type the field name to delete it</span>
          <Input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={field.name} />
        </label>
        <div className="flex flex-wrap justify-end gap-2 pt-2">
          <Button variant="secondary" size="lg" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="secondary" size="lg" loading={busy === "archive"} onClick={handleArchive}>
            Archive instead
          </Button>
          <Button
            variant="error-fill"
            size="lg"
            loading={busy === "delete"}
            disabled={typed !== field.name}
            onClick={handleDelete}
          >
            Delete field and values
          </Button>
        </div>
      </div>
    </ModalCore>
  );
});
