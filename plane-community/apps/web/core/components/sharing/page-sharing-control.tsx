/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { Lock, X } from "lucide-react";
import { useParams } from "next/navigation";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { EModalPosition, EModalWidth, ModalCore } from "@plane/ui";
// hooks
import { useUser } from "@/hooks/store/user";
// services
import { sharingService } from "@/services/sharing.service";
// store
import type { TPageInstance } from "@/store/pages/base-page";
// local imports
import { SharingPanel } from "./sharing-panel";

type Props = {
  page: TPageInstance;
};

/** "Permissions" button in the page header; opens the sharing settings. */
export const PageSharingControl = observer(function PageSharingControl({ page }: Props) {
  const { t } = useTranslation();
  const { workspaceSlug, projectId: routeProjectId } = useParams();
  const { data: currentUser } = useUser();
  const [isOpen, setIsOpen] = useState(false);
  const projectId = routeProjectId?.toString() ?? page.project_ids?.[0];
  const item =
    page.id && projectId && workspaceSlug
      ? { kind: "page" as const, workspaceSlug: workspaceSlug.toString(), projectId, itemId: page.id }
      : null;
  // shares the cache key with SharingPanel, so the badge updates after a change
  const { data } = useSWR(item ? `SHARING_page_${item.itemId}` : null, () => sharingService.getSharing(item!), {
    revalidateOnFocus: false,
  });

  if (!item) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="flex h-6 items-center gap-1 rounded-sm px-2 text-11 font-medium text-secondary transition-colors hover:bg-layer-1 hover:text-primary"
        aria-haspopup="dialog"
      >
        <Lock className="size-3.5 flex-shrink-0" />
        <span>{data?.restricted ? t("sharing.restricted_badge") : t("sharing.title")}</span>
      </button>
      <ModalCore isOpen={isOpen} handleClose={() => setIsOpen(false)} position={EModalPosition.TOP} width={EModalWidth.LG}>
        <div className="flex flex-col gap-4 p-5 text-left">
          <div className="flex items-center justify-between">
            <h3 className="text-body-md-medium text-primary">{t("sharing.title")}</h3>
            <button
              type="button"
              aria-label={t("close")}
              onClick={() => setIsOpen(false)}
              className="grid size-6 place-items-center rounded-sm text-tertiary hover:bg-layer-1 hover:text-primary"
            >
              <X className="size-4" />
            </button>
          </div>
          <SharingPanel item={item} isCreator={!!currentUser?.id && currentUser.id === page.owned_by} />
        </div>
      </ModalCore>
    </>
  );
});
