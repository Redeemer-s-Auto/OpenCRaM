/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { observer } from "mobx-react";
import { FormProvider, useForm } from "react-hook-form";
// plane imports
import { useTranslation } from "@plane/i18n";
import { TOAST_TYPE, setToast } from "@plane/propel/toast";
import { EFileAssetType } from "@plane/types";
// components
import { BlueprintPicker, EMPTY_BLUEPRINT_CHOICE } from "@/components/blueprints/blueprint-picker";
import type { TBlueprintChoice } from "@/components/blueprints/blueprint-picker";
import ProjectCommonAttributes from "@/components/project/create/common-attributes";
import ProjectCreateHeader from "@/components/project/create/header";
import ProjectCreateButtons from "@/components/project/create/project-create-buttons";
// hooks
import { getCoverImageType, uploadCoverImage } from "@/helpers/cover-image.helper";
import { useProject } from "@/hooks/store/use-project";
import { usePlatformOS } from "@/hooks/use-platform-os";
// services
import { blueprintErrorMessage, blueprintService } from "@/services/blueprint.service";
// plane web types
import type { TProject } from "@plane/types";
import { ProjectAttributes } from "./attributes";
import { getProjectFormValues } from "./utils";

export type TCreateProjectFormProps = {
  setToFavorite?: boolean;
  workspaceSlug: string;
  onClose: () => void;
  handleNextStep: (projectId: string) => void;
  data?: Partial<TProject>;
  templateId?: string;
  updateCoverImageStatus: (projectId: string, coverImage: string) => Promise<void>;
};

