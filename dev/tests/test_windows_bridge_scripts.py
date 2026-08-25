#!/usr/bin/env python3
"""Offline checks for the windowless Windows bridge launchers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "mcp_main" / "bridge" / "windows"
BRIDGE = ROOT / "mcp_main" / "bridge"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp_main.bridge import bridge_server  # noqa: E402


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


class WslBridgeCtlTest(unittest.TestCase):
    """The WSL-side control script must trigger Windows, never run the body."""

    def read(self) -> str:
        return (BRIDGE / "wsl_bridge_ctl.sh").read_text(encoding="utf-8")

    def test_triggers_windows_via_wscript_interop(self) -> None:
        script = self.read()
        self.assertIn("/mnt/c/Windows/System32/wscript.exe", script)
        self.assertIn("//B //Nologo", script)

    def test_uses_onshape_bridge_windows_launchers(self) -> None:
        script = self.read()
        self.assertIn(r"mcp_main\\bridge\\windows\\start-bridge-hidden.vbs", script)
        self.assertIn(r"mcp_main\\bridge\\windows\\restart-bridge-hidden.vbs", script)

    def test_defaults_match_onshape(self) -> None:
        script = self.read()
        self.assertIn("ONSHAPE_BRIDGE_PORT:-8766", script)
        # bash double-escapes the backslashes inside the double-quoted default.
        self.assertIn(r"ONSHAPE_WIN_ROOT:-C:\\MCP\\onshapescript", script)

    def test_supports_start_restart_status_only(self) -> None:
        script = self.read()
        self.assertIn("start)", script)
        self.assertIn("restart)", script)
        self.assertIn("status)", script)
        self.assertIn("use start|restart|status", script)
        self.assertNotIn("stop)", script)

    def test_status_checks_loopback_without_windows_call(self) -> None:
        script = self.read()
        self.assertIn("/dev/tcp/127.0.0.1/$PORT", script)
        self.assertIn("bridge reachable on 127.0.0.1:$PORT", script)

    def test_never_runs_bridge_body_in_wsl(self) -> None:
        script = self.read()
        # The body may be named in prose (header comment) but must never be
        # executed by this WSL-side trigger: no pythonw + bridge_server.py run.
        self.assertNotIn("pythonw.exe", script)
        self.assertIn("never starts", self.read())


if __name__ == "__main__":
    unittest.main()
