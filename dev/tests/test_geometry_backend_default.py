#!/usr/bin/env python3
"""The shipped default for the machine-local geometry backend selection.

``config/geometry-backend.json`` is operator-owned state: the selected
executable, argument template and tolerances of *this* install. It is excluded
from the Release artifact (see ``docs/operations/RELEASE.md``), so a fresh
install has no such file at all. Absence therefore has to mean "never
configured" -- a disabled backend -- and never "broken install".

These tests pin that rule and pin each mode's ``geometry-backend.json.example``
to the in-code default, so a shipped example cannot drift away from what the
loader substitutes.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fdm_analysis.configuration import (  # noqa: E402
    DEFAULT_COMMAND_GEOMETRY_CONFIG,
    load_command_geometry_config,
)

#: The two modes that own a geometry backend selection.
MODES = ("onshape_browser_mode", "onshape_rest_api_mode")


class GeometryBackendDefaultTest(unittest.TestCase):
    def test_missing_live_config_is_the_disabled_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "config" / "geometry-backend.json"
            self.assertFalse(missing.exists())
            config = load_command_geometry_config(missing)
        self.assertEqual(config, DEFAULT_COMMAND_GEOMETRY_CONFIG)
        self.assertFalse(config["enabled"])
        self.assertEqual(config["provider"], "command")

    def test_the_default_is_returned_as_an_editable_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_command_geometry_config(Path(tmp) / "absent.json")
            config["enabled"] = True
            config["linearToleranceMm"] = 9.0
        self.assertFalse(DEFAULT_COMMAND_GEOMETRY_CONFIG["enabled"])
        self.assertEqual(DEFAULT_COMMAND_GEOMETRY_CONFIG["linearToleranceMm"], 0.05)

    def test_a_malformed_existing_config_still_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "geometry-backend.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_command_geometry_config(path)

    def test_an_existing_config_with_wrong_types_still_raises(self) -> None:
        """Only ABSENCE falls back; an operator mistake must stay visible."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "geometry-backend.json"
            path.write_text(json.dumps({**DEFAULT_COMMAND_GEOMETRY_CONFIG, "enabled": "yes"}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "enabled must be a boolean"):
                load_command_geometry_config(path)

    def test_every_mode_ships_an_example_equal_to_the_default(self) -> None:
        for mode in MODES:
            directory = ROOT / mode / "config"
            example = directory / "geometry-backend.json.example"
            self.assertTrue(example.is_file(), example)
            self.assertEqual(
                json.loads(example.read_text(encoding="utf-8")),
                DEFAULT_COMMAND_GEOMETRY_CONFIG,
                example,
            )
            live = directory / "geometry-backend.json"
            self.assertFalse(
                live.exists(),
                f"{live} is machine-local operator state and must not be committed",
            )

    def test_both_mode_statuses_report_absence_without_raising(self) -> None:
        from onshape_browser_mode.geometry import browser_geometry_status
        from onshape_rest_api_mode.geometry import geometry_backend_status

        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "geometry-backend.json"
            reports = (
                geometry_backend_status(missing),
                browser_geometry_status(missing),
            )
        for report in reports:
            self.assertFalse(report["configured"])
            self.assertFalse(report["ready"])
            self.assertFalse(report["configFilePresent"])
            self.assertEqual(report["configPath"], str(missing))
            self.assertFalse(report["bambuIncluded"])


if __name__ == "__main__":
    unittest.main()
