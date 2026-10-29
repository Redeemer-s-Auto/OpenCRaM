/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import { Bell, CalendarDays } from "lucide-react";
import useSWR from "swr";
import { formatDateMentionLabel } from "@plane/editor";
import type { TDateMentionRenderProps } from "@plane/editor";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { cn } from "@plane/utils";
// components
import { useInlineViewHost } from "@/components/inline-views/host-context";
// services
import { DateReminderService } from "@/services/date-reminder.service";

const service = new DateReminderService();

/** How long before the date a reminder goes off, in minutes. */
const REMINDER_CHOICES = [
  { value: "", label: "No reminder" },
  { value: "0", label: "At the time" },
  { value: "5", label: "5 minutes before" },
  { value: "15", label: "15 minutes before" },
  { value: "60", label: "1 hour before" },
  { value: "1440", label: "1 day before" },
  { value: "2880", label: "2 days before" },
  { value: "10080", label: "1 week before" },
];

const todayString = () => {
  const now = new Date();
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
};

/** The first message in a server error, for a toast. */
const errorText = (error: unknown): string => {
  const data = error as Record<string, unknown> | undefined;
  if (!data) return "Something went wrong.";
  if (typeof data.error === "string") return data.error;
  for (const value of Object.values(data)) {
    if (typeof value === "string") return value;
    if (Array.isArray(value) && typeof value[0] === "string") return value[0];
  }
  return "Something went wrong.";
};

/** A date in the text. Click it to change the date or time, or to ask for a reminder. */
export const DateMentionChip = observer(function DateMentionChip(props: TDateMentionRenderProps) {
  const { date, time, mentionId, update, remove, editable } = props;
  const host = useInlineViewHost();
  const slug = host?.workspaceSlug;
  const issueId = host?.issueId;
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLSpanElement>(null);
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";

  const { data: reminders, mutate } = useSWR(
    slug && issueId && mentionId ? ["date-reminders", slug, issueId] : null,
    () => service.list(slug as string, issueId as string),
    { shouldRetryOnError: false, revalidateOnFocus: false }
  );
  const mine = reminders?.find((r) => r.mention_id === mentionId);
  const waiting = !!mine && !mine.sent_at && !mine.stopped;

  // Close when the click lands outside.
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const changeWhen = (next: { date: string; time: string }) => {
    if (!next.date) return;
    update(next);
    if (slug && issueId && mentionId)
      service
        .move(slug, mentionId, { issue_id: issueId, date: next.date, time: next.time || null, tz: timezone })
        .then(() => mutate())
        .catch(() => undefined); // only people who can edit the card move reminders; others just change nothing
  };

  const changeReminder = async (value: string) => {
    if (!slug || !issueId || !mentionId) return;
    try {
      if (value === "") await service.remove(slug, mentionId);
      else
        await service.set(slug, mentionId, {
          issue_id: issueId,
          date,
          time: time || null,
          tz: timezone,
          offset_minutes: Number(value),
        });
      await mutate();
    } catch (error) {
      setToast({ type: TOAST_TYPE.ERROR, title: "Reminder not saved", message: errorText(error) });
    }
  };

  const overdue = date !== "" && date < todayString();
  return (
    <span ref={rootRef} className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "inline-flex items-center gap-1 rounded-sm bg-layer-1 px-1 text-[0.95em] hover:bg-layer-1-hover",
          overdue ? "text-danger-primary" : "text-secondary"
        )}
        title={mine ? "You have a reminder on this date" : "Date"}
      >
        <CalendarDays className="size-3 shrink-0" />
        {formatDateMentionLabel(date, time)}
        {waiting && <Bell className="size-3 shrink-0 text-accent-primary" aria-label="Reminder set" />}
      </button>
      {open && (
        <span
          className="shadow-lg absolute top-full left-0 z-20 mt-1 flex w-64 flex-col gap-2 rounded-md border border-subtle bg-surface-1 p-3 text-body-xs-regular"
          contentEditable={false}
        >
          <label className="flex flex-col gap-1">
            <span className="text-tertiary">Date</span>
            <input
              type="date"
              value={date}
              disabled={!editable}
              onChange={(e) => changeWhen({ date: e.target.value, time })}
              className="rounded-sm border border-subtle bg-transparent px-1.5 py-0.5"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="flex items-center justify-between text-tertiary">
              Time (optional)
              {time && editable && (
                <button
                  type="button"
                  className="text-11 hover:underline"
                  onClick={() => changeWhen({ date, time: "" })}
                >
                  No time
                </button>
              )}
            </span>
            <input
              type="time"
              value={time}
              disabled={!editable}
              onChange={(e) => changeWhen({ date, time: e.target.value })}
              className="rounded-sm border border-subtle bg-transparent px-1.5 py-0.5"
            />
          </label>
          {issueId ? (
            <label className="flex flex-col gap-1">
              <span className="text-tertiary">Remind me (only you)</span>
              <select
                value={mine ? String(mine.offset_minutes) : ""}
                onChange={(e) => void changeReminder(e.target.value)}
                className="rounded-sm border border-subtle bg-surface-1 px-1.5 py-0.5"
              >
                {REMINDER_CHOICES.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
              {!time && <span className="text-11 text-tertiary">A date with no time reminds at 9:00 AM.</span>}
              {mine?.sent_at && (
                <span className="text-11 text-tertiary">Reminder sent. Pick a time to set it again.</span>
              )}
              {mine?.stopped && <span className="text-11 text-danger-primary">Stopped: {mine.stop_reason}</span>}
            </label>
          ) : (
            <span className="text-11 text-tertiary">Reminders work on dates inside a card.</span>
          )}
          <span className="flex items-center justify-between">
            {editable ? (
              <button type="button" className="text-11 text-danger-primary hover:underline" onClick={remove}>
                Remove date
              </button>
            ) : (
              <span />
            )}
            <button type="button" className="text-11 text-secondary hover:underline" onClick={() => setOpen(false)}>
              Done
            </button>
          </span>
        </span>
      )}
    </span>
  );
});
