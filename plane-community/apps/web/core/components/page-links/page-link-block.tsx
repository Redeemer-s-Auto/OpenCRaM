/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import Link from "next/link";
import { EyeOff, FileX, Search, X } from "lucide-react";
import type { TPageLinkHandler, TPageLinkRenderProps, TPageLinkTarget } from "@plane/editor";
import { Logo } from "@plane/propel/emoji-icon-picker";
import { PageIcon } from "@plane/propel/icons";
import type { TLogoProps } from "@plane/types";
import { cn } from "@plane/utils";
import type { TLinkedPage, TLinkedProject } from "@/services/page-tree.service";
import { pageHref, pageTreeService, projectHref } from "@/services/page-tree.service";
import type { TLinkResolution } from "./store";
import {
  HIDDEN_PAGE_LABEL,
  HIDDEN_PROJECT_LABEL,
  REMOVED_PAGE_LABEL,
  rememberPage,
  rememberProject,
  useLinkResolution,
} from "./store";

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";

/** The page or board behind an address of this app. */
export function parsePageUrl(workspaceSlug: string, text: string): TPageLinkTarget | null {
  let url: URL;
  try {
    url = new URL(text, window.location.origin);
  } catch {
    return null;
  }
  if (url.origin !== window.location.origin) return null;
  const slug = workspaceSlug.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const page = url.pathname.match(new RegExp(`^/${slug}/projects/${UUID}/pages/(${UUID})/?$`, "i"));
  if (page) return { kind: "page", id: page[1].toLowerCase() };
  const board = url.pathname.match(new RegExp(`^/${slug}/projects/(${UUID})/?(?:issues|cycles|modules|views|pages)?/?$`, "i"));
  if (board) return { kind: "project", id: board[1].toLowerCase() };
  return null;
}

/** The page's emoji or icon; a plain page glyph when it has none. */
export function PageLogo(props: { logo?: TLogoProps | Record<string, never>; size?: number; className?: string }) {
  const { logo, size = 16, className } = props;
  const inUse = logo && "in_use" in logo ? logo.in_use : undefined;
  if (inUse) {
    return (
      <span className={cn("grid flex-shrink-0 place-items-center", className)} style={{ width: size, height: size }}>
        <Logo logo={logo as TLogoProps} size={size} type="lucide" />
      </span>
    );
  }
  return <PageIcon className={cn("flex-shrink-0 text-placeholder", className)} style={{ width: size, height: size }} />;
}

/** "Hidden page" / "Page removed": the same words for every case, no other detail. */
function Unavailable(props: { status: "hidden" | "removed"; kind: "page" | "project" }) {
  const { status, kind } = props;
  const Icon = status === "hidden" ? EyeOff : FileX;
  const label = status === "removed" ? REMOVED_PAGE_LABEL : kind === "project" ? HIDDEN_PROJECT_LABEL : HIDDEN_PAGE_LABEL;
  return (
    <span className="flex min-w-0 items-center gap-1.5 text-tertiary" data-page-link-state={status}>
      <Icon className="size-3.5 flex-shrink-0" />
      <span className="truncate italic">{label}</span>
    </span>
  );
}

type TChipProps = { workspaceSlug: string; target: TPageLinkTarget; resolution: TLinkResolution | undefined };

/** One linked page or board: icon and title, opening it. Unavailable targets say only that. */
export const PageLinkChip = observer(function PageLinkChip(props: TChipProps) {
  const { workspaceSlug, target, resolution } = props;
  const base = "flex w-full min-w-0 items-center gap-2 rounded-md px-2 py-1.5 text-13 hover:bg-layer-transparent-hover";
  if (!resolution) {
    return (
      <span className={cn(base, "text-placeholder")} data-page-link-state="loading">
        <span className="size-4 animate-pulse rounded-sm bg-layer-3" />
        <span className="h-3 w-40 animate-pulse rounded bg-layer-3" />
      </span>
    );
  }
  if (resolution.status !== "visible") {
    return (
      <span className={base}>
        <Unavailable status={resolution.status} kind={target.kind} />
      </span>
    );
  }
  const href =
    resolution.kind === "page"
      ? pageHref(workspaceSlug, resolution.page.project_id, resolution.page.id)
      : projectHref(workspaceSlug, resolution.project.id);
  const name = resolution.kind === "page" ? resolution.page.name : resolution.project.name;
  const logo = resolution.kind === "page" ? resolution.page.logo_props : resolution.project.logo_props;
  return (
    <Link
      href={href}
      className={cn(base, "!no-underline [&_*]:!no-underline")}
      data-page-link-state="visible"
      data-page-link-kind={resolution.kind}
      title={name}
    >
      <PageLogo logo={logo} size={16} />
      <span className="truncate font-medium text-primary underline decoration-subtle underline-offset-4">
        {name || "Untitled"}
      </span>
      {resolution.kind === "project" && (
        <span className="ml-auto flex-shrink-0 text-11 text-tertiary">{resolution.project.identifier}</span>
      )}
    </Link>
  );
});

