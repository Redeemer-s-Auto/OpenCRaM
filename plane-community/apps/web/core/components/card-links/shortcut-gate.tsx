/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { CornerUpRight } from "lucide-react";
import { Loader } from "@plane/ui";
import { useAppRouter } from "@/hooks/use-app-router";
import type { TCardResolution } from "@/services/card-links.service";
import { cardLinksService } from "@/services/card-links.service";
import { UnavailableCard } from "./card-link-chip";
import { linkedCardHref, setShortcutTarget } from "./store";

type Props = {
  workspaceSlug: string;
  issueId: string;
  children: React.ReactNode;
};

/**
 * On a card's own page: a shortcut card sends the person to the card it points to.
 * If they may not see that card (or it was deleted) the page says only "Hidden card"
 * or "Card removed". Normal cards render as usual.
 */
export const ShortcutGate = observer(function ShortcutGate(props: Props) {
  const { workspaceSlug, issueId, children } = props;
  const router = useAppRouter();
  const [state, setState] = useState<{ issueId: string; target: TCardResolution | null } | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    cardLinksService
      .shortcutInfo(workspaceSlug, issueId)
      .then((info) => {
        if (!alive) return;
        const target = info?.is_shortcut ? info.target : null;
        if (target) setShortcutTarget(issueId, target);
        setState({ issueId, target });
      })
      .catch(() => alive && setState({ issueId, target: null }));
    return () => {
      alive = false;
    };
  }, [workspaceSlug, issueId]);

  const current = state?.issueId === issueId ? state : undefined;
  const target = current?.target;

  useEffect(() => {
    if (target?.status === "visible") router.replace(linkedCardHref(workspaceSlug, target.card));
  }, [target, router, workspaceSlug]);

  if (!current || target?.status === "visible") {
    return (
      <Loader className="flex h-full flex-col gap-3 p-5">
        <Loader.Item height="30px" width="40%" />
        <Loader.Item height="15px" width="60%" />
      </Loader>
    );
  }
  if (!target) return <>{children}</>;
  return (
    <div className="flex h-full w-full items-center justify-center p-8" data-shortcut-gate={target.status}>
      <div className="flex max-w-sm flex-col items-center gap-3 text-center">
        <CornerUpRight className="size-6 text-placeholder" />
        <UnavailableCard status={target.status} className="text-15" />
        <p className="text-13 text-tertiary">
          {target.status === "hidden"
            ? "This shortcut points to a card you do not have access to."
            : "The card this shortcut pointed to was deleted."}
        </p>
      </div>
    </div>
  );
});
