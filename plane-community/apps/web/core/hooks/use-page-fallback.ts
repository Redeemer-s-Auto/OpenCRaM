/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { EditorRefApi, CollaborationState } from "@plane/editor";
// plane editor
import { convertBinaryDataToBase64String, getBinaryDataFromDocumentEditorHTMLString } from "@plane/editor";
// plane types
import type { TDocumentPayload } from "@plane/types";
// hooks
import useAutoSave from "@/hooks/use-auto-save";
import type { TPageInstance } from "@/store/pages/base-page";

type TArgs = {
  editorRef: React.RefObject<EditorRefApi>;
  fetchPageDescription: () => Promise<ArrayBuffer>;
  collaborationState: CollaborationState | null;
  updatePageDescription: (data: TDocumentPayload) => Promise<void>;
  page: TPageInstance;
};

export const usePageFallback = (args: TArgs) => {
  const { editorRef, fetchPageDescription, collaborationState, updatePageDescription, page } = args;
  const hasShownFallbackToast = useRef(false);
  // One fallback save at a time. The collaboration stage flips between "reconnecting" and
  // "disconnected" on every failed attempt, and each flip used to start another save while the
  // previous one was still converting the page HTML: two independent conversions applied to the
  // same Y.Doc show the body twice.
  const isSavingRef = useRef(false);
  // Read through refs so the save callback does not change identity (and re-run) when the store
  // echoes our own PATCH back into page.description_html.
  const pageRef = useRef(page);
  useEffect(() => {
    pageRef.current = page;
  }, [page]);

  const [isFetchingFallbackBinary, setIsFetchingFallbackBinary] = useState(false);

  // Derive connection failure from collaboration state
  const hasConnectionFailed = collaborationState?.stage.kind === "disconnected";

  const handleUpdateDescription = useCallback(async () => {
    if (!hasConnectionFailed) return;
    if (isSavingRef.current) return;
    const editor = editorRef.current;
    if (!editor) return;

    // Show toast notification when fallback mechanism kicks in (only once)
    if (!hasShownFallbackToast.current) {
      console.warn("Websocket Connection lost, your changes are being saved using backup mechanism.");
      hasShownFallbackToast.current = true;
    }

    isSavingRef.current = true;
    try {
      setIsFetchingFallbackBinary(true);

      const latestEncodedDescription = await fetchPageDescription();
      if (latestEncodedDescription && latestEncodedDescription.byteLength > 0) {
        // Yjs merges a stored update that is already in the document as a no-op.
        editor.setProviderDocument(new Uint8Array(latestEncodedDescription));
      } else if (!editor.hasProviderDocumentContent()) {
        // Never opened in the editor yet: the body exists only as HTML. Build the document from
        // it once. Converting again onto a document that already has content (an earlier
        // conversion, the local cache) would append a second copy of every block.
        const currentPage = pageRef.current;
        editor.setProviderDocument(
          getBinaryDataFromDocumentEditorHTMLString(currentPage.description_html ?? "<p></p>", currentPage.name)
        );
      }
      const { binary, html, json } = editor.getDocument();
      if (!binary || !json) return;
      const encodedBinary = convertBinaryDataToBase64String(binary);

      await updatePageDescription({
        description_binary: encodedBinary,
        description_html: html,
        description_json: json,
      });
    } catch (error: any) {
      console.error(error);
    } finally {
      isSavingRef.current = false;
      setIsFetchingFallbackBinary(false);
    }
  }, [editorRef, fetchPageDescription, hasConnectionFailed, updatePageDescription]);

  useEffect(() => {
    if (hasConnectionFailed) {
      handleUpdateDescription();
    } else {
      // Reset toast flag when connection is restored
      hasShownFallbackToast.current = false;
    }
  }, [handleUpdateDescription, hasConnectionFailed]);

  useAutoSave(handleUpdateDescription);

  return { isFetchingFallbackBinary };
};
