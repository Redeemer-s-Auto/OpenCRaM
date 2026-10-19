/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import type { TRepeatFrequency, TRepeatRule, TRepeatRuleInput } from "@/services/repeat.service";

/** 0 = Monday ... 6 = Sunday (same as the server). */
export const WEEKDAYS = [
  { value: 0, short: "M", name: "Mon" },
  { value: 1, short: "T", name: "Tue" },
  { value: 2, short: "W", name: "Wed" },
  { value: 3, short: "T", name: "Thu" },
  { value: 4, short: "F", name: "Fri" },
  { value: 5, short: "S", name: "Sat" },
  { value: 6, short: "S", name: "Sun" },
];

export const LAST_DAY = -1;

const UNIT: Record<TRepeatFrequency, [string, string]> = {
  daily: ["day", "days"],
  weekly: ["week", "weeks"],
  monthly: ["month", "months"],
};

export const unitName = (frequency: TRepeatFrequency, interval: number) => UNIT[frequency][interval === 1 ? 0 : 1];

/** JS Date.getDay() is 0 = Sunday; the server's weekday is 0 = Monday. */
export const serverWeekday = (date: Date) => (date.getDay() + 6) % 7;

export const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export const ordinal = (n: number) => {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
};

const formatClock = (hhmm: string) => {
  const [h, m] = hhmm.split(":").map(Number);
  const hour12 = h % 12 === 0 ? 12 : h % 12;
  return `${hour12}:${String(m).padStart(2, "0")} ${h < 12 ? "AM" : "PM"}`;
};

/** "Every 2 weeks on Mon, Fri at 6:00 AM" */
export function describeRule(rule: Pick<TRepeatRule, "frequency" | "interval" | "weekdays" | "month_day" | "time_of_day">) {
  const every = rule.interval === 1 ? `Every ${unitName(rule.frequency, 1)}` : `Every ${rule.interval} ${unitName(rule.frequency, rule.interval)}`;
  let on = "";
  if (rule.frequency === "weekly" && rule.weekdays?.length) {
    on = ` on ${WEEKDAYS.filter((d) => rule.weekdays.includes(d.value))
      .map((d) => d.name)
      .join(", ")}`;
  } else if (rule.frequency === "monthly" && rule.month_day) {
    on = rule.month_day === LAST_DAY ? " on the last day" : ` on the ${ordinal(rule.month_day)}`;
  }
  const head = rule.frequency === "daily" && rule.interval === 1 ? "Every day" : every;
  return `${head}${on} at ${formatClock(rule.time_of_day)}`;
}

/** A run moment shown in the rule's time zone (or the browser's), e.g. "Mon, Oct 26, 6:00 AM CDT". */
export function formatRunTime(iso: string, timeZone?: string) {
  const options: Intl.DateTimeFormatOptions = {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  };
  try {
    return new Intl.DateTimeFormat(undefined, { ...options, timeZone }).format(new Date(iso));
  } catch {
    return new Intl.DateTimeFormat(undefined, options).format(new Date(iso));
  }
}

const browserTimezone = () => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined;
  } catch {
    return undefined;
  }
};

export type TEndMode = "never" | "on" | "after";

export type TRepeatDraft = TRepeatRuleInput & { end_mode: TEndMode };

export function defaultDraft(): TRepeatDraft {
  const today = new Date();
  return {
    frequency: "weekly",
    interval: 1,
    weekdays: [serverWeekday(today)],
    month_day: today.getDate(),
    time_of_day: "06:00",
    start_date: todayIso(),
    end_date: null,
    max_count: null,
    end_mode: "never",
  };
}

export function draftFromRule(rule: TRepeatRule): TRepeatDraft {
  return {
    frequency: rule.frequency,
    interval: rule.interval,
    weekdays: rule.weekdays?.length ? rule.weekdays : [serverWeekday(new Date())],
    month_day: rule.month_day ?? new Date().getDate(),
    time_of_day: rule.time_of_day,
    timezone: rule.timezone,
    start_date: rule.start_date,
    end_date: rule.end_date,
    max_count: rule.max_count,
    end_mode: rule.end_date ? "on" : rule.max_count ? "after" : "never",
  };
}

export function payloadFromDraft(draft: TRepeatDraft): TRepeatRuleInput {
  return {
    frequency: draft.frequency,
    interval: Math.max(1, Math.floor(Number(draft.interval) || 1)),
    weekdays: draft.frequency === "weekly" ? draft.weekdays : [],
    month_day: draft.frequency === "monthly" ? draft.month_day : null,
    time_of_day: draft.time_of_day || "06:00",
    timezone: draft.timezone,
    fallback_timezone: browserTimezone(),
    start_date: draft.start_date,
    end_date: draft.end_mode === "on" ? draft.end_date || null : null,
    max_count: draft.end_mode === "after" ? Math.max(1, Math.floor(Number(draft.max_count) || 1)) : null,
  };
}
