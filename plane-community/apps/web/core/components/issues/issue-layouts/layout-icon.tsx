/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import {
  ListLayoutIcon,
  BoardLayoutIcon,
  CalendarLayoutIcon,
  SheetLayoutIcon,
  TimelineLayoutIcon,
} from "@plane/propel/icons";
import { LayoutGrid } from "lucide-react";
import type { ISvgIcons } from "@plane/propel/icons";
import { FileText } from "lucide-react";
import { EIssueLayoutTypes } from "@plane/types";

export function IssueLayoutIcon({
  layout,
  size,
  ...props
}: { layout: EIssueLayoutTypes; size?: number } & Omit<ISvgIcons, "width" | "height">) {
  const iconProps = {
    ...props,
    ...(size && { width: size, height: size }),
  };

  switch (layout) {
    case EIssueLayoutTypes.LIST:
      return <ListLayoutIcon {...iconProps} />;
    case EIssueLayoutTypes.PAGE_LIST:
      return <FileText width={size ?? 16} height={size ?? 16} className={props.className} />;
    case EIssueLayoutTypes.KANBAN:
      return <BoardLayoutIcon {...iconProps} />;
    case EIssueLayoutTypes.CALENDAR:
      return <CalendarLayoutIcon {...iconProps} />;
    case EIssueLayoutTypes.SPREADSHEET:
      return <SheetLayoutIcon {...iconProps} />;
    case EIssueLayoutTypes.GANTT:
      return <TimelineLayoutIcon {...iconProps} />;
    case EIssueLayoutTypes.GALLERY:
      return <LayoutGrid width={size ?? 16} height={size ?? 16} className={props.className} />;
    default:
      return null;
  }
}
