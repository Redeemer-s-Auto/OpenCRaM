/**
 * Copyright (c) 2026-present OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { NodeViewProps } from "@tiptap/react";
import { NodeViewContent, NodeViewWrapper } from "@tiptap/react";
import { ChevronRight } from "lucide-react";

export function ToggleBlock(props: NodeViewProps) {
  const { node, updateAttributes } = props;
  const isOpen = node.attrs["data-open"] !== false;

  return (
    <NodeViewWrapper
      className="editor-toggle-component group/toggle-node relative my-1 flex items-start gap-1"
      data-open={isOpen ? "true" : "false"}
    >
      <button
        type="button"
        contentEditable={false}
        aria-label={isOpen ? "Close toggle" : "Open toggle"}
        aria-expanded={isOpen}
        onClick={() => updateAttributes({ "data-open": !isOpen })}
        className="mt-[3px] grid size-5 shrink-0 place-items-center rounded-sm text-tertiary hover:bg-layer-1 hover:text-primary"
      >
        <ChevronRight className={`size-4 transition-transform duration-150 ${isOpen ? "rotate-90" : ""}`} />
      </button>
      <NodeViewContent as="div" className="editor-toggle-body min-w-0 grow" />
    </NodeViewWrapper>
  );
}
