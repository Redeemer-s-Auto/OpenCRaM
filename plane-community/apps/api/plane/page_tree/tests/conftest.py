# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The sharing-rule cast (one workspace, boards Alpha and Beta, five people) serves these tests too."""

from plane.sharing.tests.conftest import cast, eager_celery

__all__ = ["cast", "eager_celery"]
