/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import { observer } from "mobx-react";
import { CornerUpRight } from "lucide-react";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { Tooltip } from "@plane/propel/tooltip";
import { EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
import { cn } from "@plane/utils";
import { useProject } from "@/hooks/store/use-project";
import { useAppRouter } from "@/hooks/use-app-router";
import { cardLinksService } from "@/services/card-links.service";
import { getShortcutTarget, loadProjectShortcuts, setShortcutTarget } from "./store";

const MEMBER_ROLE = 15;

type Props = {
  workspaceSlug: string;
  /** the card the shortcut will open */
  issueId: string;
  /** its board (offered last, since a shortcut on the same board is rarely wanted) */
  projectId: string;
  className?: string;
};

/** Header button: put a shortcut to this card on another board (Notion's "link to page"). */
export const AddShortcutButton = observer(function AddShortcutButton(props: Props) {
  const { workspaceSlug, issueId, projectId, className } = props;
  const [open, setOpen] = useState(false);
  // A shortcut card itself cannot be the target of another shortcut.
  if (getShortcutTarget(issueId)) return null;
  return (
    <>
      <Tooltip tooltipContent="Add a shortcut to this card on another board">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className={cn(
            "flex items-center gap-1 rounded-sm px-2 py-1 text-12 text-secondary hover:bg-layer-1-hover hover:text-primary",
            className
          )}
          aria-label="Add shortcut"
        >
          <CornerUpRight className="size-3.5" />
          Add shortcut
        </button>
      </Tooltip>
      {open && (
        <AddShortcutModal
          workspaceSlug={workspaceSlug}
          issueId={issueId}
          projectId={projectId}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
});

const AddShortcutModal = observer(function AddShortcutModal(props: Omit<Props, "className"> & { onClose: () => void }) {
  const { workspaceSlug, issueId, projectId, onClose } = props;
  const router = useAppRouter();
  const { joinedProjectIds, getProjectById } = useProject();
  const [chosen, setChosen] = useState<string | undefined>(undefined);
  const [busy, setBusy] = useState(false);

  const boards = useMemo(() => {
    const allowed = joinedProjectIds
      .map((id) => getProjectById(id))
      .filter((project): project is NonNullable<typeof project> => {
        if (!project || project.archived_at) return false;
        return Number(project.member_role ?? 0) >= MEMBER_ROLE;
      });
    return [...allowed.filter((p) => p.id !== projectId), ...allowed.filter((p) => p.id === projectId)];
  }, [joinedProjectIds, getProjectById, projectId]);

  const submit = async () => {
    if (!chosen) return;
    setBusy(true);
    try {
      const made = await cardLinksService.createShortcut(workspaceSlug, chosen, issueId);
      setShortcutTarget(made.id, made.target);
      loadProjectShortcuts(workspaceSlug, chosen, true);
      const board = getProjectById(chosen);
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: "Shortcut added",
        message: board ? `A shortcut to this card is now on ${board.name}.` : "Shortcut added.",
      });
      onClose();
      router.push(`/${workspaceSlug}/projects/${chosen}/issues/`);
    } catch (error) {
      const message = (error as { error?: string } | undefined)?.error ?? "Could not add the shortcut.";
      setToast({ type: TOAST_TYPE.ERROR, title: "Shortcut not added", message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalCore isOpen handleClose={onClose} position={EModalPosition.CENTER} width={EModalWidth.LG}>
      <div className="flex flex-col gap-3 p-5">
        <div>
          <h3 className="text-16 font-medium text-primary">Add a shortcut</h3>
          <p className="text-13 text-tertiary">
            Pick a board. A shortcut card appears there and opens this card. People who cannot see this card see
            only &quot;Hidden card&quot;.
          </p>
        </div>
        <div className="flex max-h-72 flex-col gap-0.5 overflow-y-auto" role="radiogroup">
          {boards.length === 0 && <p className="text-13 text-tertiary">You cannot add cards to any board.</p>}
          {boards.map((board) => (
            <label
              key={board.id}
              className={cn("flex cursor-pointer items-center gap-2 rounded-sm px-2 py-1.5 text-13 hover:bg-layer-1-hover", {
                "bg-layer-1-hover": chosen === board.id,
              })}
            >
              <input
                type="radio"
                name="shortcut-board"
                value={board.id}
                checked={chosen === board.id}
                onChange={() => setChosen(board.id)}
              />
              <span className="truncate text-primary">{board.name}</span>
              <span className="ml-auto text-11 text-tertiary">
                {board.identifier}
                {board.id === projectId ? " · this card's board" : ""}
              </span>
            </label>
          ))}
        </div>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="lg" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" size="lg" disabled={!chosen || busy} onClick={() => void submit()}>
            {busy ? "Adding…" : "Add shortcut"}
          </Button>
        </div>
      </div>
    </ModalCore>
  );
});
