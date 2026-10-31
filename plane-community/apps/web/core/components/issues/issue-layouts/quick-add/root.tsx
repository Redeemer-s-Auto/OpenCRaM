/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { FC } from "react";
import { useEffect, useState } from "react";
import { observer } from "mobx-react";
import { useParams } from "next/navigation";
import type { UseFormRegister } from "react-hook-form";
import { useForm } from "react-hook-form";
// plane imports
import { useTranslation } from "@plane/i18n";
import { SeparatorHorizontal } from "lucide-react";
import { PlusIcon } from "@plane/propel/icons";
import { TOAST_TYPE, setPromiseToast, setToast } from "@plane/propel/toast";
import type { IProject, TIssue } from "@plane/types";
import { EIssueLayoutTypes } from "@plane/types";
import { cn, createIssuePayload } from "@plane/utils";
// hooks
import { useIssues } from "@/hooks/store/use-issues";
// local imports
import { QuickAddIssueFormRoot } from "./form";
import { endOfListSortOrder } from "./inline-row";
import { CreateIssueToastActionItems } from "../../create-issue-toast-action-items";
import { blankRowFields, requestRowTitleFocus } from "../row-line-tools";

export type TQuickAddIssueForm = {
  ref: React.RefObject<HTMLFormElement>;
  isOpen: boolean;
  projectDetail: IProject;
  hasError: boolean;
  register: UseFormRegister<TIssue>;
  onSubmit: () => void;
  isEpic: boolean;
};

export type TQuickAddIssueButton = {
  isEpic?: boolean;
  onClick: () => void;
};

type TQuickAddIssueRoot = {
  isQuickAddOpen?: boolean;
  layout: EIssueLayoutTypes;
  prePopulatedData?: Partial<TIssue>;
  QuickAddButton?: FC<TQuickAddIssueButton>;
  customQuickAddButton?: React.ReactNode;
  containerClassName?: string;
  setIsQuickAddOpen?: (isOpen: boolean) => void;
  quickAddCallback?: (projectId: string | null | undefined, data: TIssue) => Promise<TIssue | undefined>;
  isEpic?: boolean;
};

const defaultValues: Partial<TIssue> = {
  name: "",
};

