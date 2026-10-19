# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Toggle and column blocks survive the server's HTML clean-up."""

import pytest

from plane.utils.content_validator import validate_html_content

TOGGLE = (
    '<details data-block-type="toggle" data-open="false">'
    '<summary data-block-type="toggle-title">Title</summary>'
    '<div data-block-type="toggle-content"><p>Inside</p></div></details>'
)
COLUMNS = (
    '<div data-block-type="column-list" data-columns="3">'
    '<div data-block-type="column"><p>A</p></div>'
    '<div data-block-type="column"><p>B</p></div>'
    '<div data-block-type="column"><p>C</p></div></div>'
)


@pytest.mark.unit
@pytest.mark.parametrize("html", [TOGGLE, COLUMNS])
def test_layout_blocks_keep_their_settings(html):
    ok, error, cleaned = validate_html_content(html)
    assert ok, error
    result = cleaned if cleaned is not None else html
    for needle in ['data-open="false"', 'data-columns="3"', "<summary", 'data-block-type="column"']:
        if needle in html:
            assert needle in result, (needle, result)


@pytest.mark.unit
def test_scripts_inside_layout_blocks_are_still_removed():
    html = TOGGLE.replace("<p>Inside</p>", "<p>Inside</p><script>alert(1)</script>")
    ok, _, cleaned = validate_html_content(html)
    # Either the whole body is refused, or the script is cut out.
    if ok:
        assert cleaned is not None and "<script" not in cleaned
