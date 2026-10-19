/**
 * Copyright (c) 2026 OpenCRaM contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 */

import { useState } from "react";
import { observer } from "mobx-react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import { Button } from "@plane/propel/button";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
// components
import { PageHead } from "@/components/core/page-title";
// services
import { sharedWithMeService } from "@/services/sharing.service";
// local imports
import type { Route } from "./+types/page";

const COMMENT_LEVEL = 10;
const EDIT_LEVEL = 15;

/** Plain text from the box -> safe HTML paragraphs. */
function textToHtml(text: string) {
  const escape = (value: string) =>
    value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  return text
    .split(/\n{2,}/)
    .map((block) => `<p>${escape(block).replace(/\n/g, "<br>")}</p>`)
    .join("");
}

/** Safe HTML from the server -> text for the edit box. */
function htmlToText(html: string) {
  const doc = new DOMParser().parseFromString(html.replace(/<\/p>/g, "</p>\n\n").replace(/<br\s*\/?>/g, "\n"), "text/html");
  return (doc.body.textContent ?? "").trim();
}

const SharedIssuePage = observer(function SharedIssuePage({ params }: Route.ComponentProps) {
  const { workspaceSlug, issueId } = params;
  const { t } = useTranslation();
  const issueKey = `SHARED_ISSUE_${issueId}`;
  const commentsKey = `SHARED_ISSUE_COMMENTS_${issueId}`;
  const { data: issue, error, mutate } = useSWR(issueKey, () => sharedWithMeService.getIssue(workspaceSlug, issueId));
  const { data: comments, mutate: mutateComments } = useSWR(issue ? commentsKey : null, () =>
    sharedWithMeService.listComments(workspaceSlug, issueId)
  );
  // state
  const [draft, setDraft] = useState<{ name: string; text: string } | null>(null);
  const [comment, setComment] = useState("");
  const [isBusy, setIsBusy] = useState(false);

  if (error) return <p className="p-8 text-center text-body-sm-regular text-tertiary">{t("sharing.no_results")}</p>;
  if (!issue) return <div className="m-6 h-60 animate-pulse rounded-md bg-layer-1" />;

  const canEdit = issue.level >= EDIT_LEVEL;
  const canComment = issue.level >= COMMENT_LEVEL;

  const saveEdit = async () => {
    if (!draft) return;
    setIsBusy(true);
    try {
      const saved = await sharedWithMeService.updateIssue(workspaceSlug, issueId, {
        name: draft.name,
        description_html: textToHtml(draft.text),
      });
      await mutate(saved, false);
      setDraft(null);
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: t("error"), message: t("something_went_wrong_please_try_again") });
    } finally {
      setIsBusy(false);
    }
  };

  const postComment = async () => {
    if (!comment.trim()) return;
    setIsBusy(true);
    try {
      await sharedWithMeService.addComment(workspaceSlug, issueId, textToHtml(comment.trim()));
      setComment("");
      await mutateComments();
    } catch {
      setToast({ type: TOAST_TYPE.ERROR, title: t("error"), message: t("something_went_wrong_please_try_again") });
    } finally {
      setIsBusy(false);
    }
  };

  const details: [string, string][] = [
    [t("common.state"), issue.state?.name ?? "-"],
    [t("common.priority"), issue.priority ?? "-"],
    [t("common.assignees"), issue.assignees.map((a) => a?.name).filter(Boolean).join(", ") || "-"],
    [t("common.labels"), issue.labels.map((l) => l.name).join(", ") || "-"],
    [t("common.order_by.due_date"), issue.target_date ?? "-"],
  ];

  return (
    <>
      <PageHead title={`${issue.identifier} ${issue.name}`} />
      <div className="h-full w-full overflow-y-auto">
        <div className="mx-auto flex max-w-5xl flex-wrap gap-8 p-6">
          <article className="flex min-w-0 flex-col gap-4" style={{ flex: "999 1 480px" }}>
            <p className="text-caption-md-medium text-tertiary">
              {issue.project_name} · {issue.identifier}
            </p>
            {draft ? (
              <div className="flex flex-col gap-3">
                <input
                  aria-label={t("name")}
                  className="rounded-md border border-subtle bg-layer-2 px-3 py-2 text-h4-medium text-primary outline-none focus:border-accent-strong"
                  value={draft.name}
                  onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                />
                <textarea
                  aria-label={t("description")}
                  rows={10}
                  className="rounded-md border border-subtle bg-layer-2 px-3 py-2 text-body-sm-regular text-primary outline-none focus:border-accent-strong"
                  value={draft.text}
                  onChange={(e) => setDraft({ ...draft, text: e.target.value })}
                />
                <div className="flex gap-2">
                  <Button variant="primary" size="lg" onClick={saveEdit} disabled={isBusy || !draft.name.trim()}>
                    {t("save")}
                  </Button>
                  <Button variant="secondary" size="lg" onClick={() => setDraft(null)}>
                    {t("cancel")}
                  </Button>
                </div>
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <h1 className="text-h3-medium text-primary">{issue.name}</h1>
                  {canEdit && (
                    <Button
                      variant="secondary"
                      size="lg"
                      onClick={() => setDraft({ name: issue.name, text: htmlToText(issue.description_html) })}
                    >
                      {t("sharing.edit")}
                    </Button>
                  )}
                </div>
                {/* description_html is sanitized on the server (nh3) before it reaches here */}
                <div
                  className="prose max-w-none text-body-sm-regular text-secondary"
                  dangerouslySetInnerHTML={{ __html: issue.description_html }}
                />
              </>
            )}

            <section className="mt-4 flex flex-col gap-3 border-t border-subtle-1 pt-4" aria-label={t("sharing.comments")}>
              <h2 className="text-body-sm-medium text-primary">{t("sharing.comments")}</h2>
              {comments?.length === 0 && <p className="text-caption-md-regular text-tertiary">{t("sharing.no_comments")}</p>}
              {comments?.map((c) => (
                <div key={c.id} className="rounded-md border border-subtle p-3">
                  <p className="mb-1 text-caption-md-medium text-tertiary">
                    {c.actor?.name} · {new Date(c.created_at).toLocaleString()}
                  </p>
                  {/* comment_html is sanitized on the server (nh3) */}
                  <div className="text-body-sm-regular text-secondary" dangerouslySetInnerHTML={{ __html: c.comment_html }} />
                </div>
              ))}
              {canComment && (
                <div className="flex flex-col gap-2">
                  <textarea
                    aria-label={t("sharing.add_comment")}
                    placeholder={t("sharing.add_comment")}
                    rows={3}
                    className="rounded-md border border-subtle bg-layer-2 px-3 py-2 text-body-sm-regular text-primary outline-none placeholder:text-placeholder focus:border-accent-strong"
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                  />
                  <Button
                    className="self-start"
                    variant="primary"
                    size="lg"
                    onClick={postComment}
                    disabled={isBusy || !comment.trim()}
                  >
                    {t("sharing.post_comment")}
                  </Button>
                </div>
              )}
            </section>
          </article>

          <aside className="flex flex-col gap-3" style={{ flex: "1 1 240px", maxWidth: 320 }}>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2.5 rounded-md border border-subtle p-4 text-body-xs-regular">
              {details.map(([label, value]) => (
                <div key={label} className="contents">
                  <dt className="text-tertiary">{label}</dt>
                  <dd className="text-primary">{value}</dd>
                </div>
              ))}
            </dl>
            {issue.created_by && (
              <p className="text-caption-md-regular text-tertiary">{t("sharing.shared_by", { name: issue.created_by.name })}</p>
            )}
          </aside>
        </div>
      </div>
    </>
  );
});

export default SharedIssuePage;