export const QuickAddIssueRoot = observer(function QuickAddIssueRoot(props: TQuickAddIssueRoot) {
  const {
    isQuickAddOpen,
    layout,
    prePopulatedData,
    QuickAddButton,
    customQuickAddButton,
    containerClassName = "",
    setIsQuickAddOpen,
    quickAddCallback,
    isEpic = false,
  } = props;
  // i18n
  const { t } = useTranslation();
  // router
  const { workspaceSlug, projectId } = useParams();
  // store
  const { issueMap } = useIssues();
  // states
  const [isOpen, setIsOpen] = useState(isQuickAddOpen ?? false);
  // form info
  const {
    reset,
    handleSubmit,
    setFocus,
    register,
    formState: { errors, isSubmitting },
  } = useForm<TIssue>({ defaultValues });

  useEffect(() => {
    if (isQuickAddOpen !== undefined) {
      setIsOpen(isQuickAddOpen);
    }
  }, [isQuickAddOpen]);

  useEffect(() => {
    if (!isOpen) reset({ ...defaultValues });
  }, [isOpen, reset]);

  // oxlint-disable-next-line no-shadow
  const handleIsOpen = (isOpen: boolean) => {
    if (isQuickAddOpen !== undefined && setIsQuickAddOpen) {
      setIsQuickAddOpen(isOpen);
    } else {
      setIsOpen(isOpen);
    }
  };

  const onSubmitHandler = async (formData: TIssue) => {
    if (isSubmitting || !workspaceSlug || !projectId) return;

    reset({ ...defaultValues });

    const payload = createIssuePayload(projectId.toString(), {
      // oxlint-disable-next-line unicorn/no-useless-fallback-in-spread
      ...(prePopulatedData ?? {}),
      ...formData,
    });

    if (quickAddCallback) {
      const quickAddPromise = quickAddCallback(projectId.toString(), { ...payload });
      setPromiseToast<any>(quickAddPromise, {
        loading: isEpic ? t("epic.adding") : t("issue.adding"),
        success: {
          title: t("common.success"),
          message: () => `${isEpic ? t("epic.create.success") : t("issue.create.success")}`,
          actionItems: (data) => (
            // TODO: Translate here
            <CreateIssueToastActionItems
              workspaceSlug={workspaceSlug.toString()}
              projectId={projectId.toString()}
              issueId={data.id}
              isEpic={isEpic}
            />
          ),
        },
        error: {
          title: t("common.error.label"),
          message: (err) => err?.message || t("common.error.message"),
        },
      });

      await quickAddPromise;
    }
  };

  // List layout: a divider (section header) added at the end of the list, its name typed in place.
  const canAddDivider = layout === EIssueLayoutTypes.LIST && !!quickAddCallback && !isEpic;
  const handleAddDivider = () => {
    if (!quickAddCallback || !projectId) return;
    const boardId = projectId.toString();
    const sort_order = endOfListSortOrder(Object.values(issueMap).filter((issue) => issue?.project_id === boardId));
    const payload = createIssuePayload(boardId, {
      // oxlint-disable-next-line unicorn/no-useless-fallback-in-spread
      ...(prePopulatedData ?? {}),
      ...blankRowFields("divider"),
      sort_order,
    });
    quickAddCallback(boardId, payload)
      .then((created) => requestRowTitleFocus(created?.id))
      .catch((error: { message?: string }) =>
        setToast({ type: TOAST_TYPE.ERROR, title: "Could not add the divider", message: error?.message ?? "Try again." })
      );
  };

  if (!projectId) return null;

  const addButtons = (
    <>
      {QuickAddButton && <QuickAddButton isEpic={isEpic} onClick={() => handleIsOpen(true)} />}
      {customQuickAddButton && <>{customQuickAddButton}</>}
      {!QuickAddButton && !customQuickAddButton && (
        <button
          className="flex w-full cursor-pointer items-center gap-2 bg-layer-transparent px-2 py-3 hover:bg-layer-transparent-hover"
          onClick={() => handleIsOpen(true)}
        >
          <PlusIcon className="h-3.5 w-3.5 stroke-2" />
          <span className="text-13 font-medium">{t(`${isEpic ? "epic.new" : "issue.new"}`)}</span>
        </button>
      )}
    </>
  );

  return (
    <div
      className={cn(
        containerClassName,
        errors && errors?.name && errors?.name?.message ? `border-danger-strong bg-danger-subtle` : ``
      )}
    >
      {isOpen ? (
        <QuickAddIssueFormRoot
          isOpen={isOpen}
          layout={layout}
          prePopulatedData={prePopulatedData}
          projectId={projectId?.toString()}
          // oxlint-disable-next-line no-unneeded-ternary
          hasError={errors && errors?.name && errors?.name?.message ? true : false}
          setFocus={setFocus}
          register={register}
          onSubmit={handleSubmit(onSubmitHandler)}
          onClose={() => handleIsOpen(false)}
          isEpic={isEpic}
        />
      ) : canAddDivider ? (
        <div className="flex items-stretch">
          <div className="min-w-0 flex-grow">{addButtons}</div>
          <button
            type="button"
            className="flex flex-shrink-0 items-center gap-1.5 bg-layer-transparent px-3 text-13 font-medium text-tertiary hover:bg-layer-transparent-hover hover:text-primary"
            onClick={handleAddDivider}
            title="Add a divider (section header) at the end of the list"
          >
            <SeparatorHorizontal className="h-3.5 w-3.5" />
            <span>Add divider</span>
          </button>
        </div>
      ) : (
        addButtons
      )}
    </div>
  );
});
