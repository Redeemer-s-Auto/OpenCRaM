/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { Repeat } from "lucide-react";
import useSWR from "swr";
// plane imports
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { cn, generateWorkItemLink } from "@plane/utils";
// hooks
import { useProject } from "@/hooks/store/use-project";
// services
import type { TIssueRef, TIssueRepeat, TRepeatFrequency } from "@/services/repeat.service";
import { repeatService } from "@/services/repeat.service";
// local
import type { TRepeatDraft } from "./helpers";
import {
  LAST_DAY,
  WEEKDAYS,
  defaultDraft,
  describeRule,
  draftFromRule,
  formatRunTime,
  ordinal,
  payloadFromDraft,
  unitName,
} from "./helpers";
import { refreshRepeatingIssues } from "./use-repeating-issues";

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled: boolean;
};

const inputClass =
  "rounded-md border border-subtle bg-layer-1 px-2 py-1 text-body-xs-regular text-primary outline-none focus:border-accent-strong disabled:opacity-60";
const buttonClass = "rounded-md px-2.5 py-1 text-body-xs-medium disabled:opacity-60";

function errorMessage(error: unknown) {
  if (error && typeof error === "object") {
    const first = Object.values(error as Record<string, unknown>)[0];
    if (typeof first === "string") return first;
    if (Array.isArray(first) && typeof first[0] === "string") return first[0];
  }
  return "The repeat could not be saved.";
}

const IssueLink = observer(function IssueLink(props: { workspaceSlug: string; issue: TIssueRef }) {
  const { workspaceSlug, issue } = props;
  const { getProjectById } = useProject();
  const identifier = getProjectById(issue.project_id)?.identifier;
  const href = generateWorkItemLink({
    workspaceSlug,
    projectId: issue.project_id,
    issueId: issue.id,
    projectIdentifier: identifier,
    sequenceId: issue.sequence_id,
  });
  return (
    <Link href={href} className="truncate text-accent-primary hover:underline">
      {issue.name}
    </Link>
  );
});

