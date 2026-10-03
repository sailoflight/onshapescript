"""Offline gates for the geometry-leg interference check (issue #20).

The whole point of this capability is that a check which did not run must not be
able to read as a clean model, so most of this file is about verdict honesty
rather than arithmetic: no runner is started unless a test says so, and every
failure surface must land on an explicit non-clean verdict.

One test group does run real geometry (``LiveCadQuery``): it builds two solids
whose intersection is known analytically and asserts the measured volume. It
skips -- with a stated reason, never as a pass -- when no interpreter on this
machine can import CadQuery.
"""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONVERTER = ROOT / "fdm_analysis" / "conversion" / "cadquery_interference.py"
sys.path.insert(0, str(ROOT))

from onshape_rest_api_mode import interference  # noqa: E402


def _config(path: Path, *, enabled: bool = True, template: list[str] | None = None, **extra: object) -> Path:
    payload: dict[str, object] = {
        "enabled": enabled,
        "provider": "command",
        "name": "cadquery-ocp-wsl",
        "version": "cadquery-2.8.0+OCP-7.9.3.1",
        "executable": "/usr/bin/wsl.exe" if enabled else "",
        "argumentTemplate": template
        if template is not None
        else [
            "-d",
            "Ubuntu-24.04",
            "--exec",
            "/opt/cadquery/bin/python",
            "/srv/repo/fdm_analysis/conversion/cadquery_step_to_stl.py",
            "--input",
            "{input}",
            "--output",
            "{output}",
        ],
        "timeoutSeconds": 300,
        "linearToleranceMm": 0.05,
        "angularToleranceDegrees": 5.0,
        "overhangFromVerticalDegrees": 45.0,
        **extra,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class PlanTest(unittest.TestCase):
    """The plan is pure: it must name the exact argv without running anything."""

    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="interference-plan-"))
        self.step = self.temp / "part.step"
        self.step.write_text("ISO-10303-21;\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp, ignore_errors=True)

    def test_derived_template_swaps_only_the_converter_script(self) -> None:
        plan = interference.plan_interference_check(
            step_path=str(self.step), config_path=_config(self.temp / "conf.json")
        )
        self.assertTrue(plan["available"], plan["failures"])
        self.assertEqual(plan["backend"]["templateSource"], "derived")
        self.assertEqual(
            plan["backend"]["converter"],
            "/srv/repo/fdm_analysis/conversion/cadquery_interference.py",
        )
        command = plan["command"]
        # Every element that PRECEDED the configured script is preserved (that is
        # the interpreter selection); the STEP converter's own arguments are not.
        self.assertEqual(
            command[:5],
            ["/usr/bin/wsl.exe", "-d", "Ubuntu-24.04", "--exec", "/opt/cadquery/bin/python"],
        )
        self.assertIn("/srv/repo/fdm_analysis/conversion/cadquery_interference.py", command)
        self.assertNotIn("cadquery_step_to_stl.py", command)
        self.assertNotIn("--angular-tolerance-degrees", command)

    def test_explicit_block_wins_over_derivation(self) -> None:
        path = _config(
            self.temp / "conf.json",
            interference={"argumentTemplate": ["/bin/other", "{input}", "{output}", "{mode}"]},
        )
        plan = interference.plan_interference_check(step_path=str(self.step), config_path=path)
        self.assertEqual(plan["backend"]["templateSource"], "config")
        self.assertEqual(plan["command"][0], "/usr/bin/wsl.exe")
        self.assertEqual(plan["command"][1], "/bin/other")
        self.assertIn("boolean", plan["command"])

    def test_unsupported_placeholder_is_refused_not_ignored(self) -> None:
        path = _config(self.temp / "conf.json", interference={"argumentTemplate": ["{nope}", "{input}", "{output}"]})
        with self.assertRaises(ValueError):
            interference.plan_interference_check(step_path=str(self.step), config_path=path)

    def test_disabled_backend_is_unavailable_with_a_next_action(self) -> None:
        plan = interference.plan_interference_check(
            step_path=str(self.step), config_path=_config(self.temp / "conf.json", enabled=False)
        )
        self.assertFalse(plan["available"])
        self.assertEqual(plan["verdict"], "unavailable")
        self.assertIsNotNone(plan["nextAction"])

    def test_template_without_a_script_is_unavailable(self) -> None:
        plan = interference.plan_interference_check(
            step_path=str(self.step),
            config_path=_config(self.temp / "conf.json", template=["--input", "{input}", "--output", "{output}"]),
        )
        self.assertFalse(plan["available"])
        self.assertIn("names no .py converter script", plan["failures"][0])

    def test_missing_step_and_bad_arguments_are_distinguished(self) -> None:
        plan = interference.plan_interference_check(
            step_path=str(self.temp / "absent.step"), config_path=_config(self.temp / "conf.json")
        )
        self.assertTrue(plan["failures"], plan)
        self.assertIn("does not exist", plan["failures"][0])
        for kwargs, message in (
            ({"step_path": "relative.step"}, "absolute"),
            ({"step_path": str(self.step), "mode": "fuzzy"}, "mode must be"),
            ({"step_path": str(self.step), "tolerance_mm": 0}, "positive"),
            ({"step_path": str(self.step), "max_pairs": 0}, "max_pairs"),
            ({"step_path": str(self.step), "max_pairs": interference.MAX_PAIRS_CAP + 1}, "max_pairs"),
            ({"step_path": str(self.step), "part_names": ["ok", ""]}, "non-empty"),
            ({"step_path": str(self.step), "part_names": "solid_01"}, "list of strings"),
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError) as caught:
                    interference.plan_interference_check(
                        config_path=_config(self.temp / "conf.json"), **kwargs
                    )
                self.assertIn(message, str(caught.exception))

    def test_part_filter_reaches_the_converter_in_template_form(self) -> None:
        plan = interference.plan_interference_check(
            step_path=str(self.step),
            config_path=_config(self.temp / "conf.json"),
            part_names=["solid_02", "solid_07"],
            max_pairs=12,
        )
        self.assertEqual(plan["command"][plan["command"].index("--parts") + 1], "solid_02,solid_07")
        self.assertEqual(plan["command"][plan["command"].index("--max-pairs") + 1], "12")


class _FakeRunner:
    """Records the argv it was handed and writes the report the plan expects."""

    def __init__(self, payload: object | None = None, *, returncode: int = 0, write_report: bool = True, stderr: str = ""):
        self.payload = payload
        self.returncode = returncode
        self.write_report = write_report
        self.stderr = stderr
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(command))
        if self.write_report:
            output = Path(command[command.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            body = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
            output.write_text(body, encoding="utf-8")
        return subprocess.CompletedProcess(command, self.returncode, "", self.stderr)


def _report(*, interfering: int, truncated: bool = False) -> dict[str, object]:
    return {
        "schema": "onshapescript.interference/1",
        "mode": "boolean",
        "tolerance_mm": 0.05,
        "parts": [{"index": 1, "name": "solid_01"}, {"index": 2, "name": "solid_02"}],
        "pairs": [{"a": "solid_01", "b": "solid_02"} for _ in range(interfering)],
        "counts": {
            "parts": 2,
            "candidate_pairs": 1,
            "checked_pairs": 1,
            "interfering": interfering,
            "touching": 0 if interfering else 1,
            "pairs_truncated": truncated,
        },
        "failures": [],
    }


class VerdictTest(unittest.TestCase):
    """`clean` is the one verdict that must be hard to reach."""

    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="interference-verdict-"))
        self.step = self.temp / "part.step"
        self.step.write_text("ISO-10303-21;\n", encoding="utf-8")
        self.config = _config(self.temp / "conf.json")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp, ignore_errors=True)

    def _run(self, runner: _FakeRunner, **kwargs: object) -> dict[str, object]:
        return interference.run_interference_check(
            step_path=str(self.step), config_path=self.config, runner=runner, **kwargs
        )

    def test_zero_interfering_in_boolean_mode_is_clean(self) -> None:
        result = self._run(_FakeRunner(_report(interfering=0)))
        self.assertEqual(result["verdict"], "clean")
        self.assertEqual(result["failures"], [])
        self.assertEqual(result["checkedPairs"], 1)
        self.assertTrue(Path(result["reportPath"]).is_file())

    def test_a_positive_finding_wins(self) -> None:
        result = self._run(_FakeRunner(_report(interfering=3)))
        self.assertEqual(result["verdict"], "interference")

    def test_truncation_without_a_finding_cannot_be_clean(self) -> None:
        result = self._run(_FakeRunner(_report(interfering=0, truncated=True)))
        self.assertEqual(result["verdict"], "indeterminate")
        self.assertEqual(result["failureClass"], "pairs_truncated")
        self.assertTrue(result["failures"])

    def test_truncation_with_a_finding_stays_sound(self) -> None:
        result = self._run(_FakeRunner(_report(interfering=2, truncated=True)))
        self.assertEqual(result["verdict"], "interference")

    def test_aabb_mode_never_claims_clean(self) -> None:
        result = self._run(_FakeRunner(_report(interfering=0)), mode="aabb")
        self.assertEqual(result["verdict"], "candidates_only")
        self.assertNotEqual(result["verdict"], "clean")

    def test_unavailable_never_runs(self) -> None:
        runner = _FakeRunner(_report(interfering=0))
        result = interference.run_interference_check(
            step_path=str(self.step),
            config_path=_config(self.temp / "off.json", enabled=False),
            runner=runner,
        )
        self.assertEqual(result["verdict"], "unavailable")
        self.assertEqual(runner.commands, [])

    def test_converter_failure_is_indeterminate(self) -> None:
        result = self._run(_FakeRunner(None, returncode=2, write_report=False, stderr="Traceback: boom"))
        self.assertEqual(result["verdict"], "indeterminate")
        self.assertEqual(result["failureClass"], "converter_failed")
        self.assertEqual(result["exitCode"], 2)
        self.assertIn("boom", result["failures"][0])

    def test_zero_exit_without_a_report_is_indeterminate(self) -> None:
        result = self._run(_FakeRunner(None, returncode=0, write_report=False))
        self.assertEqual(result["verdict"], "indeterminate")
        self.assertEqual(result["failureClass"], "report_missing")

    def test_unreadable_report_is_indeterminate(self) -> None:
        result = self._run(_FakeRunner("{not json"))
        self.assertEqual(result["verdict"], "indeterminate")
        self.assertEqual(result["failureClass"], "report_unreadable")

    def test_report_without_the_expected_counts_is_indeterminate(self) -> None:
        result = self._run(_FakeRunner({"schema": "onshapescript.interference/1"}))
        self.assertEqual(result["verdict"], "indeterminate")
        self.assertEqual(result["failureClass"], "report_unreadable")

    def test_timeout_is_indeterminate(self) -> None:
        def runner(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise subprocess.TimeoutExpired(command, kwargs.get("timeout", 1))

        result = self._run(runner)  # type: ignore[arg-type]
        self.assertEqual(result["verdict"], "indeterminate")
        self.assertEqual(result["failureClass"], "converter_timeout")

    def test_the_report_path_is_content_addressed_and_reused(self) -> None:
        first = self._run(_FakeRunner(_report(interfering=1)))
        second = self._run(_FakeRunner(_report(interfering=3)))
        self.assertEqual(first["reportPath"], second["reportPath"])
        self.assertNotEqual(first["reportSha256"], second["reportSha256"])


class ConverterTest(unittest.TestCase):
    """The converter must be inspectable without CadQuery present."""

    def test_module_imports_without_cadquery(self) -> None:
        source = CONVERTER.read_text(encoding="utf-8")
        tree = ast.parse(source)
        top_level_imports = {
            alias.name.split(".")[0]
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            (node.module or "").split(".")[0]
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
        }
        self.assertNotIn("cadquery", top_level_imports)
        self.assertNotIn("OCP", top_level_imports)

    def test_arguments_help_runs_without_cadquery(self) -> None:
        process = subprocess.run(
            [sys.executable, str(CONVERTER), "--help"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        for option in ("--input", "--output", "--mode", "--linear-tolerance-mm", "--parts", "--max-pairs"):
            self.assertIn(option, process.stdout)


def _cadquery_python() -> str | None:
    for candidate in (
        "/home/lijq/code/CadQ/.venv/bin/python",
        shutil.which("python3"),
        sys.executable,
    ):
        if not candidate or not Path(candidate).exists():
            continue
        probe = subprocess.run(
            [candidate, "-c", "import cadquery"],
            capture_output=True,
            timeout=180,
        )
        if probe.returncode == 0:
            return candidate
    return None


CADQUERY_PYTHON = _cadquery_python()


@unittest.skipUnless(CADQUERY_PYTHON, "no interpreter on this machine can import CadQuery")
class LiveCadQuery(unittest.TestCase):
    """Real geometry: the measured intersection is checked against arithmetic.

    A bounding-box overlap alone cannot decide these two fixtures -- the interlock
    has a 3 x 3 x 10 mm box overlap and an intersection volume of zero -- which is
    exactly why the boolean volume is the primitive that this capability rests on.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = Path(tempfile.mkdtemp(prefix="interference-live-"))
        builder = cls.temp / "build.py"
        builder.write_text(
            "import cadquery as cq, pathlib\n"
            "out = pathlib.Path(%r)\n"
            "a = cq.Workplane('XY').box(10, 10, 10)\n"
            "b = cq.Workplane('XY').box(10, 10, 10).translate((8, 7, 6))\n"
            "cq.exporters.export(cq.Compound.makeCompound([a.val(), b.val()]), str(out / 'overlap.step'))\n"
            "l = cq.Workplane('XY').box(10, 4, 10).union(cq.Workplane('XY').box(4, 10, 10))\n"
            "n = cq.Workplane('XY').box(6, 6, 10).translate((5, 5, 0))\n"
            "cq.exporters.export(cq.Compound.makeCompound([l.val(), n.val()]), str(out / 'interlock.step'))\n"
            % str(cls.temp),
            encoding="utf-8",
        )
        process = subprocess.run(
            [CADQUERY_PYTHON, str(builder)], capture_output=True, text=True, timeout=600
        )
        if process.returncode != 0:
            shutil.rmtree(cls.temp, ignore_errors=True)
            raise unittest.SkipTest(f"the fixture build failed: {process.stderr[-400:]}")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.temp, ignore_errors=True)

    def _config(self) -> Path:
        # The interpreter is the CadQuery python itself and the template names the
        # real STEP converter, so the derivation is exercised against the same
        # shape the deployed Windows configuration has (there the launcher is
        # wsl.exe and the template holds `--exec <python> <script> ...`).
        return _config(
            self.temp / "conf.json",
            executable=CADQUERY_PYTHON,
            template=[
                str(ROOT / "fdm_analysis" / "conversion" / "cadquery_step_to_stl.py"),
                "--input",
                "{input}",
                "--output",
                "{output}",
                "--linear-tolerance-mm",
                "{linear_tolerance_mm}",
                "--angular-tolerance-degrees",
                "{angular_tolerance_degrees}",
            ],
        )

    def test_overlapping_solids_measure_their_intersection(self) -> None:
        result = interference.run_interference_check(
            step_path=str(self.temp / "overlap.step"), config_path=self._config()
        )
        self.assertEqual(result["verdict"], "interference", result["failures"])
        self.assertEqual(len(result["pairs"]), 1)
        pair = result["pairs"][0]
        self.assertAlmostEqual(pair["intersection_volume_mm3"], 24.0, places=6)
        self.assertFalse(pair["zero_volume_contact"])
        self.assertEqual([round(value, 6) for value in pair["overlap_mm"]], [2.0, 3.0, 4.0])

    def test_an_interlock_has_a_box_overlap_and_no_volume(self) -> None:
        result = interference.run_interference_check(
            step_path=str(self.temp / "interlock.step"), config_path=self._config()
        )
        self.assertEqual(result["verdict"], "clean", result["failures"])
        pair = result["pairs"][0]
        self.assertEqual([round(value, 6) for value in pair["overlap_mm"]], [3.0, 3.0, 10.0])
        self.assertEqual(pair["intersection_volume_mm3"], 0.0)
        self.assertTrue(pair["zero_volume_contact"])

    def test_aabb_mode_reports_the_same_candidate_without_deciding(self) -> None:
        result = interference.run_interference_check(
            step_path=str(self.temp / "interlock.step"), config_path=self._config(), mode="aabb"
        )
        self.assertEqual(result["verdict"], "candidates_only")
        self.assertEqual(result["counts"]["candidate_pairs"], 1)
        self.assertIsNone(result["pairs"][0]["intersection_volume_mm3"])

    def test_the_part_filter_restricts_the_pairs(self) -> None:
        result = interference.run_interference_check(
            step_path=str(self.temp / "overlap.step"),
            config_path=self._config(),
            part_names=["solid_01", "solid_02"],
        )
        self.assertEqual(result["counts"]["selected_parts"], 2)
        self.assertEqual(result["verdict"], "interference")


if __name__ == "__main__":
    unittest.main()
