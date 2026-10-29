/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import { debounce } from "lodash-es";
import { observer } from "mobx-react";
import useSWR from "swr";
import type { EditorRefApi, TSyncedBlockRenderProps } from "@plane/editor";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
// components
import { RichTextEditor } from "@/components/editor/rich-text";
import { useInlineViewHost } from "@/components/inline-views/host-context";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
// services
import { SyncedBlockService } from "@/services/synced-block.service";
import type { TSyncedBlock } from "@/services/synced-block.service";
import { WorkspaceService } from "@/services/workspace.service";

const service = new SyncedBlockService();
const workspaceService = new WorkspaceService();
const SAVE_DELAY_MS = 1000;
const REFRESH_MS = 4000;

const frame = "rounded-lg border border-dashed border-accent-primary/50 bg-surface-1";
const smallButton = "text-11 text-secondary hover:underline";

/** Nothing chosen yet: make a new shared block, or reuse one that exists. */
function Chooser(props: Pick<TSyncedBlockRenderProps, "setId" | "removeCopy">) {
  const { setId, removeCopy } = props;
  const host = useInlineViewHost();
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const slug = host?.workspaceSlug;
  const { data: blocks } = useSWR(slug ? ["synced-block-list", slug, search] : null, () =>
    service.list(slug as string, search)
  );

  const make = async () => {
    if (!slug || !host?.issueId) return;
    setBusy(true);
    try {
      const block = await service.create(slug, host.issueId);
      setId(block.id);
    } catch (e) {
      const message = (e as { error?: string })?.error ?? "The block was not made.";
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not make block", message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`${frame} p-3`}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-body-sm-medium">Synced block</span>
        <button type="button" className={smallButton} onClick={removeCopy}>
          Cancel
        </button>
      </div>
      <button
        type="button"
        disabled={busy || !host?.issueId}
        onClick={() => void make()}
        className="rounded-md border border-subtle px-2 py-1 text-body-xs-medium hover:bg-layer-1 disabled:opacity-50"
      >
        + Make a new synced block
      </button>
      <div className="mt-3 text-11 text-tertiary">Or use one that already exists:</div>
      <input
        className="mt-1 w-full rounded-sm border border-subtle bg-transparent px-1.5 py-0.5 text-body-xs-regular"
        placeholder="Search by text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <ul className="mt-1 max-h-48 overflow-y-auto">
        {(blocks ?? []).map((block) => (
          <li key={block.id}>
            <button
              type="button"
              onClick={() => setId(block.id)}
              className="flex w-full items-baseline gap-2 rounded-sm px-1.5 py-1 text-left text-body-xs-regular hover:bg-layer-1"
            >
              <span className="min-w-0 flex-1 truncate">{block.snippet || "(empty)"}</span>
              <span className="shrink-0 text-11 text-tertiary">
                {block.home.project_identifier}-{block.home.sequence_id}
              </span>
            </button>
          </li>
        ))}
        {blocks && blocks.length === 0 && <li className="px-1.5 py-1 text-11 text-tertiary">No blocks found.</li>}
      </ul>
    </div>
  );
}

/** The shared text, in a small editor. Saves on a pause in typing; other copies pick the change up. */
const SharedText = observer(function SharedText(props: {
  block: TSyncedBlock;
  workspaceSlug: string;
  editable: boolean;
  onSaved: (block: TSyncedBlock) => void;
  editorRef: MutableRefObject<EditorRefApi | null>;
}) {
  const { block, workspaceSlug, editable, onSaved, editorRef } = props;
  const host = useInlineViewHost();
  const { getWorkspaceBySlug } = useWorkspace();
  const workspaceId = getWorkspaceBySlug(workspaceSlug)?.id;
  const focused = useRef(false);
  // The newest version this copy has shown or saved. Newer from the server means someone else edited.
  const seen = useRef(block.version);
  const latest = useRef(block.content_html);
  const pending = useRef<string | null>(null);

  const flush = useCallback(async () => {
    const html = pending.current;
    if (html === null) return;
    pending.current = null;
    try {
      const saved = await service.save(workspaceSlug, block.id, html);
      seen.current = saved.version;
      latest.current = html;
      onSaved(saved);
    } catch (e) {
      const message = (e as { error?: string })?.error === "read_only" ? "You cannot edit this block." : "The change was not saved.";
      setToast({ type: TOAST_TYPE.ERROR, title: "Could not save block", message });
    }
  }, [workspaceSlug, block.id, onSaved]);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const debouncedFlush = useCallback(debounce(flush, SAVE_DELAY_MS), [flush]);

  // Save what is pending if the page closes this copy.
  useEffect(
    () => () => {
      debouncedFlush.cancel();
      void flush();
    },
    [debouncedFlush, flush]
  );

  // Another copy changed the text: show it, unless this copy is being typed in.
  useEffect(() => {
    if (block.version > seen.current && !focused.current && pending.current === null) {
      seen.current = block.version;
      latest.current = block.content_html;
      editorRef.current?.setEditorValue(block.content_html, false);
    }
  }, [block.version, block.content_html, editorRef]);

  if (!workspaceId) return null;

  return (
    <div
      onFocusCapture={() => (focused.current = true)}
      onBlurCapture={() => {
        focused.current = false;
        void flush();
      }}
    >
      <RichTextEditor
        key={block.id}
        ref={(instance) => {
          editorRef.current = instance;
        }}
        id={`synced-${block.id}`}
        editable={editable}
        workspaceSlug={workspaceSlug}
        workspaceId={workspaceId}
        projectId={host?.projectId}
        initialValue={block.content_html}
        placeholder={() => "Type here. Every copy of this block updates."}
        onChange={(_json, html) => {
          if (html === latest.current) return;
          pending.current = html;
          debouncedFlush();
        }}
        searchMentionCallback={async (payload) =>
          await workspaceService.searchEntity(workspaceSlug, { ...payload, project_id: host?.projectId })
        }
        uploadFile={async () => {
          throw new Error("Images are not supported inside synced blocks yet.");
        }}
        duplicateFile={async () => {
          throw new Error("Images are not supported inside synced blocks yet.");
        }}
      />
    </div>
  );
});

/** One copy of a synced block on a page. */
export const SyncedBlockView = observer(function SyncedBlockView(props: TSyncedBlockRenderProps) {
  const { id, setId, unsync, removeCopy, editable } = props;
  const host = useInlineViewHost();
  const slug = host?.workspaceSlug;
  const editorRef = useRef<EditorRefApi | null>(null);
  const { data, error, mutate } = useSWR(
    slug && id ? ["synced-block", slug, id] : null,
    () => service.retrieve(slug as string, id),
    { refreshInterval: REFRESH_MS, revalidateOnFocus: true, shouldRetryOnError: false }
  );

  if (!host) return <div className="rounded-md border border-subtle p-3 text-13 text-tertiary">Synced block</div>;
  if (!id) return <Chooser setId={setId} removeCopy={removeCopy} />;

  if (error) {
    const noAccess = (error as { error?: string })?.error === "no_access";
    return (
      <div className={`${frame} flex items-center justify-between gap-3 p-3`}>
        <span className="text-body-xs-regular text-tertiary">
          {noAccess ? "You do not have access to this synced block." : "This synced block could not be loaded."}
        </span>
        {editable && (
          <button type="button" className={smallButton} onClick={removeCopy}>
            Remove from page
          </button>
        )}
      </div>
    );
  }
  if (!data) return <div className={`${frame} p-3 text-body-xs-regular text-tertiary`}>Loading...</div>;

  const canEdit = editable && data.can_edit;
  const here = data.home.id === host.issueId;

  return (
    <div className={frame}>
      <div className="flex flex-wrap items-center gap-2 border-b border-dashed border-subtle px-3 py-1">
        <span className="text-11 font-medium text-accent-primary">Synced block</span>
        <span className="min-w-0 flex-1 truncate text-11 text-tertiary">
          {here ? "made on this page" : "from "}
          {!here && (
            <a
              className="hover:underline"
              href={`/${slug}/browse/${data.home.project_identifier}-${data.home.sequence_id}/`}
            >
              {data.home.project_identifier}-{data.home.sequence_id} {data.home.name}
            </a>
          )}
          {!data.can_edit && " (read only)"}
        </span>
        {editable && (
          <>
            <button
              type="button"
              className={smallButton}
              title="Make this copy plain text. Other copies keep the shared block."
              onClick={() => unsync(editorRef.current?.getDocument().html ?? data.content_html)}
            >
              Unsync
            </button>
            <button type="button" className={smallButton} title="Take this copy off the page." onClick={removeCopy}>
              Remove copy
            </button>
            <button
              type="button"
              className="text-11 text-danger-primary hover:underline"
              title="Delete the shared text. Every copy goes empty."
              onClick={() => {
                if (!window.confirm("Delete this synced block everywhere? Every page that shows it will lose the text."))
                  return;
                service
                  .remove(slug as string, id)
                  .then(() => {
                    removeCopy();
                    return mutate();
                  })
                  .catch(() =>
                    setToast({
                      type: TOAST_TYPE.ERROR,
                      title: "Could not delete",
                      message: "Only the person who made the block, or a workspace admin, can delete it.",
                    })
                  );
              }}
            >
              Delete everywhere
            </button>
          </>
        )}
      </div>
      <div className="px-1 py-1">
        <SharedText
          block={data}
          workspaceSlug={slug as string}
          editable={canEdit}
          editorRef={editorRef}
          onSaved={(saved) => void mutate(saved, { revalidate: false })}
        />
      </div>
    </div>
  );
});