/** "Repeat" section for the card side panel and the peek view. */
export const IssueRepeatSection = observer(function IssueRepeatSection(props: Props) {
  const { workspaceSlug, projectId, issueId, disabled } = props;
  const swrKey = `ISSUE_REPEAT_${issueId}`;
  const { data, error, mutate } = useSWR<TIssueRepeat>(
    swrKey,
    () => repeatService.getRepeat(workspaceSlug, projectId, issueId),
    { revalidateOnFocus: false, shouldRetryOnError: false }
  );
  const [draft, setDraft] = useState<TRepeatDraft | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const rule = data?.rule ?? null;
  const active = !!rule?.is_active;
  const set = (patch: Partial<TRepeatDraft>) => setDraft((current) => (current ? { ...current, ...patch } : current));

  const finish = async (next: TIssueRepeat) => {
    await mutate(next, false);
    void refreshRepeatingIssues(projectId);
  };

  const save = async () => {
    if (!draft) return;
    setIsSaving(true);
    try {
      await finish(await repeatService.setRepeat(workspaceSlug, projectId, issueId, payloadFromDraft(draft)));
      setDraft(null);
    } catch (error) {
      setToast({ type: TOAST_TYPE.ERROR, title: "Repeat not saved", message: errorMessage(error) });
    } finally {
      setIsSaving(false);
    }
  };

  const stop = async () => {
    setIsSaving(true);
    try {
      await finish(await repeatService.stopRepeat(workspaceSlug, projectId, issueId));
      setDraft(null);
    } catch (error) {
      setToast({ type: TOAST_TYPE.ERROR, title: "Repeat not stopped", message: errorMessage(error) });
    } finally {
      setIsSaving(false);
    }
  };

  const toggleWeekday = (day: number) => {
    if (!draft) return;
    const days = new Set(draft.weekdays ?? []);
    if (days.has(day)) days.delete(day);
    else days.add(day);
    if (days.size) set({ weekdays: [...days].sort((a, b) => a - b) });
  };

  // Guests (and anyone the server turns away) see no Repeat section.
  if (error) return null;

  return (
    <section className="mt-5 border-t border-subtle-1 pt-4" aria-label="Repeat">
      <h5 className="mb-3 flex items-center gap-1.5 text-body-xs-medium">
        <Repeat className="size-3.5" />
        Repeat
      </h5>

      {!data && <div className="h-10 animate-pulse rounded-md bg-layer-1" />}

      {data?.copy_of && (
        <p className="mb-2 flex min-w-0 flex-wrap gap-1 text-body-xs-regular text-tertiary">
          <span>Made by a repeat on {formatRunTime(data.copy_of.scheduled_for)} from</span>
          {data.copy_of.template ? (
            <IssueLink workspaceSlug={workspaceSlug} issue={data.copy_of.template} />
          ) : (
            <span>a card you cannot see.</span>
          )}
        </p>
      )}

      {data && !draft && (
        <div className={cn("flex flex-col gap-2 text-body-xs-regular", isSaving && "opacity-80")}>
          {active && rule ? (
            <>
              <p className="text-primary">{describeRule(rule)}</p>
              <p className="text-secondary">
                Next copy: {rule.next_run_at ? formatRunTime(rule.next_run_at, rule.timezone) : "none"}
              </p>
              <p className="text-tertiary">
                Time zone {rule.timezone}. {rule.created_count} made so far
                {rule.max_count ? ` of ${rule.max_count}` : ""}
                {rule.end_date ? `, ends ${rule.end_date}` : ""}. Copies are made as {rule.owner?.name || "the person who set it"}.
              </p>
            </>
          ) : (
            <p className="text-tertiary">
              {rule?.stop_reason ? `Not repeating. ${rule.stop_reason}` : "This card does not repeat."}
            </p>
          )}

          {!!rule?.recent_copies?.length && (
            <div className="flex flex-col gap-1">
              <span className="text-tertiary">Latest copies</span>
              {rule.recent_copies.map((copy) => (
                <IssueLink key={copy.id} workspaceSlug={workspaceSlug} issue={copy} />
              ))}
            </div>
          )}

          {!disabled && (
            <div className="flex gap-2">
              <button
                type="button"
                className={cn(buttonClass, "bg-layer-3 text-primary hover:bg-layer-2")}
                onClick={() => setDraft(active && rule ? draftFromRule(rule) : defaultDraft())}
                disabled={isSaving}
              >
                {active ? "Change" : "Set repeat"}
              </button>
              {active && (
                <button
                  type="button"
                  className={cn(buttonClass, "text-danger-primary hover:bg-layer-2")}
                  onClick={() => void stop()}
                  disabled={isSaving}
                >
                  Stop repeating
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {draft && (
        <form
          className="flex flex-col gap-2.5 text-body-xs-regular"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <label className="flex items-center gap-2">
            <span className="w-14 text-tertiary">Repeat</span>
            <select
              className={inputClass}
              value={draft.frequency}
              onChange={(e) => set({ frequency: e.target.value as TRepeatFrequency })}
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>

          <label className="flex items-center gap-2">
            <span className="w-14 text-tertiary">Every</span>
            <input
              type="number"
              min={1}
              max={365}
              className={cn(inputClass, "w-16")}
              value={draft.interval}
              onChange={(e) => set({ interval: Number(e.target.value) })}
            />
            <span className="text-secondary">{unitName(draft.frequency, Number(draft.interval) || 1)}</span>
          </label>

          {draft.frequency === "weekly" && (
            <div className="flex items-center gap-2">
              <span className="w-14 text-tertiary">On</span>
              <div className="flex gap-1" role="group" aria-label="Days of the week">
                {WEEKDAYS.map((day) => {
                  const on = draft.weekdays?.includes(day.value);
                  return (
                    <button
                      key={day.value}
                      type="button"
                      aria-pressed={on}
                      aria-label={day.name}
                      title={day.name}
                      onClick={() => toggleWeekday(day.value)}
                      className={cn(
                        "grid size-6 place-items-center rounded-full border text-caption-md-medium",
                        on ? "border-accent-strong bg-accent-primary text-on-color" : "border-subtle text-secondary"
                      )}
                    >
                      {day.short}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {draft.frequency === "monthly" && (
            <label className="flex items-center gap-2">
              <span className="w-14 text-tertiary">On</span>
              <select
                className={inputClass}
                value={draft.month_day ?? 1}
                onChange={(e) => set({ month_day: Number(e.target.value) })}
              >
                {Array.from({ length: 31 }, (_, i) => i + 1).map((day) => (
                  <option key={day} value={day}>
                    the {ordinal(day)}
                  </option>
                ))}
                <option value={LAST_DAY}>the last day</option>
              </select>
            </label>
          )}

          <label className="flex items-center gap-2">
            <span className="w-14 text-tertiary">At</span>
            <input
              type="time"
              className={inputClass}
              value={draft.time_of_day}
              onChange={(e) => set({ time_of_day: e.target.value })}
              required
            />
          </label>

          <label className="flex items-center gap-2">
            <span className="w-14 text-tertiary">Starts</span>
            <input
              type="date"
              className={inputClass}
              value={draft.start_date ?? ""}
              onChange={(e) => set({ start_date: e.target.value })}
              required
            />
          </label>

          <div className="flex flex-wrap items-center gap-2">
            <span className="w-14 text-tertiary">Ends</span>
            <select
              className={inputClass}
              value={draft.end_mode}
              onChange={(e) => set({ end_mode: e.target.value as TRepeatDraft["end_mode"] })}
            >
              <option value="never">Never</option>
              <option value="on">On a date</option>
              <option value="after">After a number of copies</option>
            </select>
            {draft.end_mode === "on" && (
              <input
                type="date"
                aria-label="End date"
                className={inputClass}
                value={draft.end_date ?? ""}
                min={draft.start_date}
                onChange={(e) => set({ end_date: e.target.value })}
                required
              />
            )}
            {draft.end_mode === "after" && (
              <input
                type="number"
                aria-label="Number of copies"
                min={1}
                className={cn(inputClass, "w-20")}
                value={draft.max_count ?? 1}
                onChange={(e) => set({ max_count: Number(e.target.value) })}
                required
              />
            )}
          </div>

          <p className="text-tertiary">
            Each run makes a new copy of this card (with its fields, labels, people and sub-cards). Due dates keep the
            same distance from the run day as this card&apos;s dates have from the start day.
          </p>

          <div className="flex gap-2">
            <button
              type="submit"
              className={cn(buttonClass, "bg-accent-primary text-on-color hover:bg-accent-primary/90")}
              disabled={isSaving}
            >
              Save
            </button>
            <button
              type="button"
              className={cn(buttonClass, "text-secondary hover:bg-layer-2")}
              onClick={() => setDraft(null)}
              disabled={isSaving}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
});
