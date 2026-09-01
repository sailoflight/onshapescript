from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fdm_analysis import StepArtifact
from fdm_analysis.conversion import CommandStepConverter
from fdm_analysis.conversion.cadquery_step_to_stl import host_path
from fdm_analysis.conversion.command import subprocess_platform_kwargs


SCRIPT = """#!/usr/bin/env python3
import pathlib
import sys
out = pathlib.Path(sys.argv[sys.argv.index('--output') + 1])
out.write_text('''solid fixture
facet normal 0 0 1
outer loop
vertex 0 0 0
vertex 1 0 0
vertex 0 1 0
endloop
endfacet
endsolid fixture
''', encoding='ascii')
"""


class CommandStepConverterTest(unittest.TestCase):
    def _step(self, root: Path):
        path = root / "source model.step"
        path.write_text("ISO-10303-21;\nEND-ISO-10303-21;\n", encoding="ascii")
        return StepArtifact.from_path(path, units="mm", source={"mode": "fixture"})

    def _executable(self, root: Path, source=SCRIPT):
        path = root / "fixture converter"
        path.write_text(source, encoding="utf-8")
        os.chmod(path, 0o755)
        return path

    def test_real_subprocess_uses_argv_and_validates_stl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            converter = CommandStepConverter(
                self._executable(root),
                name="fixture-cli",
                version="1.0",
                argument_template=(
                    "--input", "{input}",
                    "--output", "{output}",
                    "--linear", "{linear_tolerance_mm}",
                    "--angular", "{angular_tolerance_degrees}",
                ),
            )
            mesh = converter.convert(
                self._step(root),
                output_path=root / "output mesh.stl",
                linear_tolerance_mm=0.05,
                angular_tolerance_degrees=5,
            )
        self.assertEqual(mesh.triangle_count, 1)
        self.assertEqual(mesh.units, "mm")
        self.assertEqual(mesh.converter["name"], "fixture-cli")
        self.assertEqual(mesh.converter["execution"], "argv-no-shell")
        self.assertEqual(mesh.converter["argumentTemplate"][0], "--input")

    def test_command_preserves_paths_with_spaces_as_single_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            converter = CommandStepConverter(
                self._executable(root),
                name="fixture-cli",
                version="1",
                argument_template=("--input", "{input}", "--output", "{output}"),
            )
            command = converter.build_command(
                self._step(root),
                output_path=root / "output mesh.stl",
                linear_tolerance_mm=0.1,
                angular_tolerance_degrees=3,
            )
        self.assertIsInstance(command, list)
        self.assertTrue(command[2].endswith("source model.step"))
        self.assertTrue(command[4].endswith("output mesh.stl"))

    def test_windows_backend_uses_no_console_window_flag(self):
        self.assertEqual(subprocess_platform_kwargs("posix"), {})
        flags = subprocess_platform_kwargs("nt")
        self.assertEqual(flags["creationflags"] & 0x08000000, 0x08000000)

    def test_cadquery_cli_maps_windows_paths_without_shell(self):
        self.assertEqual(
            host_path(r"C:\MCP\onshapescript\model.step"),
            Path("/mnt/c/MCP/onshapescript/model.step"),
        )
        self.assertEqual(host_path("/tmp/model.step"), Path("/tmp/model.step"))
        with self.assertRaisesRegex(ValueError, "absolute"):
            host_path("relative/model.step")

    def test_template_and_executable_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(ValueError, r"include \{input\} and \{output\}"):
                CommandStepConverter(
                    root / "missing",
                    name="fixture",
                    version="1",
                    argument_template=("{input}",),
                )
            with self.assertRaisesRegex(ValueError, "unsupported placeholder"):
                CommandStepConverter(
                    root / "missing",
                    name="fixture",
                    version="1",
                    argument_template=("{input}", "{output}", "{shell}"),
                )
            converter = CommandStepConverter(
                root / "missing",
                name="fixture",
                version="1",
                argument_template=("{input}", "{output}"),
            )
            self.assertFalse(converter.capabilities()["available"])
            with self.assertRaisesRegex(RuntimeError, "executable is unavailable"):
                converter.convert(
                    self._step(root),
                    output_path=root / "out.stl",
                    linear_tolerance_mm=0.1,
                    angular_tolerance_degrees=5,
                )

    def test_nonzero_exit_and_invalid_stl_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failing = self._executable(root, "#!/usr/bin/env python3\nraise SystemExit(3)\n")
            converter = CommandStepConverter(
                failing,
                name="fixture",
                version="1",
                argument_template=("{input}", "{output}"),
            )
            with self.assertRaisesRegex(RuntimeError, "exited 3"):
                converter.convert(
                    self._step(root),
                    output_path=root / "failed.stl",
                    linear_tolerance_mm=0.1,
                    angular_tolerance_degrees=5,
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            invalid = self._executable(
                root,
                "#!/usr/bin/env python3\nimport pathlib, sys\npathlib.Path(sys.argv[-1]).write_text('invalid')\n",
            )
            converter = CommandStepConverter(
                invalid,
                name="fixture",
                version="1",
                argument_template=("{input}", "{output}"),
            )
            with self.assertRaisesRegex(ValueError, "complete triangles"):
                converter.convert(
                    self._step(root),
                    output_path=root / "invalid.stl",
                    linear_tolerance_mm=0.1,
                    angular_tolerance_degrees=5,
                )


if __name__ == "__main__":
    unittest.main()
