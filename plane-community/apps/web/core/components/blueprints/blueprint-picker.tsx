/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import useSWR from "swr";
// hooks
import { useProject } from "@/hooks/store/use-project";
// services
import type { TBlueprint } from "@/services/blueprint.service";
import { blueprintService } from "@/services/blueprint.service";
// local
import { describeSummary } from "./helpers";

export type TBlueprintChoice = {
  blueprint: TBlueprint | null;
  relationTargets: Record<string, string>;
  includeSamples: boolean;
};

export const EMPTY_BLUEPRINT_CHOICE: TBlueprintChoice = { blueprint: null, relationTargets: {}, includeSamples: true };

type Props = {
  workspaceSlug: string;
  value: TBlueprintChoice;
  onChange: (value: TBlueprintChoice) => void;
};

const selectClass =
  "w-full rounded-md border border-subtle bg-layer-2 px-3 py-2 text-body-xs-regular text-primary outline-none focus:border-accent-strong";

/** "Start from: Blank board / a blueprint" in the new-board window. Hidden when there are no blueprints. */
export const BlueprintPicker = observer(function BlueprintPicker(props: Props) {
  const { workspaceSlug, value, onChange } = props;
  const { joinedProjectIds, getProjectById } = useProject();
  const { data: blueprints } = useSWR(`BOARD_BLUEPRINTS_${workspaceSlug}`, () => blueprintService.list(workspaceSlug), {
    revalidateOnFocus: false,
  });

  if (!blueprints || blueprints.length === 0) return null;
  const chosen = value.blueprint;

  return (
    <div className="flex flex-col gap-2 rounded-md border border-subtle bg-layer-1 p-3">
      <label className="flex flex-col gap-1">
        <span className="text-body-xs-medium text-secondary">Start from</span>
        <select
          className={selectClass}
          value={chosen?.id ?? ""}
          onChange={(e) => {
            const blueprint = blueprints.find((b) => b.id === e.target.value) ?? null;
            onChange({ blueprint, relationTargets: {}, includeSamples: true });
          }}
        >
          <option value="">Blank board</option>
          {blueprints.map((b) => (
            <option key={b.id} value={b.id}>
              Blueprint: {b.name} (v{b.version})
            </option>
          ))}
        </select>
      </label>
      {chosen && (
        <div className="flex flex-col gap-2 text-caption-md-regular text-tertiary">
          <p>
            {chosen.description ? `${chosen.description} ` : ""}
            The new board gets {describeSummary(chosen.summary)}.
            {chosen.summary.is_private ? " It will be private: only you, until you add people." : ""}
          </p>
          {chosen.summary.pick_boards.map((pick) => (
            <label key={pick.key} className="flex flex-col gap-1">
              <span className="text-body-xs-medium text-secondary">
                &quot;{pick.name}&quot; links to {pick.board_name ? `the board ${pick.board_name}` : "another board"}.
                Pick the board to link to:
              </span>
              <select
                className={selectClass}
                value={value.relationTargets[pick.key] ?? ""}
                onChange={(e) =>
                  onChange({ ...value, relationTargets: { ...value.relationTargets, [pick.key]: e.target.value } })
                }
              >
                <option value="">Leave this field out</option>
                {joinedProjectIds.map((id) => (
                  <option key={id} value={id}>
                    {getProjectById(id)?.name}
                  </option>
                ))}
              </select>
            </label>
          ))}
          {chosen.summary.sample_cards > 0 && (
            <label className="flex items-center gap-2 text-body-xs-regular text-secondary">
              <input
                type="checkbox"
                checked={value.includeSamples}
                onChange={(e) => onChange({ ...value, includeSamples: e.target.checked })}
              />
              Add the {chosen.summary.sample_cards} sample card(s)
            </label>
          )}
        </div>
      )}
    </div>
  );
});
