# Copyright (c) 2026-present OpenCRaM contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The live view block keeps its settings through the server's HTML clean-up."""

import pytest

from plane.utils.content_validator import validate_html_content

BLOCK = (
    '<div data-block-type="inline-view" '
    'data-view-config="{&quot;source&quot;:{&quot;type&quot;:&quot;project&quot;},&quot;layout&quot;:&quot;board&quot;}">'
    "</div>"
)


@pytest.mark.unit
def test_view_block_keeps_its_settings():
    ok, error, cleaned = validate_html_content(BLOCK)
    assert ok, error
    result = cleaned if cleaned is not None else BLOCK
    assert 'data-block-type="inline-view"' in result
    assert "data-view-config=" in result and "board" in result


@pytest.mark.unit
def test_script_next_to_a_view_block_is_still_removed():
    ok, _, cleaned = validate_html_content(BLOCK + "<script>alert(1)</script>")
    if ok:
        assert cleaned is not None and "<script" not in cleaned