type TPickerProps = {
  workspaceSlug: string;
  onPick: (target: TPageLinkTarget) => void;
  onCancel: () => void;
};

/** Search box over the pages and boards the person may link to. */
function PageLinkPicker(props: TPickerProps) {
  const { workspaceSlug, onPick, onCancel } = props;
  const [query, setQuery] = useState("");
  const [pages, setPages] = useState<TLinkedPage[]>([]);
  const [projects, setProjects] = useState<TLinkedProject[]>([]);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    const handle = setTimeout(() => {
      pageTreeService
        .search(workspaceSlug, query, 15)
        .then((result) => {
          if (cancelled) return;
          setPages(result.pages);
          setProjects(result.projects);
        })
        .catch(() => undefined)
        .finally(() => !cancelled && setBusy(false));
    }, 150);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
  }, [workspaceSlug, query]);

  const rowClass =
    "flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left text-13 text-secondary hover:bg-layer-transparent-hover";

  return (
    <div
      className="w-full max-w-md rounded-md border border-subtle bg-surface-1 p-2 shadow-sm"
      onKeyDown={(e) => {
        if (e.key === "Escape") onCancel();
      }}
    >
      <div className="flex items-center gap-2 rounded-sm border border-subtle px-2 py-1">
        <Search className="size-3.5 flex-shrink-0 text-placeholder" />
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Link to a page or board"
          className="w-full bg-transparent text-13 text-primary outline-none placeholder:text-placeholder"
          aria-label="Search pages and boards"
        />
        <button type="button" aria-label="Cancel" onClick={onCancel} className="text-placeholder hover:text-secondary">
          <X className="size-3.5" />
        </button>
      </div>
      <div className="mt-1 max-h-64 overflow-y-auto">
        {pages.length > 0 && <p className="px-2 pt-1 text-11 font-medium text-tertiary">Pages</p>}
        {pages.map((page) => (
          <button
            key={page.id}
            type="button"
            className={rowClass}
            onClick={() => {
              rememberPage(page);
              onPick({ kind: "page", id: page.id });
            }}
          >
            <PageLogo logo={page.logo_props} size={14} />
            <span className="truncate">{page.name || "Untitled"}</span>
          </button>
        ))}
        {projects.length > 0 && <p className="px-2 pt-1 text-11 font-medium text-tertiary">Boards</p>}
        {projects.map((project) => (
          <button
            key={project.id}
            type="button"
            className={rowClass}
            onClick={() => {
              rememberProject(project);
              onPick({ kind: "project", id: project.id });
            }}
          >
            <PageLogo logo={project.logo_props} size={14} />
            <span className="truncate">{project.name}</span>
            <span className="ml-auto flex-shrink-0 text-11 text-tertiary">{project.identifier}</span>
          </button>
        ))}
        {!busy && pages.length === 0 && projects.length === 0 && (
          <p className="px-2 py-2 text-12 text-tertiary">Nothing found</p>
        )}
      </div>
    </div>
  );
}

const PageLinkBlock = observer(function PageLinkBlock(props: TPageLinkRenderProps & { workspaceSlug: string }) {
  const { workspaceSlug, target, editable, selected, onPick, onRemove } = props;
  const resolution = useLinkResolution(workspaceSlug, target);

  if (!target) {
    if (!editable) return null;
    return (
      <div className="my-1" contentEditable={false}>
        <PageLinkPicker workspaceSlug={workspaceSlug} onPick={onPick} onCancel={onRemove} />
      </div>
    );
  }

  return (
    <div
      className={cn("group/page-link relative my-0.5 flex items-center", {
        "rounded-md ring-1 ring-accent-strong": selected,
      })}
      contentEditable={false}
    >
      <PageLinkChip workspaceSlug={workspaceSlug} target={target} resolution={resolution} />
      {editable && (
        <button
          type="button"
          aria-label="Remove link"
          onClick={onRemove}
          className="absolute top-1/2 right-1 hidden -translate-y-1/2 rounded-sm bg-layer-1 p-0.5 text-placeholder group-hover/page-link:block hover:text-secondary"
        >
          <X className="size-3.5" />
        </button>
      )}
    </div>
  );
});

/** What the editor needs to show "Link to page" blocks in a page body. */
export function getPageLinkHandler(workspaceSlug: string): TPageLinkHandler {
  return {
    renderComponent: (props) => <PageLinkBlock {...props} workspaceSlug={workspaceSlug} />,
    isPageUrl: (text) => parsePageUrl(workspaceSlug, text) !== null,
    targetFromUrl: async (text) => {
      const target = parsePageUrl(workspaceSlug, text);
      if (!target) return null;
      const results = await pageTreeService.resolve(
        workspaceSlug,
        target.kind === "page" ? [target.id] : [],
        target.kind === "project" ? [target.id] : []
      );
      if (target.kind === "page") {
        const value = results.pages?.[target.id];
        if (value?.status !== "visible") return null;
        rememberPage(value.page);
      } else {
        const value = results.projects?.[target.id];
        if (value?.status !== "visible") return null;
        rememberProject(value.project);
      }
      return target;
    },
  };
}
