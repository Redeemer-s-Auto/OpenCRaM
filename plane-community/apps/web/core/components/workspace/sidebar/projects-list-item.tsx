/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { RefObject } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { combine } from "@atlaskit/pragmatic-drag-and-drop/combine";
import { draggable, dropTargetForElements } from "@atlaskit/pragmatic-drag-and-drop/element/adapter";
import { pointerOutsideOfPreview } from "@atlaskit/pragmatic-drag-and-drop/element/pointer-outside-of-preview";
import { setCustomNativeDragPreview } from "@atlaskit/pragmatic-drag-and-drop/element/set-custom-native-drag-preview";
import { attachInstruction, extractInstruction } from "@atlaskit/pragmatic-drag-and-drop-hitbox/tree-item";
import { observer } from "mobx-react";
import { useParams, useRouter } from "next/navigation";
import { createRoot } from "react-dom/client";
import scrollIntoView from "smooth-scroll-into-view-if-needed";
import { Settings, Share2, LogOut, MoreHorizontal } from "lucide-react";
import { Disclosure, Transition } from "@headlessui/react";
// plane imports
import { EUserPermissions, EUserPermissionsLevel, MEMBER_TRACKER_ELEMENTS } from "@plane/constants";
import { useOutsideClickDetector } from "@plane/hooks";
import { useTranslation } from "@plane/i18n";
import { Logo } from "@plane/propel/emoji-icon-picker";
import { LinkIcon, ArchiveIcon, ChevronRightIcon } from "@plane/propel/icons";
import { IconButton } from "@plane/propel/icon-button";
import { Tooltip } from "@plane/propel/tooltip";
import { CustomMenu, DropIndicator, DragHandle, ControlLink } from "@plane/ui";
import { cn } from "@plane/utils";
// components
import { DEFAULT_TAB_KEY, getTabUrl } from "@/components/navigation/tab-navigation-utils";
import { useTabPreferences } from "@/components/navigation/use-tab-preferences";
import { LeaveProjectModal } from "@/components/project/leave-project-modal";
import { PublishProjectModal } from "@/components/project/publish-project/modal";
// hooks
import { useAppTheme } from "@/hooks/store/use-app-theme";
import { useCommandPalette } from "@/hooks/store/use-command-palette";
import { useProject } from "@/hooks/store/use-project";
import { useUserPermissions } from "@/hooks/store/user";
import { useProjectNavigationPreferences } from "@/hooks/use-navigation-preferences";
import { usePlatformOS } from "@/hooks/use-platform-os";
// local imports
import { HIGHLIGHT_CLASS, highlightIssueOnDrop } from "../../issues/issue-layouts/utils";
import { ProjectNavigation } from "./project-navigation";
import { useNearViewport } from "./use-near-viewport";
import { SidebarCardTree } from "@/components/one-unit/sidebar-card-tree";
import { useNavigationItems } from "@/components/navigation/use-navigation-items";

type Props = {
  projectId: string;
  handleCopyText: () => void;
  handleOnProjectDrop?: (
    sourceId: string | undefined,
    destinationId: string | undefined,
    shouldDropAtEnd: boolean
  ) => void;
  projectListType: "JOINED" | "FAVORITES";
  disableDrag?: boolean;
  disableDrop?: boolean;
  isLastChild: boolean;
  renderInExtendedSidebar?: boolean;
  /** Set when other projects (or pages) sit inside this one: shows a chevron that opens/closes them. */
  childProjects?: { isOpen: boolean; onToggle: () => void };
  /** A folder board opens on its landing page instead of its default tab. */
  landingHref?: string;
};

