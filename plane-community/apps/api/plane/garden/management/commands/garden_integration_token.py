# Copyright (c) 2026 The Garden contributors
# SPDX-License-Identifier: AGPL-3.0-only

import os
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from plane.db.models import APIToken, Project, ProjectMember, User, Workspace, WorkspaceMember


PLANE_ROLE_ADMIN = 20
DEFAULT_EMAIL = "garden-work-integration@garden.invalid"
DEFAULT_LABEL = "Garden Work server integration"


@transaction.atomic
def reconcile_integration_identity(*, rotate: bool = False):
    workspace_slug = os.environ.get("GARDEN_WORKSPACE_SLUG", "the-garden").strip() or "the-garden"
    workspace = Workspace.objects.filter(slug=workspace_slug).first()
    if workspace is None:
        raise CommandError(f"Workspace '{workspace_slug}' does not exist. Bootstrap Garden Work first.")

    email = os.environ.get("GARDEN_INTEGRATION_USER_EMAIL", DEFAULT_EMAIL).strip().lower() or DEFAULT_EMAIL
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User(
            email=email,
            username=f"garden-work-integration-{uuid.uuid4().hex[:16]}",
            display_name="Garden Work Integration",
            first_name="Garden Work",
            last_name="Integration",
            is_active=True,
            is_bot=True,
            is_managed=True,
            is_password_autoset=True,
            is_email_verified=True,
            user_timezone=os.environ.get("GARDEN_WORKSPACE_TIMEZONE", "America/Chicago").strip() or "America/Chicago",
        )
        user.set_unusable_password()
        user.save()
    else:
        changed = []
        desired = {
            "display_name": "Garden Work Integration",
            "is_active": True,
            "is_bot": True,
            "is_managed": True,
            "is_password_autoset": True,
            "is_email_verified": True,
        }
        for field, value in desired.items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                changed.append(field)
        if changed:
            user.save(update_fields=[*changed, "updated_at"])

    membership = WorkspaceMember.objects.filter(
        workspace=workspace,
        member=user,
        deleted_at__isnull=True,
    ).first()
    if membership is None:
        WorkspaceMember.objects.create(
            workspace=workspace,
            member=user,
            role=PLANE_ROLE_ADMIN,
            is_active=True,
        )
    else:
        updates = []
        if membership.role != PLANE_ROLE_ADMIN:
            membership.role = PLANE_ROLE_ADMIN
            updates.append("role")
        if not membership.is_active:
            membership.is_active = True
            updates.append("is_active")
        if updates:
            membership.save(update_fields=[*updates, "updated_at"])

    project_count = 0
    for project in Project.objects.filter(workspace=workspace, deleted_at__isnull=True).iterator():
        project_count += 1
        project_membership = ProjectMember.objects.filter(
            project=project,
            member=user,
            deleted_at__isnull=True,
        ).first()
        if project_membership is None:
            ProjectMember.objects.create(
                project=project,
                member=user,
                role=PLANE_ROLE_ADMIN,
                is_active=True,
            )
        else:
            updates = []
            if project_membership.role != PLANE_ROLE_ADMIN:
                project_membership.role = PLANE_ROLE_ADMIN
                updates.append("role")
            if not project_membership.is_active:
                project_membership.is_active = True
                updates.append("is_active")
            if updates:
                project_membership.save(update_fields=[*updates, "updated_at"])

    label = os.environ.get("GARDEN_INTEGRATION_TOKEN_LABEL", DEFAULT_LABEL).strip() or DEFAULT_LABEL
    existing_tokens = APIToken.objects.filter(user=user, workspace=workspace, label=label, is_active=True)
    if rotate:
        existing_tokens.update(is_active=False)

    token = None if rotate else existing_tokens.order_by("-created_at").first()
    created = token is None
    if token is None:
        token = APIToken.objects.create(
            user=user,
            workspace=workspace,
            label=label,
            description="Server-only Garden Firebase Functions integration token",
            is_active=True,
            is_service=True,
            user_type=1,
            allowed_rate_limit=os.environ.get("GARDEN_INTEGRATION_RATE_LIMIT", "600/min").strip() or "600/min",
        )

    return user, workspace, token, project_count, created


class Command(BaseCommand):
    help = "Create/rotate the Garden-owned Plane service token and reconcile its project memberships."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rotate",
            action="store_true",
            help="Deactivate existing active Garden integration tokens and issue a replacement.",
        )

    def handle(self, *args, **options):
        user, workspace, token, project_count, created = reconcile_integration_identity(rotate=bool(options["rotate"]))
        self.stdout.write(self.style.SUCCESS("Garden Work integration identity reconciled."))
        self.stdout.write(f"Workspace: {workspace.slug}")
        self.stdout.write(f"Service user: {user.email}")
        self.stdout.write(f"Project memberships reconciled: {project_count}")
        self.stdout.write(f"Token status: {'created' if created else 'existing'}")
        self.stdout.write("")
        self.stdout.write("Store this value as the Firebase Functions secret PLANE_WORK_API_TOKEN:")
        self.stdout.write(token.token)
        self.stdout.write("")
        self.stdout.write("Treat the token as a server credential. Never expose it to browser/mobile code or commit it to Git.")
