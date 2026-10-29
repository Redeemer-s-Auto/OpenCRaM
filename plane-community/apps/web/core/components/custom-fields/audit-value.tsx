/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import type { TCustomField, TCustomFieldValue } from "@plane/types";
import { cn } from "@plane/utils";
// hooks
import { useMember } from "@/hooks/store/use-member";
// local
import { formatCustomFieldValue } from "./helpers";

type Props = {
  field: TCustomField;
  value: TCustomFieldValue | undefined;
  variant?: "sidebar" | "cell";
};

/** Created time, last edited time, created by, last edited by: plain text, never an input. */
export const AuditValue = observer(function AuditValue(props: Props) {
  const { field, value, variant = "sidebar" } = props;
  const { getUserDetails } = useMember();
  const text = formatCustomFieldValue(field, value, (userId) => getUserDetails(userId)?.display_name);
  return (
    <span
      className={cn("block w-full truncate px-2 py-1 text-body-xs-regular", !text && "text-placeholder")}
      title={text}
    >
      {text || (variant === "cell" ? "" : "Empty")}
    </span>
  );
});