const SidebarProjectsListItemFull = observer(function SidebarProjectsListItemFull(props: Props) {
  const {
    projectId,
    handleCopyText,
    disableDrag,
    disableDrop,
    isLastChild,
    handleOnProjectDrop,
    projectListType,
    renderInExtendedSidebar = false,
    childProjects,
    landingHref,
  } = props;
  // store hooks
  const { t } = useTranslation();
  const { getPartialProjectById } = useProject();
  const { isMobile } = usePlatformOS();
  const { allowPermissions } = useUserPermissions();
  const { getIsProjectListOpen, toggleProjectListOpen } = useCommandPalette();
  const { preferences: projectPreferences } = useProjectNavigationPreferences();
  const { isExtendedProjectSidebarOpened, toggleExtendedProjectSidebar, toggleAnySidebarDropdown, toggleSidebar } =
    useAppTheme();

  // states
  const [leaveProjectModalOpen, setLeaveProjectModal] = useState(false);
  const [publishModalOpen, setPublishModal] = useState(false);
  // The two modals, the "..." menu, the drag-handle tooltip and the outside-click listeners are set up the
  // first time the pointer or focus reaches the row (they are hidden until then), and the modals the first time
  // they open, so a sidebar of many boards does not build hundreds of closed menus on every load.
  const [isArmed, setIsArmed] = useState(false);
  const [isPublishModalMounted, setIsPublishModalMounted] = useState(false);
  const [isLeaveModalMounted, setIsLeaveModalMounted] = useState(false);
  const [isMenuActive, setIsMenuActive] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const isProjectListOpen = getIsProjectListOpen(projectId);
  const [instruction, setInstruction] = useState<"DRAG_OVER" | "DRAG_BELOW" | undefined>(undefined);
  // refs
  const actionSectionRef = useRef<HTMLButtonElement | null>(null);
  const projectRef = useRef<HTMLDivElement | null>(null);
  const dragHandleRef = useRef<HTMLButtonElement | null>(null);
  // router
  const { workspaceSlug, projectId: URLProjectId } = useParams();
  const router = useRouter();
  // derived values
  const project = getPartialProjectById(projectId);

  // Get available navigation items for this project
  const navigationItems = useNavigationItems({
    workspaceSlug: workspaceSlug.toString(),
    projectId,
    project,
    allowPermissions,
  });
  const availableTabKeys = navigationItems.map((item) => item.key);

  // Get preferences from hook
  const { tabPreferences } = useTabPreferences(workspaceSlug.toString(), projectId);
  const defaultTabKey = tabPreferences.defaultTab;
  // Validate that the default tab is available
  const validatedDefaultTabKey = availableTabKeys.includes(defaultTabKey) ? defaultTabKey : DEFAULT_TAB_KEY;
  const defaultTabUrl =
    landingHref ?? (project ? getTabUrl(workspaceSlug.toString(), project.id, validatedDefaultTabKey) : "");

  // toggle project list open
  const setIsProjectListOpen = useCallback(
    (value: boolean) => toggleProjectListOpen(projectId, value),
    [projectId, toggleProjectListOpen]
  );
  // auth
  const isAdmin = allowPermissions(
    [EUserPermissions.ADMIN],
    EUserPermissionsLevel.PROJECT,
    workspaceSlug.toString(),
    project?.id
  );
  const isAuthorized = allowPermissions(
    [EUserPermissions.ADMIN, EUserPermissions.MEMBER],
    EUserPermissionsLevel.PROJECT,
    workspaceSlug.toString(),
    project?.id
  );

  const handleLeaveProject = () => {
    setIsLeaveModalMounted(true);
    setLeaveProjectModal(true);
  };
  const handleOpenPublishModal = () => {
    setIsPublishModalMounted(true);
    setPublishModal(true);
  };
  const armRow = () => {
    if (!isArmed) setIsArmed(true);
  };

  useEffect(() => {
    const element = projectRef.current;
    const dragHandleElement = dragHandleRef.current;

    if (!element) return;

    return combine(
      draggable({
        element,
        canDrag: () => !disableDrag,
        dragHandle: dragHandleElement ?? undefined,
        getInitialData: () => ({ id: projectId, dragInstanceId: "PROJECTS" }),
        onDragStart: () => {
          setIsDragging(true);
        },
        onDrop: () => {
          setIsDragging(false);
        },
        onGenerateDragPreview: ({ nativeSetDragImage }) => {
          // Add a custom drag image
          setCustomNativeDragPreview({
            getOffset: pointerOutsideOfPreview({ x: "0px", y: "0px" }),
            render: ({ container }) => {
              const root = createRoot(container);
              root.render(
                <div className="flex items-center rounded-sm bg-surface-1 p-1 pr-2 text-13">
                  <div className="grid size-4 flex-shrink-0 place-items-center">
                    {project && <Logo logo={project?.logo_props} />}
                  </div>
                  <p className="truncate text-secondary">{project?.name}</p>
                </div>
              );
              return () => root.unmount();
            },
            nativeSetDragImage,
          });
        },
      }),
      dropTargetForElements({
        element,
        canDrop: ({ source }) =>
          !disableDrop && source?.data?.id !== projectId && source?.data?.dragInstanceId === "PROJECTS",
        // oxlint-disable-next-line no-shadow
        getData: ({ input, element }) => {
          const data = { id: projectId };

          // attach instruction for last in list
          return attachInstruction(data, {
            input,
            element,
            currentLevel: 0,
            indentPerLevel: 0,
            mode: isLastChild ? "last-in-group" : "standard",
          });
        },
        onDrag: ({ self }) => {
          const extractedInstruction = extractInstruction(self?.data)?.type;
          // check if the highlight is to be shown above or below
          setInstruction(
            extractedInstruction
              ? extractedInstruction === "reorder-below" && isLastChild
                ? "DRAG_BELOW"
                : "DRAG_OVER"
              : undefined
          );
        },
        onDragLeave: () => {
          setInstruction(undefined);
        },
        onDrop: ({ self, source }) => {
          setInstruction(undefined);
          const extractedInstruction = extractInstruction(self?.data)?.type;
          const currentInstruction = extractedInstruction
            ? extractedInstruction === "reorder-below" && isLastChild
              ? "DRAG_BELOW"
              : "DRAG_OVER"
            : undefined;
          if (!currentInstruction) return;

          const sourceId = source?.data?.id as string | undefined;
          const destinationId = self?.data?.id as string | undefined;

          handleOnProjectDrop?.(sourceId, destinationId, currentInstruction === "DRAG_BELOW");

          highlightIssueOnDrop(`sidebar-${sourceId}-${projectListType}`);
        },
      })
    );
    // isArmed: the drag handle is a new element once its tooltip is added
    // oxlint-disable-next-line eslint-plugin-react-hooks/exhaustive-deps
  }, [projectId, isLastChild, projectListType, handleOnProjectDrop, isArmed]);

  useEffect(() => {
    if (!isArmed) return;
    if (isMenuActive) toggleAnySidebarDropdown(true);
    else toggleAnySidebarDropdown(false);
  }, [isArmed, isMenuActive, toggleAnySidebarDropdown]);

  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    if (URLProjectId === project?.id) {
      setIsProjectListOpen(true);
      // Scroll to active project
      if (projectRef.current) {
        timeoutId = setTimeout(() => {
          if (projectRef.current) {
            scrollIntoView(projectRef.current, {
              behavior: "smooth",
              block: "center",
              scrollMode: "if-needed",
            });
          }
        }, 200);
      }
    }

    return () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [URLProjectId, project?.id, setIsProjectListOpen]);

  if (!project) return null;

  const isAccordionMode = projectPreferences.navigationMode === "ACCORDION";

  const handleItemClick = () => {
    if (projectPreferences.navigationMode === "ACCORDION") {
      setIsProjectListOpen(!isProjectListOpen);
    } else {
      router.push(defaultTabUrl);
      // on a phone the menu is a drawer over the page: it gets out of the way after a tap
      if (window.innerWidth < 768) toggleSidebar(true);
    }
    // close the extended sidebar if it is open
    if (isExtendedProjectSidebarOpened && !isAccordionMode) {
      toggleExtendedProjectSidebar(false);
    }
  };

  const menuClassName = cn(
    "pointer-events-none flex-shrink-0 opacity-0 group-hover/project-item:pointer-events-auto group-hover/project-item:opacity-100",
    {
      "pointer-events-auto opacity-100": isMenuActive,
    }
  );

  const shouldHighlightProject = URLProjectId === project?.id && projectPreferences.navigationMode !== "ACCORDION";

  return (
    <>
      {isPublishModalMounted && (
        <PublishProjectModal isOpen={publishModalOpen} projectId={projectId} onClose={() => setPublishModal(false)} />
      )}
      {isLeaveModalMounted && (
        <LeaveProjectModal
          project={project}
          isOpen={leaveProjectModalOpen}
          onClose={() => setLeaveProjectModal(false)}
        />
      )}
      {isArmed && (
        <SidebarRowListeners
          actionSectionRef={actionSectionRef}
          projectRef={projectRef}
          onOutsideMenuClick={() => setIsMenuActive(false)}
        />
      )}
      <Disclosure key={`${project.id}_${URLProjectId}`} defaultOpen={isProjectListOpen} as="div">
        <div
          id={`sidebar-${projectId}-${projectListType}`}
          className={cn("relative", {
            "bg-layer-1 opacity-60": isDragging,
          })}
          ref={projectRef}
          onPointerEnter={armRow}
          onFocus={armRow}
        >
          <DropIndicator classNames="absolute top-0" isVisible={instruction === "DRAG_OVER"} />
          <div
            className={cn(
              "group/project-item relative flex w-full items-center rounded-md px-2 py-1.5 text-primary hover:bg-layer-transparent-hover",
              {
                "bg-surface-2": isMenuActive,
                "bg-layer-transparent-active": shouldHighlightProject,
              }
            )}
            id={`${project?.id}`}
            data-sidebar-row=""
          >
            {!disableDrag &&
              (isArmed ? (
                <Tooltip
                  isMobile={isMobile}
                  tooltipContent={
                    project.sort_order === null ? t("join_the_project_to_rearrange") : t("drag_to_rearrange")
                  }
                  position="top-end"
                  disabled={isDragging}
                >
                  <button
                    type="button"
                    className={cn(
                      "absolute top-1/2 -left-3 hidden -translate-y-1/2 cursor-grab items-center justify-center rounded-sm text-placeholder group-hover/project-item:flex",
                      {
                        "cursor-not-allowed opacity-60": project.sort_order === null,
                        "cursor-grabbing": isDragging,
                        flex: isMenuActive || renderInExtendedSidebar,
                      }
                    )}
                    ref={dragHandleRef}
                  >
                    <DragHandle className="bg-transparent" />
                  </button>
                </Tooltip>
              ) : (
                <button
                  type="button"
                  className={cn(
                    "absolute top-1/2 -left-3 hidden -translate-y-1/2 cursor-grab items-center justify-center rounded-sm text-placeholder group-hover/project-item:flex",
                    {
                      "cursor-not-allowed opacity-60": project.sort_order === null,
                      "cursor-grabbing": isDragging,
                      flex: isMenuActive || renderInExtendedSidebar,
                    }
                  )}
                  ref={dragHandleRef}
                >
                  <DragHandle className="bg-transparent" />
                </button>
              ))}
            <>
              {/* Same chevron as the sidebar card tree. */}
              {childProjects && (
                <button
                  type="button"
                  aria-label={childProjects.isOpen ? `Close ${project.name}` : `Open ${project.name}`}
                  aria-expanded={childProjects.isOpen}
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    childProjects.onToggle();
                  }}
                  className="mr-1 -ml-1 grid size-4 flex-shrink-0 place-items-center rounded-sm text-placeholder hover:bg-layer-1"
                >
                  <ChevronRightIcon
                    className={cn("size-3 transition-transform", { "rotate-90": childProjects.isOpen })}
                  />
                </button>
              )}
              <ControlLink href={defaultTabUrl} className="flex flex-grow truncate" onClick={handleItemClick}>
                {isAccordionMode ? (
                  <Disclosure.Button
                    as="button"
                    type="button"
                    className={cn("flex w-full flex-grow items-center gap-1.5 text-left select-none", {})}
                    aria-label={
                      isProjectListOpen
                        ? t("aria_labels.projects_sidebar.close_project_menu")
                        : t("aria_labels.projects_sidebar.open_project_menu")
                    }
                  >
                    <div className="grid size-4 flex-shrink-0 place-items-center">
                      <Logo logo={project.logo_props} size={16} />
                    </div>
                    <p className="truncate text-13 font-medium text-secondary">{project.name}</p>
                  </Disclosure.Button>
                ) : (
                  <div className="flex w-full flex-grow items-center gap-1.5 text-left select-none">
                    <div className="grid size-4 flex-shrink-0 place-items-center">
                      <Logo logo={project.logo_props} size={16} />
                    </div>
                    <p className="truncate text-13 font-medium text-secondary">{project.name}</p>
                  </div>
                )}
              </ControlLink>
              <div className="flex items-center gap-1">
                {isArmed ? (
                  <CustomMenu
                    customButton={
                      <IconButton
                        ref={actionSectionRef}
                        variant="ghost"
                        size="sm"
                        icon={MoreHorizontal}
                        onClick={() => setIsMenuActive(!isMenuActive)}
                        className="text-placeholder"
                      />
                    }
                    className={menuClassName}
                    customButtonClassName="grid place-items-center"
                    placement="bottom-start"
                    ariaLabel={t("aria_labels.projects_sidebar.toggle_quick_actions_menu")}
                    useCaptureForOutsideClick
                    closeOnSelect
                    onMenuClose={() => setIsMenuActive(false)}
                  >
                    {/* TODO: Removed is_favorite logic due to the optimization in projects API */}
                    {/* {isAuthorized && (
                    <CustomMenu.MenuItem
                      onClick={project.is_favorite ? handleRemoveFromFavorites : handleAddToFavorites}
                    >
                      <span className="flex items-center justify-start gap-2">
                        <Star
                          className={cn("h-3.5 w-3.5 ", {
                            "fill-yellow-500 stroke-yellow-500": project.is_favorite,
                          })}
                        />
                        <span>{project.is_favorite ? t("remove_from_favorites") : t("add_to_favorites")}</span>
                      </span>
                    </CustomMenu.MenuItem>
                  )} */}

                    {/* publish project settings */}
                    {isAdmin && (
                      <CustomMenu.MenuItem onClick={handleOpenPublishModal}>
                        <div className="relative flex flex-shrink-0 items-center justify-start gap-2">
                          <div className="flex h-4 w-4 cursor-pointer items-center justify-center rounded-sm text-secondary transition-all duration-300 hover:bg-layer-1">
                            <Share2 className="h-3.5 w-3.5 stroke-[1.5]" />
                          </div>
                          <div>{t("publish_project")}</div>
                        </div>
                      </CustomMenu.MenuItem>
                    )}
                    <CustomMenu.MenuItem onClick={handleCopyText}>
                      <span className="flex items-center justify-start gap-2">
                        <LinkIcon className="h-3.5 w-3.5 stroke-[1.5]" />
                        <span>{t("copy_link")}</span>
                      </span>
                    </CustomMenu.MenuItem>
                    {isAuthorized && (
                      <CustomMenu.MenuItem
                        onClick={() => {
                          router.push(`/${workspaceSlug}/projects/${project?.id}/archives/issues`);
                        }}
                      >
                        <div className="flex cursor-pointer items-center justify-start gap-2">
                          <ArchiveIcon className="h-3.5 w-3.5 stroke-[1.5]" />
                          <span>{t("archives")}</span>
                        </div>
                      </CustomMenu.MenuItem>
                    )}
                    <CustomMenu.MenuItem
                      onClick={() => {
                        router.push(`/${workspaceSlug}/settings/projects/${project?.id}`);
                      }}
                    >
                      <div className="flex cursor-pointer items-center justify-start gap-2">
                        <Settings className="h-3.5 w-3.5 stroke-[1.5]" />
                        <span>{t("settings")}</span>
                      </div>
                    </CustomMenu.MenuItem>
                    {/* leave project */}
                    {!isAuthorized && (
                      <CustomMenu.MenuItem
                        onClick={handleLeaveProject}
                        data-ph-element={MEMBER_TRACKER_ELEMENTS.SIDEBAR_PROJECT_QUICK_ACTIONS}
                      >
                        <div className="flex items-center justify-start gap-2">
                          <LogOut className="h-3.5 w-3.5 stroke-[1.5]" />
                          <span>{t("leave_project")}</span>
                        </div>
                      </CustomMenu.MenuItem>
                    )}
                  </CustomMenu>
                ) : (
                  <SidebarRowMenuStandIn
                    className={menuClassName}
                    ariaLabel={t("aria_labels.projects_sidebar.toggle_quick_actions_menu")}
                  />
                )}
                {isAccordionMode && (
                  <IconButton
                    variant="ghost"
                    size="sm"
                    icon={ChevronRightIcon}
                    onClick={() => setIsProjectListOpen(!isProjectListOpen)}
                    className={cn("hidden text-placeholder group-hover/project-item:inline-flex", {
                      "inline-flex": isMenuActive,
                    })}
                    iconClassName={cn("transition-transform", {
                      "rotate-90": isProjectListOpen,
                    })}
                    aria-label={t(
                      isProjectListOpen
                        ? "aria_labels.projects_sidebar.close_project_menu"
                        : "aria_labels.projects_sidebar.open_project_menu"
                    )}
                  />
                )}
              </div>
            </>
          </div>
          {isAccordionMode && (
            <Transition
              show={isProjectListOpen}
              enter="transition duration-100 ease-out"
              enterFrom="transform scale-95 opacity-0"
              enterTo="transform scale-100 opacity-100"
              leave="transition duration-75 ease-out"
              leaveFrom="transform scale-100 opacity-100"
              leaveTo="transform scale-95 opacity-0"
            >
              {isProjectListOpen && (
                <Disclosure.Panel as="div" className="relative mt-1 mb-1.5 flex flex-col gap-0.5 pl-6">
                  <div className="absolute top-0 bottom-1 left-[15px] w-[1px] bg-layer-3" />
                  <ProjectNavigation workspaceSlug={workspaceSlug.toString()} projectId={projectId.toString()} />
                  <SidebarCardTree workspaceSlug={workspaceSlug.toString()} projectId={projectId.toString()} />
                </Disclosure.Panel>
              )}
            </Transition>
          )}
          {isLastChild && <DropIndicator isVisible={instruction === "DRAG_BELOW"} />}
        </div>
      </Disclosure>
    </>
  );
});

