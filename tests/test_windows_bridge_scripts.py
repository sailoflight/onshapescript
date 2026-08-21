#!/usr/bin/env python3
"""Offline checks for the windowless Windows bridge launchers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = ROOT / "tools" / "windows"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import bridge_server  # noqa: E402


class WindowlessBridgeScriptTest(unittest.TestCase):
    def read(self, name: str) -> str:
        return (WINDOWS / name).read_text(encoding="utf-8")

    def test_hidden_start_uses_pythonw_and_no_dialogs(self) -> None:
        script = self.read("start-bridge-hidden.vbs")
        self.assertIn(r".venv\Scripts\pythonw.exe", script)
        self.assertIn("shell.Run command, 0, False", script)
        self.assertNotIn("WScript.Echo", script)

    def test_hidden_restart_runs_powershell_without_window(self) -> None:
        script = self.read("restart-bridge-hidden.vbs")
        self.assertIn("powershell.exe -NoProfile", script)
        self.assertIn("shell.Run(command, 0, True)", script)

    def test_batch_launchers_delegate_to_hidden_vbs(self) -> None:
        self.assertIn("start-bridge-hidden.vbs", self.read("start-bridge.bat"))
        self.assertIn("restart-bridge-hidden.vbs", self.read("restart-bridge.bat"))
        self.assertIn("start-bridge-hidden.vbs", self.read("setup-autostart.bat"))

    def test_task_and_restart_use_pythonw(self) -> None:
        task = self.read("register-bridge-task.ps1")
        restart = self.read("restart-bridge.ps1")
        self.assertIn(r".venv\Scripts\pythonw.exe", task)
        self.assertIn(r".venv\Scripts\pythonw.exe", restart)
        self.assertIn("'pythonw.exe'", restart)
        self.assertIn("-WindowStyle Hidden", restart)

    def test_console_output_is_safe_under_pythonw(self) -> None:
        with mock.patch.object(bridge_server.sys, "stdout", None):
            bridge_server._console("not visible")


if __name__ == "__main__":
    unittest.main()
