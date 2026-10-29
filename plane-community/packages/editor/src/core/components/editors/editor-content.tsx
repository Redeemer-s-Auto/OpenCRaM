/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { EditorContent } from "@tiptap/react";
import type { Editor } from "@tiptap/react";
import type { ReactNode } from "react";

type Props = {
  className?: string;
  children?: ReactNode;
  editor: Editor | null;
  id: string;
  tabIndex?: number;
};

export function EditorContentWrapper(props: Props) {
  const { editor, className, children, tabIndex, id } = props;

  return (
    <div
      tabIndex={tabIndex}
      onFocus={(event) => {
        // focus inside a block that holds its own editor (a synced block) is that editor's, not this one's
        const inner = (event.target as HTMLElement).closest?.(".ProseMirror");
        if (inner && inner !== editor?.view.dom) return;
        editor?.chain().focus(undefined, { scrollIntoView: false }).run();
      }}
      className={className}
    >
      <EditorContent editor={editor} id={id} />
      {children}
    </div>
  );
}