/** The outside-click listeners of a row, added once the row is in use. */
function SidebarRowListeners(props: {
  actionSectionRef: RefObject<HTMLButtonElement | null>;
  projectRef: RefObject<HTMLDivElement | null>;
  onOutsideMenuClick: () => void;
}) {
  const { actionSectionRef, projectRef, onOutsideMenuClick } = props;
  useOutsideClickDetector(actionSectionRef, onOutsideMenuClick);
  useOutsideClickDetector(projectRef, () => projectRef?.current?.classList?.remove(HIGHLIGHT_CLASS));
  return null;
}

/** Looks exactly like the closed "..." menu (same wrapper and buttons); the real menu replaces it on first use. */
function SidebarRowMenuStandIn(props: { className: string; ariaLabel: string }) {
  return (
    <div className={cn("relative w-min text-left", props.className)} role="presentation" data-main-menu="true">
      {/* aria-haspopup / aria-expanded as on the real menu button: the phone drawer styles buttons by them */}
      <button
        type="button"
        className="grid place-items-center"
        tabIndex={0}
        aria-label={props.ariaLabel}
        aria-haspopup="menu"
        aria-expanded={false}
      >
        <IconButton variant="ghost" size="sm" icon={MoreHorizontal} className="text-placeholder" />
      </button>
    </div>
  );
}

