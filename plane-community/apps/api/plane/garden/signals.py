# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

import logging
import os

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from firebase_admin import firestore

from plane.db.models import Project, ProjectMember, ProjectNetwork, User
from plane.garden.services.firebase_identity import _firebase_app
from plane.garden.services.project_policy import garden_mode_enabled, garden_workspace_slug


logger = logging.getLogger("plane.garden.signals")
PLANE_ROLE_ADMIN = 20
DEFAULT_EMAIL = "garden-work-integration@garden.invalid"


def _register_project_mapping(project: Project) -> None:
    """Publish a Garden-owned organization mapping for projects created in Work.

    The mapping trigger in Firebase recomputes access projections for staff. This
    keeps projects created from the embedded Work UI from becoming invisible to
    Garden Work Planning/Integrations or to later Firebase-provisioned members.
    Failure is logged rather than aborting the Plane transaction; the project is
    still usable by its creator and can be reconciled later.
    """
    if not garden_mode_enabled() or project.workspace.slug != garden_workspace_slug():
        return
    try:
        now = timezone.now()
        ref = firestore.client(app=_firebase_app()).collection("workProjectMappings").document(str(project.id))
        existing = ref.get()
        ref.set(
            {
                "planeProjectId": str(project.id),
                "planeProjectIdentifier": project.identifier or None,
                "ownerType": "organization",
                "ownerId": None,
                "departmentId": None,
                "managedByGardenAccess": True,
                "requiredNetwork": ProjectNetwork.SECRET.value,
                "active": True,
                "source": "garden-work-ui",
                "createdAt": existing.get("createdAt") if existing.exists and existing.get("createdAt") else now,
                "updatedAt": now,
            },
            merge=True,
        )
    except Exception as exc:
        logger.warning("Unable to register Garden Work project mapping for %s: %s", project.id, type(exc).__name__)


@receiver(post_save, sender=Project, dispatch_uid="garden_integration_project_membership")
def ensure_integration_user_on_new_project(sender, instance: Project, created: bool, **kwargs):
    """Keep Garden service access and mappings aligned with newly created projects."""
    if not created:
        return

    _register_project_mapping(instance)

    email = os.environ.get("GARDEN_INTEGRATION_USER_EMAIL", DEFAULT_EMAIL).strip().lower() or DEFAULT_EMAIL
    user = User.objects.filter(email=email, is_active=True, is_bot=True).first()
    if user is None:
        return

    membership = ProjectMember.objects.filter(
        project=instance,
        member=user,
        deleted_at__isnull=True,
    ).first()
    if membership is None:
        ProjectMember.objects.create(
            project=instance,
            member=user,
            role=PLANE_ROLE_ADMIN,
            is_active=True,
        )
        return

    changed = []
    if membership.role != PLANE_ROLE_ADMIN:
        membership.role = PLANE_ROLE_ADMIN
        changed.append("role")
    if not membership.is_active:
        membership.is_active = True
        changed.append("is_active")
    if changed:
        membership.save(update_fields=[*changed, "updated_at"])
