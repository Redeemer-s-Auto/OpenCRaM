/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactElement, SyntheticEvent } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import { CheckSquare } from "lucide-react";
import { Tooltip } from "@plane/propel/tooltip";
import type { IIssueDisplayProperties, TCustomField, TCustomFieldValue, TIssue } from "@plane/types";
import { EIssueLayoutTypes } from "@plane/types";
import { CustomSearchSelect } from "@plane/ui";
import { cn } from "@plane/utils";
// components
import { ButtonAvatars } from "@/components/dropdowns/member/avatar";
// hooks
import { useCustomField } from "@/hooks/store/use-custom-field";
import { useMember } from "@/hooks/store/use-member";
import { usePlatformOS } from "@/hooks/use-platform-os";
// local
import { effectiveFieldType, formatCustomFieldValue, getFieldTypeDetails, isEmptyValue, linkedCards } from "./helpers";
import { buildCustomFieldsPayload } from "./issue-properties";
import { OptionChip } from "./value-input";

/**
 * Board and list cards show a custom field only when it is turned on for the view.
 * The key is separate from the table column key (customfield_<id>, on by default)
 * because one view keeps one set of display properties for every layout.
 */
export const cardFaceDisplayKey = (fieldId: string) => `cardfield_${fieldId}` as const;

export const isCustomFieldOnCardFace = (displayProperties: IIssueDisplayProperties | undefined, fieldId: string) =>
  displayProperties?.[cardFaceDisplayKey(fieldId)] === true;

/** Layouts whose cards use the card face keys. */
export const CARD_FACE_LAYOUTS: string[] = [EIssueLayoutTypes.KANBAN, EIssueLayoutTypes.LIST];

const chipClass =
  "flex h-5 max-w-48 flex-shrink-0 items-center gap-1 overflow-hidden rounded-sm border-[0.5px] border-strong px-2 text-caption-sm-regular text-tertiary";

const stop = (e: SyntheticEvent) => {
  e.stopPropagation();
  e.preventDefault();
};

type TUpdate = ((projectId: string | null, issueId: string, data: Partial<TIssue>) => Promise<void>) | undefined;

type Props = {
  issue: TIssue;
  displayProperties: IIssueDisplayProperties | undefined;
  updateIssue: TUpdate;
  isReadOnly: boolean;
};

/** Custom field values on a board card or list row, for the fields turned on in Display. */
export const CustomFieldCardFaces = observer(function CustomFieldCardFaces(props: Props) {
  const { issue, displayProperties, updateIssue, isReadOnly } = props;
  const { projectId } = useParams();
  const { getProjectFields } = useCustomField();
  // Fields of the card's own board (workspace views mix boards); fall back to the board in the URL.
  const fields = getProjectFields(issue.project_id ?? projectId?.toString()) ?? [];
  const shown = fields.filter(
    (field) =>
      isCustomFieldOnCardFace(displayProperties, field.id) && hasCardValue(field, issue.custom_fields?.[field.id])
  );
  if (shown.length === 0) return null;

  return (
    <>
      {shown.map((field) => (
        <CardFaceValue key={field.id} field={field} issue={issue} updateIssue={isReadOnly ? undefined : updateIssue} />
      ))}
    </>
  );
});

/** Empty values (and an unticked checkbox) show nothing on a card. */
const hasCardValue = (field: TCustomField, value: TCustomFieldValue | undefined) => {
  if (isEmptyValue(value)) return false;
  if (effectiveFieldType(field) === "checkbox") return value === true;
  return true;
};

