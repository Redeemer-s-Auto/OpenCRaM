# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Pages inside pages: the sidebar page tree and "Link to page" blocks.

Every answer is worked out for the caller with the same rules as the project
pages list (``plane.app.views.page.base.PageViewSet``): a page is sent only when
the caller reaches its board, the sharing rules do not hide it, and it is public
or their own. Nothing here adds a way to see a page.
"""
