/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React, { useState, useEffect, useMemo } from "react";
import { observer } from "mobx-react";
// plane imports
import type {
  IFilterOption,
  TFilterProperty,
  TSingleSelectFilterFieldConfig,
  TFilterConditionNodeForDisplay,
} from "@plane/types";
import { CustomSearchSelect } from "@plane/ui";
// local imports
import { SelectedOptionsDisplay } from "./selected-options-display";
import { getCommonCustomSearchSelectProps, getFormattedOptions, loadOptions } from "./shared";

type TSingleSelectFilterValueInputProps<P extends TFilterProperty> = {
  config: TSingleSelectFilterFieldConfig<string>;
  condition: TFilterConditionNodeForDisplay<P, string>;
  isDisabled?: boolean;
  onChange: (value: string | null) => void;
};

export const SingleSelectFilterValueInput = observer(function SingleSelectFilterValueInput<P extends TFilterProperty>(
  props: TSingleSelectFilterValueInputProps<P>
) {
  const { config, condition, onChange, isDisabled } = props;
  // states
  const [options, setOptions] = useState<IFilterOption<string>[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  // derived values
  const formattedOptions = useMemo(() => getFormattedOptions<string>(options), [options]);
  // A saved value can be a real boolean (checkbox filters store false/true) while the options
  // use string ids "true"/"false". Compare as strings, and treat only null/undefined/"" as empty,
  // so a saved false shows "Not checked" and does not start open.
  const rawValue = condition.value as unknown;
  const value: string | undefined =
    rawValue === null || rawValue === undefined || rawValue === "" ? undefined : String(rawValue);

  useEffect(() => {
    loadOptions({ config, setOptions, setLoading });
  }, [config]);

  const handleSelectChange = (selected: string) => {
    if (selected === value) {
      onChange(null);
    } else {
      onChange(selected);
    }
  };

  return (
    <CustomSearchSelect
      {...getCommonCustomSearchSelectProps(isDisabled)}
      value={value}
      onChange={handleSelectChange}
      options={formattedOptions}
      multiple={false}
      disabled={loading || isDisabled}
      customButton={<SelectedOptionsDisplay<string> selectedValue={value as string} options={options} displayCount={1} />}
      defaultOpen={value === undefined}
    />
  );
});
