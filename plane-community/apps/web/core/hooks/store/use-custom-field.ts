/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useContext } from "react";
// mobx store
import { StoreContext } from "@/lib/store-context";
// types
import type { ICustomFieldStore } from "@/store/custom-field.store";

export const useCustomField = (): ICustomFieldStore => {
  const context = useContext(StoreContext);
  if (context === undefined) throw new Error("useCustomField must be used within StoreProvider");
  return context.customField;
};
