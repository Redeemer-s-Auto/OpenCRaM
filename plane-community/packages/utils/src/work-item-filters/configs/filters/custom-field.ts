/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import type { IUserLite, TCustomField, TCustomFieldOption, TFilterConfig, TFilterProperty } from "@plane/types";
import { COLLECTION_OPERATOR, EQUALITY_OPERATOR } from "@plane/types";
// local imports
import type { IFilterIconConfig, TCreateDateFilterParams, TCreateFilterConfigParams } from "../../../rich-filters";
import {
  createFilterConfig,
  createOperatorConfigEntry,
  getMemberMultiSelectConfig,
  getMultiSelectConfig,
  getSingleSelectConfig,
} from "../../../rich-filters";
import { getSupportedDateOperators } from "./shared";

/** Field types the filter menu supports today. Text and numbers come later. */
export const FILTERABLE_CUSTOM_FIELD_TYPES = ["date", "checkbox", "select", "multi_select", "label", "person"];

export type TCreateCustomFieldFilterParams = TCreateFilterConfigParams &
  IFilterIconConfig<string> & {
    field: TCustomField;
    /** Workspace or project members, for person fields. */
    members: IUserLite[];
    getMemberIcon?: (member: IUserLite) => React.ReactNode;
  };

/** Filter key for a field: customfield_<field id>. */
export const getCustomFieldFilterKey = (fieldId: string) => `customfield_${fieldId}`;

/**
 * Filter config for one custom field, or undefined when its type has no filter yet.
 * The server reads keys as customfield_<id>__<operator>.
 */
export const getCustomFieldFilterConfig = <P extends TFilterProperty>(
  key: P,
  params: TCreateCustomFieldFilterParams
): TFilterConfig<P> | undefined => {
  const { field } = params;
  const base = { id: key, label: field.name, ...params, icon: params.filterIcon };
  // A formula filters as its result type.
  const type = field.field_type === "formula" ? (field.settings?.result_type ?? "number") : field.field_type;

  switch (type) {
    case "date":
      return createFilterConfig<P>({
        ...base,
        allowMultipleFilters: true,
        supportedOperatorConfigsMap: getSupportedDateOperators(params as TCreateDateFilterParams),
      });

    case "checkbox":
      return createFilterConfig<P>({
        ...base,
        supportedOperatorConfigsMap: new Map([
          createOperatorConfigEntry(EQUALITY_OPERATOR.EXACT, params, (updatedParams) =>
            getSingleSelectConfig<{ id: string; label: string }, string>(
              {
                items: [
                  { id: "true", label: "Checked" },
                  { id: "false", label: "Not checked" },
                ],
                getId: (item) => item.id,
                getLabel: (item) => item.label,
                getValue: (item) => item.id,
              },
              { ...updatedParams }
            )
          ),
        ]),
      });

    case "select":
    case "multi_select":
    case "label":
      return createFilterConfig<P>({
        ...base,
        supportedOperatorConfigsMap: new Map([
          createOperatorConfigEntry(COLLECTION_OPERATOR.IN, params, (updatedParams) =>
            getMultiSelectConfig<TCustomFieldOption, string, string>(
              {
                items: field.options,
                getId: (option) => option.id,
                getLabel: (option) => option.name,
                getValue: (option) => option.id,
                getIconData: (option) => option.color,
              },
              { singleValueOperator: EQUALITY_OPERATOR.EXACT, ...updatedParams },
              { getOptionIcon: params.getOptionIcon }
            )
          ),
        ]),
      });

    case "person":
      return createFilterConfig<P>({
        ...base,
        supportedOperatorConfigsMap: new Map([
          createOperatorConfigEntry(COLLECTION_OPERATOR.IN, params, (updatedParams) =>
            getMemberMultiSelectConfig(
              { ...updatedParams, members: params.members, getOptionIcon: params.getMemberIcon },
              EQUALITY_OPERATOR.EXACT
            )
          ),
        ]),
      });

    default:
      return undefined;
  }
};
