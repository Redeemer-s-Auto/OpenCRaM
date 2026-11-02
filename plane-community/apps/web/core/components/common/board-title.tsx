/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { observer } from "mobx-react";
// hooks
import { useProject } from "@/hooks/store/use-project";

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
 */
export const BoardTitle = observer(function BoardTitle(props: Props) {
  const { projectId, suffix, children } = props;
  const { getPartialProjectById } = useProject();
  const name = projectId ? getPartialProjectById(projectId)?.name : undefined;

  return (
    <div className="flex max-w-full min-w-0 items-center gap-2">
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
