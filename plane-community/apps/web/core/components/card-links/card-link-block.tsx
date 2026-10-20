/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { X } from "lucide-react";
import type { TCardLinkHandler, TCardLinkRenderProps } from "@plane/editor";
import { cn } from "@plane/utils";
import { cardLinksService } from "@/services/card-links.service";
import { CardLinkChip } from "./card-link-chip";
import { CardPicker } from "./card-picker";
import { rememberCard, useCardResolution } from "./store";

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";

/** The card behind an address of this app: /<slug>/browse/ABC-12/ or /<slug>/projects/<id>/issues/<id>. */
function parseCardUrl(workspaceSlug: string, text: string): { cardId?: string; identifier?: string } | null {
  let url: URL;
  try {
    url = new URL(text, window.location.origin);
  } catch {
    return null;
  }
  if (url.origin !== window.location.origin) return null;
  const slug = workspaceSlug.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const browse = url.pathname.match(new RegExp(`^/${slug}/browse/([A-Za-z0-9]{1,12}-\\d{1,9})/?$`));
  if (browse) return { identifier: browse[1] };
  const direct = url.pathname.match(new RegExp(`^/${slug}/projects/${UUID}/(?:archives/)?issues/(${UUID})/?$`, "i"));
  if (direct) return { cardId: direct[1].toLowerCase() };
  return null;
}

const CardLinkBlock = observer(function CardLinkBlock(props: TCardLinkRenderProps & { workspaceSlug: string }) {
  const { workspaceSlug, cardId, editable, selected, onPick, onRemove } = props;
  const resolution = useCardResolution(workspaceSlug, cardId);

  if (!cardId) {
    if (!editable) return null;
    return (
      <div className="my-1" contentEditable={false}>
        <CardPicker
          workspaceSlug={workspaceSlug}
          onPick={(card) => {
            rememberCard(card);
            onPick(card.id);
          }}
          onCancel={onRemove}
        />
      </div>
    );
  }

  return (
    <div className={cn("group/card-link relative my-1 flex items-center", { "rounded-md ring-1 ring-accent-strong": selected })} contentEditable={false}>
      <CardLinkChip workspaceSlug={workspaceSlug} resolution={resolution} />
      {editable && (
        <button
          type="button"
          aria-label="Remove link"
          onClick={onRemove}
          className="absolute right-1 top-1/2 hidden -translate-y-1/2 rounded-sm bg-layer-1 p-0.5 text-placeholder hover:text-secondary group-hover/card-link:block"
        >
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
});

/** What the editor needs to show "Link to card" blocks in a card body. */
export function getCardLinkHandler(workspaceSlug: string): TCardLinkHandler {
  return {
    renderComponent: (props) => <CardLinkBlock {...props} workspaceSlug={workspaceSlug} />,
    isCardUrl: (text) => parseCardUrl(workspaceSlug, text) !== null,
    cardIdFromUrl: async (text) => {
      const parsed = parseCardUrl(workspaceSlug, text);
      if (!parsed) return null;
      if (parsed.cardId) {
        const results = await cardLinksService.resolve(workspaceSlug, [parsed.cardId]);
        const value = results[parsed.cardId];
        if (value?.status !== "visible") return null;
        rememberCard(value.card);
        return parsed.cardId;
      }
      const found = await cardLinksService.search(workspaceSlug, parsed.identifier ?? "", 1);
      const card = found[0];
      if (!card) return null;
      rememberCard(card);
      return card.id;
    },
  };
}
