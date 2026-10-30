/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect } from "react";
import { observable, runInAction } from "mobx";
import type { TPageLinkTarget } from "@plane/editor";
import type {
  TLinkedPage,
  TLinkedProject,
  TPageResolution,
  TProjectResolution,
} from "@/services/page-tree.service";
import { pageTreeService } from "@/services/page-tree.service";

/**
 * Live look-ups for "Link to page" blocks. Nothing is stored with the page: every
 * title and icon comes from the server for the person looking, so renames show at
 * once and hidden pages stay hidden.
 */

const STALE_MS = 60_000;
const BATCH_MS = 25;

export const HIDDEN_PAGE_LABEL = "Hidden page";
export const REMOVED_PAGE_LABEL = "Page removed";
export const HIDDEN_PROJECT_LABEL = "Hidden board";

export type TLinkResolution =
  | { status: "visible"; kind: "page"; page: TLinkedPage }
  | { status: "visible"; kind: "project"; project: TLinkedProject }
  | { status: "hidden" }
  | { status: "removed" };

type TEntry = { value: TLinkResolution; at: number };

const resolutions = observable.map<string, TEntry>({}, { deep: false });

const key = (target: TPageLinkTarget) => `${target.kind}:${target.id}`;

let queue = new Map<string, TPageLinkTarget>();
let queueSlug = "";
let timer: ReturnType<typeof setTimeout> | null = null;
const inFlight = new Set<string>();

const fromPage = (value: TPageResolution | undefined): TLinkResolution =>
  value?.status === "visible" ? { status: "visible", kind: "page", page: value.page } : (value ?? { status: "hidden" });

const fromProject = (value: TProjectResolution | undefined): TLinkResolution =>
  value?.status === "visible"
    ? { status: "visible", kind: "project", project: value.project }
    : (value ?? { status: "hidden" });

function flush() {
  timer = null;
  const slug = queueSlug;
  const targets = [...queue.values()];
  queue = new Map();
  if (!slug || targets.length === 0) return;
  for (let i = 0; i < targets.length; i += 100) {
    const chunk = targets.slice(i, i + 100);
    chunk.forEach((target) => inFlight.add(key(target)));
    const pages = chunk.filter((t) => t.kind === "page").map((t) => t.id);
    const projects = chunk.filter((t) => t.kind === "project").map((t) => t.id);
    pageTreeService
      .resolve(slug, pages, projects)
      .then((results) => {
        runInAction(() => {
          const now = Date.now();
          chunk.forEach((target) => {
            const value =
              target.kind === "page" ? fromPage(results.pages?.[target.id]) : fromProject(results.projects?.[target.id]);
            resolutions.set(key(target), { value, at: now });
          });
        });
      })
      .catch(() => undefined)
      .finally(() => chunk.forEach((target) => inFlight.delete(key(target))));
  }
}

/** Ask for ``target`` (batched with other blocks on the page). */
export function requestTarget(workspaceSlug: string, target: TPageLinkTarget, force = false) {
  const k = key(target);
  const entry = resolutions.get(k);
  if (!force && entry && Date.now() - entry.at < STALE_MS) return;
  if (inFlight.has(k)) return;
  if (queueSlug && queueSlug !== workspaceSlug) flush();
  queueSlug = workspaceSlug;
  queue.set(k, target);
  if (!timer) timer = setTimeout(flush, BATCH_MS);
}

export function getLinkResolution(target: TPageLinkTarget | null | undefined): TLinkResolution | undefined {
  return target ? resolutions.get(key(target))?.value : undefined;
}

/** Hook: keeps one target's look-up fresh while a component shows it. Read in an observer. */
export function useLinkResolution(workspaceSlug: string | undefined, target: TPageLinkTarget | null | undefined) {
  const k = target ? key(target) : "";
  useEffect(() => {
    if (!workspaceSlug || !target) return;
    requestTarget(workspaceSlug, target);
    const onFocus = () => requestTarget(workspaceSlug, target, true);
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [workspaceSlug, k]);
  return getLinkResolution(target);
}

/** Remember something the person just picked, so the block shows it without a round trip. */
export function rememberPage(page: TLinkedPage) {
  runInAction(() =>
    resolutions.set(key({ kind: "page", id: page.id }), {
      value: { status: "visible", kind: "page", page },
      at: Date.now(),
    })
  );
}

export function rememberProject(project: TLinkedProject) {
  runInAction(() =>
    resolutions.set(key({ kind: "project", id: project.id }), {
      value: { status: "visible", kind: "project", project },
      at: Date.now(),
    })
  );
}
