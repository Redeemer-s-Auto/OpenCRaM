/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { SmilePlus } from "lucide-react";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import type { TChangeHandlerProps } from "@plane/propel/emoji-icon-picker";
import { EmojiPicker, EmojiIconPickerTypes, Logo } from "@plane/propel/emoji-icon-picker";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import type { TLogoProps } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";

type Props = {
  projectId: string | undefined;
  /** Small grey word after the name, e.g. "Views" or "Pages" on those lists. */
  suffix?: string;
  /** Anything that sits right after the name (a count chip, a lock icon). */
  children?: ReactNode;
};

/**
 * The board's name as the page heading, in the header row on every board screen (list, board,
 * table, the views list, the pages list). 24 px bold on one line; it only truncates when the
 * name alone is wider than the screen, because the header buttons wrap to a second line first.
 * The board's icon sits before the name; board admins click it to pick another emoji or icon.
 */
export const BoardTitle = observer(function BoardTitle(props: Props) {
  const { projectId, suffix, children } = props;
  const { workspaceSlug } = useParams();
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const { getPartialProjectById, updateProject } = useProject();
  const { allowPermissions } = useUserPermissions();
  const project = projectId ? getPartialProjectById(projectId) : undefined;
  const name = project?.name;
  const logo = project?.logo_props;
  const hasLogo = !!logo?.in_use;
  // Same rule as the board's settings page: board admins change the icon. An archived board
  // cannot be changed (the API refuses every save), so it gets no picker.
  const canEdit =
    !!workspaceSlug &&
    !!projectId &&
    !project?.archived_at &&
    allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.PROJECT, workspaceSlug.toString(), projectId);

  const handleLogoChange = (value: TChangeHandlerProps) => {
    if (!workspaceSlug || !projectId) return;
    const logo_props: TLogoProps =
      value.type === EmojiIconPickerTypes.EMOJI
        ? { in_use: "emoji", emoji: { value: value.value } }
        : { in_use: "icon", icon: { name: value.value.name, color: value.value.color } };
    setIsPickerOpen(false);
    updateProject(workspaceSlug.toString(), projectId, { logo_props }).catch(() =>
      setToast({ type: TOAST_TYPE.ERROR, title: "Error!", message: "The board icon could not be changed." })
    );
  };

  return (
    <div className="flex max-w-full min-w-0 items-center gap-2">
      {project && (hasLogo || canEdit) && (
        <EmojiPicker
          iconType="material"
          isOpen={isPickerOpen}
          handleToggle={(open: boolean) => setIsPickerOpen(open)}
          className="flex flex-shrink-0 items-center justify-center"
          buttonClassName={cn("flex size-8 flex-shrink-0 items-center justify-center rounded-md", {
            "hover:bg-layer-1": canEdit,
          })}
          label={
            <span data-board-icon="" title={canEdit ? "Change icon" : undefined} className="grid size-8 place-items-center">
              {hasLogo ? (
                <Logo logo={logo} size={24} />
              ) : (
                <SmilePlus className="size-5 text-placeholder" aria-label="Add icon" />
              )}
            </span>
          }
          onChange={handleLogoChange}
          defaultIconColor={logo?.in_use === "icon" ? logo.icon?.color : undefined}
          defaultOpen={logo?.in_use === "emoji" ? EmojiIconPickerTypes.EMOJI : EmojiIconPickerTypes.ICON}
          disabled={!canEdit}
        />
      )}
      <h1
        data-board-title=""
        title={name}
        className="min-w-0 truncate text-[24px] leading-8 font-bold tracking-tight text-primary"
      >
        {name ?? ""}
      </h1>
      {suffix && <span className="flex-shrink-0 text-14 font-medium text-tertiary">{suffix}</span>}
      {children}
    </div>
  );
});
