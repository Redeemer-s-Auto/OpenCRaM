/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { observable, runInAction } from "mobx";
import { generateWorkItemLink } from "@plane/utils";
import type { TCardResolution, TLinkedCard } from "@/services/card-links.service";
import { cardLinksService } from "@/services/card-links.service";

/**
 * Live look-ups for link blocks and shortcut cards. Nothing here is stored with
 * the card: every title, colour and board name comes from the server for the
 * person looking, so renames show at once and hidden cards stay hidden.
 */

const STALE_MS = 60_000;
const BATCH_MS = 25;

type TEntry = { value: TCardResolution; at: number };

const resolutions = observable.map<string, TEntry>({}, { deep: false });
const projectShortcuts = observable.map<string, Record<string, TCardResolution>>({}, { deep: false });
// shortcut card id -> its target, from every board map loaded so far
const shortcutIndex = observable.map<string, TCardResolution>({}, { deep: false });

let queue = new Set<string>();
let queueSlug = "";
let timer: ReturnType<typeof setTimeout> | null = null;
const inFlight = new Set<string>();

function flush() {
  timer = null;
  const slug = queueSlug;
  const ids = [...queue];
  queue = new Set();
  if (!slug || ids.length === 0) return;
  for (let i = 0; i < ids.length; i += 100) {
    const chunk = ids.slice(i, i + 100);
    chunk.forEach((id) => inFlight.add(id));
    cardLinksService
      .resolve(slug, chunk)
      .then((results) => {
        runInAction(() => {
          const now = Date.now();
          chunk.forEach((id) => resolutions.set(id, { value: results[id] ?? { status: "hidden" }, at: now }));
        });
      })
      .catch(() => undefined)
      .finally(() => chunk.forEach((id) => inFlight.delete(id)));
  }
}

/** Ask for ``cardId`` (batched with other blocks on the page). */
export function requestCard(workspaceSlug: string, cardId: string, force = false) {
  const entry = resolutions.get(cardId);
  if (!force && entry && Date.now() - entry.at < STALE_MS) return;
  if (inFlight.has(cardId)) return;
  if (queueSlug && queueSlug !== workspaceSlug) flush();
  queueSlug = workspaceSlug;
  queue.add(cardId);
  if (!timer) timer = setTimeout(flush, BATCH_MS);
}

export function getResolution(cardId: string | null | undefined): TCardResolution | undefined {
  return cardId ? resolutions.get(cardId)?.value : undefined;
}

/** Hook: keeps one card's look-up fresh while a component shows it. Read with ``getResolution`` in an observer. */
export function useCardResolution(workspaceSlug: string | undefined, cardId: string | null | undefined) {
  useEffect(() => {
    if (!workspaceSlug || !cardId) return;
    requestCard(workspaceSlug, cardId);
    const onFocus = () => requestCard(workspaceSlug, cardId, true);
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [workspaceSlug, cardId]);
  return getResolution(cardId);
}

/** Remember a card the person just picked, so the block shows it without a round trip. */
export function rememberCard(card: TLinkedCard) {
  runInAction(() => resolutions.set(card.id, { value: { status: "visible", card }, at: Date.now() }));
}

// ---------------------------------------------------------------------------
// Shortcut cards on a board
// ---------------------------------------------------------------------------

const boardLoads = new Map<string, number>();
// Many cards on one board ask at once (mount, tab focus): one request serves them all.
const FORCE_DEDUPE_MS = 3_000;

export function loadProjectShortcuts(workspaceSlug: string, projectId: string, force = false) {
  const key = `${workspaceSlug}/${projectId}`;
  const last = boardLoads.get(key);
  if (last && Date.now() - last < (force ? FORCE_DEDUPE_MS : STALE_MS)) return;
  boardLoads.set(key, Date.now());
  cardLinksService
    .projectShortcuts(workspaceSlug, projectId)
    .then((map) =>
      runInAction(() => {
        const previous = projectShortcuts.get(key) ?? {};
        Object.keys(previous).forEach((id) => shortcutIndex.delete(id));
        projectShortcuts.set(key, map);
        Object.entries(map).forEach(([id, value]) => shortcutIndex.set(id, value));
      })
    )
    .catch(() => boardLoads.delete(key));
}

/** Hook: load a board's shortcut cards (once a minute, and when the tab regains focus). */
export function useProjectShortcuts(workspaceSlug: string | undefined, projectId: string | null | undefined) {
  useEffect(() => {
    if (!workspaceSlug || !projectId) return;
    loadProjectShortcuts(workspaceSlug, projectId);
    const onFocus = () => loadProjectShortcuts(workspaceSlug, projectId, true);
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [workspaceSlug, projectId]);
}

/** Where a shortcut card goes (undefined when the card is not a known shortcut). */
export function getShortcutTarget(issueId: string | null | undefined): TCardResolution | undefined {
  return issueId ? shortcutIndex.get(issueId) : undefined;
}

export function setShortcutTarget(issueId: string, value: TCardResolution) {
  runInAction(() => shortcutIndex.set(issueId, value));
}

export function linkedCardHref(workspaceSlug: string, card: TLinkedCard) {
  return generateWorkItemLink({
    workspaceSlug,
    projectId: card.project_id,
    issueId: card.id,
    projectIdentifier: card.project_identifier,
    sequenceId: card.sequence_id,
  });
}

export const HIDDEN_CARD_LABEL = "Hidden card";
export const REMOVED_CARD_LABEL = "Card removed";