/**
 * One board row of the sidebar. Far from the screen it is a plain copy (same look; no menus, drag-and-drop or
 * permission look-ups); near the screen, once touched, or when it is the open board, it is the full row.
 */
export const SidebarProjectsListItem = observer(function SidebarProjectsListItem(props: Props) {
  const {
    projectId,
    disableDrag,
    isLastChild,
    projectListType,
    renderInExtendedSidebar = false,
    childProjects,
  } = props;
  const { t } = useTranslation();
  const { workspaceSlug, projectId: URLProjectId } = useParams();
  const { getPartialProjectById } = useProject();
  const { getIsProjectListOpen } = useCommandPalette();
  const { preferences: projectPreferences } = useProjectNavigationPreferences();
  const [rowElement, setRowElement] = useState<HTMLDivElement | null>(null);
  const isNear = useNearViewport(rowElement);
  const [isTouched, setIsTouched] = useState(false);
  const project = getPartialProjectById(projectId);

  const isAccordionMode = projectPreferences.navigationMode === "ACCORDION";
  const isAccordionOpen = isAccordionMode && getIsProjectListOpen(projectId);
  if (isNear || isTouched || URLProjectId === projectId || isAccordionOpen)
    return <SidebarProjectsListItemFull {...props} />;
  if (!project) return null;

  const rowLabel = (
    <>
      <div className="grid size-4 flex-shrink-0 place-items-center">
        <Logo logo={project.logo_props} size={16} />
      </div>
      <p className="truncate text-13 font-medium text-secondary">{project.name}</p>
    </>
  );
  const href = props.landingHref ?? getTabUrl(workspaceSlug?.toString() ?? "", project.id, DEFAULT_TAB_KEY);
  return (
    <div>
      <div
        id={`sidebar-${projectId}-${projectListType}`}
        className="relative"
        ref={setRowElement}
        onPointerEnter={() => setIsTouched(true)}
        onFocus={() => setIsTouched(true)}
      >
        <DropIndicator classNames="absolute top-0" isVisible={false} />
        <div
          className="group/project-item relative flex w-full items-center rounded-md px-2 py-1.5 text-primary hover:bg-layer-transparent-hover"
          id={`${project.id}`}
          data-sidebar-row=""
        >
          {!disableDrag && (
            <button
              type="button"
              className={cn(
                "absolute top-1/2 -left-3 hidden -translate-y-1/2 cursor-grab items-center justify-center rounded-sm text-placeholder group-hover/project-item:flex",
                {
                  "cursor-not-allowed opacity-60": project.sort_order === null,
                  flex: renderInExtendedSidebar,
                }
              )}
            >
              <DragHandle className="bg-transparent" />
            </button>
          )}
          {childProjects && (
            <button
              type="button"
              aria-label={childProjects.isOpen ? `Close ${project.name}` : `Open ${project.name}`}
              aria-expanded={childProjects.isOpen}
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                childProjects.onToggle();
              }}
              className="mr-1 -ml-1 grid size-4 flex-shrink-0 place-items-center rounded-sm text-placeholder hover:bg-layer-1"
            >
              <ChevronRightIcon className={cn("size-3 transition-transform", { "rotate-90": childProjects.isOpen })} />
            </button>
          )}
          <a href={href} target="_blank" className="flex flex-grow truncate" draggable={false}>
            {isAccordionMode ? (
              <button
                type="button"
                className="flex w-full flex-grow items-center gap-1.5 text-left select-none"
                aria-label={t("aria_labels.projects_sidebar.open_project_menu")}
                aria-expanded={false}
              >
                {rowLabel}
              </button>
            ) : (
              <div className="flex w-full flex-grow items-center gap-1.5 text-left select-none">{rowLabel}</div>
            )}
          </a>
          <div className="flex items-center gap-1">
            <SidebarRowMenuStandIn
              className="pointer-events-none flex-shrink-0 opacity-0 group-hover/project-item:pointer-events-auto group-hover/project-item:opacity-100"
              ariaLabel={t("aria_labels.projects_sidebar.toggle_quick_actions_menu")}
            />
            {isAccordionMode && (
              <IconButton
                variant="ghost"
                size="sm"
                icon={ChevronRightIcon}
                className="hidden text-placeholder group-hover/project-item:inline-flex"
                iconClassName="transition-transform"
                aria-label={t("aria_labels.projects_sidebar.open_project_menu")}
              />
            )}
          </div>
        </div>
        {isLastChild && <DropIndicator isVisible={false} />}
      </div>
    </div>
  );
});