const CardFaceValue = observer(function CardFaceValue(props: {
  field: TCustomField;
  issue: TIssue;
  updateIssue: TUpdate;
}) {
  const { field, issue, updateIssue } = props;
  const { isMobile } = usePlatformOS();
  const { getUserDetails } = useMember();
  const value = issue.custom_fields?.[field.id];
  const Icon = getFieldTypeDetails(field.field_type).icon;
  const text = formatCustomFieldValue(field, value, (userId) => getUserDetails(userId)?.display_name);
  const save = (next: TCustomFieldValue) =>
    updateIssue?.(issue.project_id, issue.id, buildCustomFieldsPayload(issue.custom_fields, field.id, next));

  // Hover shows the field name and the full value (long text is cut short on the card).
  const withTooltip = (content: ReactElement, tooltip: string = text) => (
    <Tooltip tooltipHeading={field.name} tooltipContent={tooltip} isMobile={isMobile} renderByDefault={false}>
      {content}
    </Tooltip>
  );

  // Checkbox: a ticked box shows the field name; clicking it unticks.
  if (field.field_type === "checkbox") {
    const chip = (
      <span className={chipClass}>
        <CheckSquare className="size-3 flex-shrink-0" />
        <span className="truncate">{field.name}</span>
      </span>
    );
    if (!updateIssue) return withTooltip(chip, "Yes");
    return withTooltip(
      <button
        type="button"
        className={cn(chipClass, "hover:bg-layer-transparent-hover")}
        onClick={(e) => {
          stop(e);
          void save(false);
        }}
        aria-label={`Untick ${field.name}`}
      >
        <CheckSquare className="size-3 flex-shrink-0" />
        <span className="truncate">{field.name}</span>
      </button>,
      "Yes (click to untick)"
    );
  }

  // Dropdown: shows the picked option; pick another or clear it right on the card.
  if (field.field_type === "select") {
    const option = field.options.find((o) => o.id === value);
    if (!option) return null; // the picked option was deleted
    const chip = (
      <span className="flex h-5 max-w-48 items-center text-caption-sm-regular text-tertiary">
        <OptionChip name={option.name} color={option.color} />
      </span>
    );
    if (!updateIssue) return withTooltip(chip);
    return (
      // oxlint-disable-next-line jsx_a11y/click-events-have-key-events oxlint-disable-next-line jsx_a11y/no-static-element-interactions
      <div className="h-5" onClick={stop} onFocus={(e) => e.stopPropagation()}>
        <CustomSearchSelect
          value={(value as string) ?? null}
          onChange={(next: string | null) => void save(next === value ? null : next)}
          options={field.options.map((o) => ({
            value: o.id,
            query: o.name,
            content: <OptionChip name={o.name} color={o.color} />,
          }))}
          customButton={withTooltip(chip)}
          customButtonClassName="h-5"
          noChevron
        />
      </div>
    );
  }

  if (field.field_type === "person") {
    const ids = (Array.isArray(value) ? value : []) as string[];
    return withTooltip(
      <span className={cn(chipClass, "px-1")}>
        <ButtonAvatars showTooltip={false} userIds={ids} size="sm" />
      </span>
    );
  }

  if (field.field_type === "multi_select" || field.field_type === "label") {
    const picked = (Array.isArray(value) ? value : []) as string[];
    const options = picked.flatMap((id) => field.options.filter((o) => o.id === id));
    if (options.length === 0) return null;
    return withTooltip(
      <span className="flex h-5 max-w-48 items-center gap-1 overflow-hidden text-caption-sm-regular text-tertiary">
        {options.slice(0, 2).map((o) => (
          <OptionChip key={o.id} name={o.name} color={o.color} />
        ))}
        {options.length > 2 && <span className="flex-shrink-0">+{options.length - 2}</span>}
      </span>
    );
  }

  if (field.field_type === "relation") {
    const cards = linkedCards(value);
    const names = cards.map((card) => card.name).filter(Boolean);
    // Count, then the first two titles. Cards the viewer may not see are already left out by the server.
    const titles = `${names.slice(0, 2).join(", ")}${names.length > 2 ? ` +${names.length - 2}` : ""}`;
    return withTooltip(
      <span className={chipClass}>
        <Icon className="size-3 flex-shrink-0" />
        <span className="flex-shrink-0 text-secondary">{cards.length}</span>
        {titles && <span className="truncate">{titles}</span>}
      </span>,
      names.join(", ") || `${cards.length} linked`
    );
  }

  // Text, long text, number, money, date, link, formula, rollup: plain text, truncated.
  if (!text) return null;
  return withTooltip(
    <span className={chipClass}>
      <Icon className="size-3 flex-shrink-0" />
      <span className="truncate">{text}</span>
    </span>
  );
});
