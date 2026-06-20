"""Tests for translation string layout."""

from __future__ import annotations

import json
from pathlib import Path


def test_options_credentials_strings_exist() -> None:
    """Options credentials step strings live under options.step.credentials."""
    strings_path = (
        Path(__file__).parent.parent
        / "custom_components"
        / "deyecloud"
        / "strings.json"
    )
    strings = json.loads(strings_path.read_text(encoding="utf-8"))
    credentials = strings["options"]["step"]["credentials"]
    assert credentials["title"] == "Update credentials"
    assert "username" in credentials["data"]
    assert "config" not in strings or "credentials" not in strings["config"]["step"]