export const CreateProjectForm = observer(function CreateProjectForm(props: TCreateProjectFormProps) {
  const { setToFavorite, workspaceSlug, data, onClose, handleNextStep, updateCoverImageStatus } = props;
  // store
  const { t } = useTranslation();
  const { addProjectToFavorites, createProject, updateProject, fetchProjectDetails } = useProject();
  // states
  const [shouldAutoSyncIdentifier, setShouldAutoSyncIdentifier] = useState(true);
  const [blueprintChoice, setBlueprintChoice] = useState<TBlueprintChoice>(EMPTY_BLUEPRINT_CHOICE);
  // form info
  const methods = useForm<TProject>({
    defaultValues: { ...getProjectFormValues(), ...data },
    reValidateMode: "onChange",
  });
  const { handleSubmit, reset, setValue } = methods;
  const { isMobile } = usePlatformOS();
  const handleAddToFavorites = (projectId: string) => {
    if (!workspaceSlug) return;

    addProjectToFavorites(workspaceSlug.toString(), projectId).catch(() => {
      setToast({
        type: TOAST_TYPE.ERROR,
        title: t("toast.error"),
        message: t("failed_to_remove_project_from_favorites"),
      });
    });
  };

  /** The cover picked in this window, set on the board once it exists (same as a blank board). */
  const applyCoverImage = async (
    projectId: string,
    coverImage: string | undefined,
    uploadedAssetUrl: string | null
  ) => {
    if (uploadedAssetUrl) {
      await updateCoverImageStatus(projectId, uploadedAssetUrl);
      await updateProject(workspaceSlug.toString(), projectId, { cover_image_url: uploadedAssetUrl });
    } else if (coverImage && coverImage.startsWith("http")) {
      await updateCoverImageStatus(projectId, coverImage);
      await updateProject(workspaceSlug.toString(), projectId, { cover_image_url: coverImage });
    }
  };

  /** New board from a blueprint: the server makes the board with the blueprint's whole design. */
  const createFromBlueprint = async (
    formData: Partial<TProject>,
    blueprintId: string,
    coverImage: string | undefined,
    uploadedAssetUrl: string | null
  ) => {
    try {
      const result = await blueprintService.use(workspaceSlug.toString(), blueprintId, {
        name: formData.name ?? "",
        identifier: formData.identifier ?? "",
        description: formData.description || undefined,
        logo_props: formData.logo_props?.in_use ? formData.logo_props : undefined,
        network: formData.network,
        relation_targets: Object.fromEntries(
          Object.entries(blueprintChoice.relationTargets).filter(([, projectId]) => Boolean(projectId))
        ),
        include_samples: blueprintChoice.includeSamples,
      });
      await fetchProjectDetails(workspaceSlug.toString(), result.project.id);
      await applyCoverImage(result.project.id, coverImage, uploadedAssetUrl);
      setToast({
        type: TOAST_TYPE.SUCCESS,
        title: t("success"),
        message:
          result.notes.length > 0
            ? `Board made from the blueprint. Note: ${result.notes.join(" ")}`
            : "Board made from the blueprint.",
      });
      if (setToFavorite) handleAddToFavorites(result.project.id);
      return handleNextStep(result.project.id);
    } catch (error) {
      setToast({ type: TOAST_TYPE.ERROR, title: t("toast.error"), message: blueprintErrorMessage(error) });
    }
  };

  const onSubmit = async (formData: Partial<TProject>) => {
    // Upper case identifier
    formData.identifier = formData.identifier?.toUpperCase();
    const coverImage = formData.cover_image_url;
    let uploadedAssetUrl: string | null = null;

    if (coverImage) {
      const imageType = getCoverImageType(coverImage);

      if (imageType === "local_static") {
        try {
          uploadedAssetUrl = await uploadCoverImage(coverImage, {
            workspaceSlug: workspaceSlug.toString(),
            entityIdentifier: "",
            entityType: EFileAssetType.PROJECT_COVER,
            isUserAsset: false,
          });
        } catch (error) {
          console.error("Error uploading cover image:", error);
          setToast({
            type: TOAST_TYPE.ERROR,
            title: t("toast.error"),
            message: error instanceof Error ? error.message : "Failed to upload cover image",
          });
          return Promise.reject(error);
        }
      } else {
        formData.cover_image = coverImage;
        formData.cover_image_asset = null;
      }
    }

    if (blueprintChoice.blueprint)
      return createFromBlueprint(formData, blueprintChoice.blueprint.id, coverImage, uploadedAssetUrl);

    return createProject(workspaceSlug.toString(), formData)
      .then(async (res) => {
        await applyCoverImage(res.id, coverImage, uploadedAssetUrl);
        setToast({
          type: TOAST_TYPE.SUCCESS,
          title: t("success"),
          message: t("project_created_successfully"),
        });

        if (setToFavorite) {
          handleAddToFavorites(res.id);
        }
        return handleNextStep(res.id);
      })
      .catch((err) => {
        try {
          // Handle the new error format where codes are nested in arrays under field names
          const errorData = err?.data ?? {};

          const nameError = errorData.name?.includes("PROJECT_NAME_ALREADY_EXIST");
          const identifierError = errorData?.identifier?.includes("PROJECT_IDENTIFIER_ALREADY_EXIST");
          const nameSpecialCharError = errorData?.name?.includes("PROJECT_NAME_CANNOT_CONTAIN_SPECIAL_CHARACTERS");

          if (nameError || identifierError || nameSpecialCharError) {
            if (nameError) {
              setToast({
                type: TOAST_TYPE.ERROR,
                title: t("toast.error"),
                message: t("project_name_already_taken"),
              });
            }

            if (identifierError) {
              setToast({
                type: TOAST_TYPE.ERROR,
                title: t("toast.error"),
                message: t("project_identifier_already_taken"),
              });
            }

            if (nameSpecialCharError) {
              setToast({
                type: TOAST_TYPE.ERROR,
                title: t("toast.error"),
                message: t("project_name_cannot_contain_special_characters"),
              });
            }
          } else {
            setToast({
              type: TOAST_TYPE.ERROR,
              title: t("toast.error"),
              message: t("something_went_wrong"),
            });
          }
        } catch (error) {
          // Fallback error handling if the error processing fails
          console.error("Error processing API error:", error);
          setToast({
            type: TOAST_TYPE.ERROR,
            title: t("toast.error"),
            message: t("something_went_wrong"),
          });
        }
      });
  };

  const handleClose = () => {
    onClose();
    setShouldAutoSyncIdentifier(true);
    setBlueprintChoice(EMPTY_BLUEPRINT_CHOICE);
    setTimeout(() => {
      reset();
    }, 300);
  };

  return (
    <FormProvider {...methods}>
      <ProjectCreateHeader handleClose={handleClose} isMobile={isMobile} />

      <form onSubmit={handleSubmit(onSubmit)} className="px-3">
        <div className="mt-9 space-y-6 pb-5">
          <BlueprintPicker
            workspaceSlug={workspaceSlug.toString()}
            value={blueprintChoice}
            onChange={(choice) => {
              setBlueprintChoice(choice);
              const logo = choice.blueprint?.logo_props;
              if (logo && "in_use" in logo && logo.in_use) setValue("logo_props", logo as TProject["logo_props"]);
            }}
          />
          <ProjectCommonAttributes
            setValue={setValue}
            isMobile={isMobile}
            shouldAutoSyncIdentifier={shouldAutoSyncIdentifier}
            setShouldAutoSyncIdentifier={setShouldAutoSyncIdentifier}
          />
          <ProjectAttributes isMobile={isMobile} />
        </div>
        <ProjectCreateButtons handleClose={handleClose} />
      </form>
    </FormProvider>
  );
});
