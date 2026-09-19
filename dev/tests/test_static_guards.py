#!/usr/bin/env python3
"""Offline tests for the zero-cost static/guard checks.

Covers the local FeatureScript checker (onshape_docs/query/fs_check.py)
— specifically that a dangling `Feature Type Name` annotation is detected even
though string masking hides its marker, that an unreplaced {{PLACEHOLDER}} is a
structural error, that a definition-map call with a non-map third argument and
dimensioned arithmetic mixed with a plain number are warned about, and that the
checker meets its acceptance on the live-labeled sample corpus — plus the
rate-limit re-raise ordering in live_gap_probe and the singleton-attribution
safety in live_is_probe. No Onshape API call is ever made: live scripts are
driven through mocks only, and the corpus check is fully offline.
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "onshape_docs" / "scripts"
for path in (str(ROOT), str(SCRIPTS_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from onshape_docs.query import fs_check  # noqa: E402
import live_gap_probe  # noqa: E402
import live_is_probe  # noqa: E402

_HEADER = (
    'FeatureScript 3044;\n'
    'import(path : "onshape/std/geometry.fs", version : "3044.0");\n\n'
)

_VALID_FEATURE = _HEADER + (
    'annotation { "Feature Type Name" : "MyFeature" }\n'
    "export const myFeature = defineFeature(function(context is Context, id is Id, definition is map)\n"
    "    precondition\n"
    "    {\n"
    '        annotation { "Name" : "Size" }\n'
    "        isLength(definition.size, { (millimeter) : [1, 2, 3] } as LengthBoundSpec);\n"
    "    }\n"
    "    {\n"
    "        opExtrude(context, id + \"e\", { \"entities\" : qCreatedBy(id, EntityType.BODY), \"direction\" : Z_DIRECTION, \"endBound\" : BoundingType.BLIND, \"endDepth\" : definition.size });\n"
    "    });\n"
)


#: A structurally broken script: a dangling Feature Type Name annotation with no
#: defineFeature after it. Used by tests that only need "the checker fails".
_BROKEN = _HEADER + 'annotation { "Feature Type Name" : "Orphan" }\n'


def check_text(text: str) -> fs_check.FsFile:
    """Check in-memory source through the in-process API, not the CLI."""
    return fs_check.check_source(fs_check.FsFile.from_text(text, "check.fs"))


class CheckerApiTest(unittest.TestCase):
    """The checker is importable from the runtime, so its API is part of the surface."""

    def test_in_memory_source_matches_the_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "same.fs"
            path.write_text(_VALID_FEATURE, encoding="utf-8")
            from_file = fs_check.check_file(path)
        from_text = check_text(_VALID_FEATURE)
        self.assertEqual(from_text.errors, from_file.errors)
        self.assertEqual(from_text.warnings, from_file.warnings)

    def test_as_result_is_json_friendly_and_advisory(self) -> None:
        clear = check_text(_VALID_FEATURE).as_result()
        self.assertTrue(clear["clear"])
        self.assertEqual(clear["errorCount"], 0)
        self.assertEqual(clear["errors"], [])
        broken = check_text(_BROKEN).as_result()
        self.assertFalse(broken["clear"])
        self.assertEqual(broken["errorCount"], len(broken["errors"]))
        self.assertGreaterEqual(broken["errorCount"], 1)

    def test_from_text_rejects_a_non_string(self) -> None:
        with self.assertRaises(TypeError):
            fs_check.FsFile.from_text(None)  # type: ignore[arg-type]

    def test_check_source_does_not_reread_the_source_it_is_given(self) -> None:
        fs = fs_check.FsFile.from_text(_VALID_FEATURE, "memory.fs")
        fs.text = _VALID_FEATURE + "\n// mutated after load\n"
        fs_check.check_source(fs)
        self.assertEqual(fs.as_result()["name"], "memory.fs")


class CheckerCliTest(unittest.TestCase):
    """The documented CLI keeps working after the analysis moved to the query layer."""

    def test_cli_passes_a_valid_file_and_fails_a_broken_one(self) -> None:
        cli = ROOT / "onshape_docs" / "scripts" / "fs_local_check.py"
        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.fs"
            good.write_text(_VALID_FEATURE, encoding="utf-8")
            bad = Path(tmp) / "bad.fs"
            bad.write_text(_BROKEN, encoding="utf-8")
            passed = subprocess.run([sys.executable, str(cli), str(good)],
                                    capture_output=True, text=True, cwd=str(ROOT))
            failed = subprocess.run([sys.executable, str(cli), str(bad)],
                                    capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(passed.returncode, 0, passed.stdout + passed.stderr)
        self.assertIn("[PASS]", passed.stdout)
        self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
        self.assertIn("[FAIL]", failed.stdout)

    def test_cli_re_exports_the_analysis_api(self) -> None:
        cli = ROOT / "onshape_docs" / "scripts" / "fs_local_check.py"
        probe = (
            "import sys; sys.path.insert(0, sys.argv[1]);"
            "import fs_local_check as m;"
            "print(m.check_file.__module__, m.FsFile.__module__, m.check_source.__module__)"
        )
        result = subprocess.run([sys.executable, "-c", probe, str(cli.parent)],
                                capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(),
                         ["onshape_docs.query.fs_check"] * 3)


class SymbolScanMaskingTest(unittest.TestCase):
    """Symbol scanning must read the code, not the prose or the comments.

    Regression: `check_symbols` scanned the raw text, so an annotation string
    containing a lowercase word followed by `(` -- `"Planar face (drill
    direction)"` -- reported a call to `face(`, and a commented-out example
    reported its own types. A checker that flags words inside strings cannot be
    trusted with a warning budget.
    """

    def _warnings(self, text: str) -> list[str]:
        return check_text(text).warnings

    def test_a_parenthesised_annotation_string_is_not_a_call(self) -> None:
        text = _HEADER + (
            'annotation { "Feature Type Name" : "MyFeature" }\n'
            "export const myFeature = defineFeature(function(context is Context, id is Id, definition is map)\n"
            "    precondition\n"
            "    {\n"
            '        annotation { "Name" : "Planar face (drill direction)" }\n'
            "        definition.face is Query;\n"
            "    }\n"
            "    {\n"
            '        opExtrude(context, id + "e", { "entities" : definition.face, "direction" : Z_DIRECTION, "endBound" : BoundingType.BLIND, "endDepth" : 1 * millimeter });\n'
            "    });\n"
        )
        self.assertEqual(self._warnings(text), [])

    def test_a_commented_out_call_or_type_is_not_scanned(self) -> None:
        text = _HEADER + (
            'annotation { "Feature Type Name" : "MyFeature" }\n'
            "export const myFeature = defineFeature(function(context is Context, id is Id, definition is map)\n"
            "    precondition\n"
            "    {\n"
            '        annotation { "Name" : "Size" }\n'
            "        definition.size is number;\n"
            "    }\n"
            "    {\n"
            "        // opFrobnicate(context, id, {}); and `definition.x is NotAType`\n"
            "        /* MyEnum.BOGUS_MEMBER */\n"
            "        println(1);\n"
            "    });\n"
        )
        self.assertEqual(self._warnings(text), [])

    def test_a_real_unknown_call_is_still_warned(self) -> None:
        """The mask must not swallow the finding it exists to qualify."""
        text = _HEADER + (
            'annotation { "Feature Type Name" : "MyFeature" }\n'
            "export const myFeature = defineFeature(function(context is Context, id is Id, definition is map)\n"
            "    {\n"
            "        qFrobnicate(id);\n"
            "    });\n"
        )
        self.assertTrue(
            any("qFrobnicate" in warning for warning in self._warnings(text)),
            "a genuine unknown symbol must still be reported",
        )

    def test_a_real_unknown_enum_member_is_still_warned(self) -> None:
        text = _HEADER + (
            'annotation { "Feature Type Name" : "MyFeature" }\n'
            "export const myFeature = defineFeature(function(context is Context, id is Id, definition is map)\n"
            "    {\n"
            "        const bound = BoundingType.NOT_A_BOUNDING_TYPE;\n"
            "    });\n"
        )
        self.assertTrue(
            any("NOT_A_BOUNDING_TYPE" in warning for warning in self._warnings(text)),
            "a genuine unknown enum member must still be reported",
        )


_FEATURE_WITH_IMPORT = (
    'annotation { "Feature Type Name" : "MyFeature" }\n'
    "export const myFeature = defineFeature(function(context is Context, id is Id, definition is map)\n"
    "    precondition\n"
    "    {\n"
    '        annotation { "Name" : "Size" }\n'
    "        isLength(definition.size, LENGTH_BOUNDS);\n"
    "    }\n"
    "    {\n"
    "        opExtrude(context, id + \"e\", { \"entities\" : qAllModifiableSolidBodies(), \"direction\" : Z_DIRECTION, \"endBound\" : BoundingType.BLIND, \"endDepth\" : definition.size });\n"
    "    });\n"
)


class ImportCheckTest(unittest.TestCase):
    """`onshape/std/...` imports are checked against what is vendored on disk.

    Measured: zero false positives over the 1717 import statements in the
    vendored library and the repository's own FeatureScript. The check compares
    against the *files* (271), not the documented module index (210): using the
    index produced 99 false positives for modules that exist but are undocumented.
    """

    def _import_warnings(self, header: str) -> list[str]:
        text = header + _FEATURE_WITH_IMPORT
        return [w for w in check_text(text).warnings if "import" in w]

    def test_a_misspelled_std_module_warns(self) -> None:
        warnings = self._import_warnings('FeatureScript 3044;\nimport(path : "onshape/std/geomtry.fs", version : "3044.0");\n')
        self.assertEqual(len(warnings), 1)
        self.assertIn("geomtry.fs", warnings[0])

    def test_a_correct_std_module_is_silent(self) -> None:
        for module in ("geometry.fs", "holeUtils.fs", "containers.fs"):
            with self.subTest(module=module):
                self.assertEqual(
                    self._import_warnings(f'FeatureScript 3044;\nimport(path : "onshape/std/{module}", version : "3044.0");\n'),
                    [],
                )

    def test_a_vendored_but_undocumented_module_is_silent(self) -> None:
        """`booleanHeuristics.fs` is on disk and absent from the module index.
        Checking the index instead of the disk is the 99-false-positive bug."""
        self.assertEqual(
            self._import_warnings('FeatureScript 3044;\nimport(path : "onshape/std/booleanHeuristics.fs", version : "3044.0");\n'),
            [],
        )

    def test_a_document_import_is_never_checked(self) -> None:
        """An import of another Feature Studio is outside the mirror by design."""
        self.assertEqual(
            self._import_warnings('FeatureScript 3044;\nimport(path : "a1b2c3d4e5f6", version : "1.0");\n'),
            [],
        )

    def test_a_versionless_import_is_still_checked_for_the_path(self) -> None:
        warnings = self._import_warnings('FeatureScript 3044;\nimport(path : "onshape/std/geomtry.fs");\n')
        self.assertEqual(len(warnings), 1)
        self.assertIn("geomtry.fs", warnings[0])

    def test_an_empty_version_string_warns(self) -> None:
        warnings = self._import_warnings('FeatureScript 3044;\nimport(path : "onshape/std/geometry.fs", version : "");\n')
        self.assertTrue(any("empty version" in warning for warning in warnings))

    def test_a_commented_out_import_is_not_scanned(self) -> None:
        self.assertEqual(
            self._import_warnings('FeatureScript 3044;\n// import(path : "onshape/std/geomtry.fs", version : "3044.0");\n'),
            [],
        )

    def test_the_library_itself_is_clean(self) -> None:
        """The rule's own false-positive gate, on the real mirror."""
        library = ROOT / "onshape_docs" / "reference" / "raw" / "std-library"
        checked = 0
        for path in sorted(library.glob("*.fs")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if not fs_check._IMPORT_PATH.search(text):
                continue
            checked += 1
            result = fs_check.check_source(fs_check.FsFile.from_text(text, name=str(path))).as_result()
            with self.subTest(module=path.name):
                self.assertEqual(
                    [w for w in result["warnings"] if "vendored standard library" in w or "empty version" in w],
                    [],
                )
        self.assertGreater(checked, 100, "the library sample looks truncated")


class DanglingAnnotationTest(unittest.TestCase):
    def test_correct_annotation_is_not_flagged(self) -> None:
        fs = check_text(_VALID_FEATURE)
        self.assertEqual(fs.errors, [])

    def test_dangling_annotation_is_a_structural_error(self) -> None:
        # No `export const ... = defineFeature(...)` after the annotation, so it
        # dangles. This was previously invisible: string masking blanked the
        # "Feature Type Name" marker before the annotation scan ran.
        fs = check_text(_HEADER + 'annotation { "Feature Type Name" : "Orphan" }\n')
        self.assertTrue(any("dangling" in e for e in fs.errors), fs.errors)

    def test_commented_out_annotation_is_not_flagged(self) -> None:
        # Comments are masked, so an annotation that lives only in a comment must
        # not count as a dangling annotation.
        fs = check_text(_HEADER + '// annotation { "Feature Type Name" : "Commented out" }\n')
        self.assertFalse(any("dangling" in e for e in fs.errors), fs.errors)

    def test_annotation_in_string_literal_is_not_flagged(self) -> None:
        # A string containing the marker text is not an annotation.
        fs = check_text(
            _HEADER
            + 'const s = "annotation { \\"Feature Type Name\\" : not-an-annotation }";\n'
        )
        self.assertFalse(any("dangling" in e for e in fs.errors), fs.errors)


class PlaceholderTest(unittest.TestCase):
    def test_unreplaced_placeholder_is_a_structural_error(self) -> None:
        # The header regex tolerates {{MAJOR}} as a version, but the placeholder
        # check must still hard-stop: a template is not uploadable as-is.
        fs = check_text(
            'FeatureScript {{MAJOR}};\n'
            'import(path : "onshape/std/geometry.fs", version : "{{VERSION}}");\n'
        )
        self.assertTrue(any("PLACEHOLDER" in e for e in fs.errors), fs.errors)

    def test_no_placeholder_no_error(self) -> None:
        fs = check_text(_VALID_FEATURE)
        self.assertFalse(any("PLACEHOLDER" in e for e in fs.errors), fs.errors)


def _fake_gap_guard(client):
    guard = mock.Mock()
    guard.client = client
    guard.budget = 22
    guard.spent = 0
    guard.exceeded.return_value = False
    guard.summary.return_value = {
        "budget": 22, "spent": 0, "remaining": 22, "annualRemaining": 100,
    }
    return guard


@contextlib.contextmanager
def _gap_env(guard, render):
    patches = [
        mock.patch.object(sys, "argv", ["live_gap_probe.py"]),
        mock.patch.object(live_gap_probe, "live_api_enabled", return_value=True),
        mock.patch.object(live_gap_probe, "rate_limit_reason", return_value=None),
        mock.patch.object(live_gap_probe, "BudgetGuard", return_value=guard),
        mock.patch.object(live_gap_probe, "eval_featurescript",
                          return_value={"errors": [], "result": [],
                                        "featureScriptVersion": "3044.0"}),
        render,
        mock.patch.object(live_gap_probe, "OUT",
                          Path(tempfile.mkdtemp()) / "gap-probe-results.json"),
    ]
    with contextlib.ExitStack() as stack:
        for patch in patches:
            stack.enter_context(patch)
        yield


class MaintainedFixtureTest(unittest.TestCase):
    def test_module_rail_fixture_has_no_structural_errors(self) -> None:
        fixture = ROOT / "dev" / "fixtures-capture" / "module-rail-fixed-wall.fs"
        checked = fs_check.check_file(fixture)
        self.assertEqual(checked.errors, [], checked.errors)


class LiveGapProbeRateLimitTest(unittest.TestCase):
    """429 must propagate out of main(), never be swallowed as a generic error."""

    def test_render_branch_reraise_rate_limited(self) -> None:
        client = mock.Mock()
        client.state = {"documentId": "did", "workspaceId": "wid"}
        guard = _fake_gap_guard(client)
        render = mock.patch.object(
            live_gap_probe, "render_preview",
            side_effect=live_gap_probe.RateLimited("429: retry after 72910s"),
        )
        with _gap_env(guard, render):
            with self.assertRaises(live_gap_probe.RateLimited):
                live_gap_probe.main()

    def test_rest_read_branch_reraise_rate_limited(self) -> None:
        client = mock.Mock()
        client.state = {"documentId": "did", "workspaceId": "wid"}
        client.request.side_effect = live_gap_probe.RateLimited("429: retry after 72910s")
        guard = _fake_gap_guard(client)
        render = mock.patch.object(live_gap_probe, "render_preview", return_value={
            "view": "iso", "width": 300, "height": 300,
            "mediaType": "image/png", "byteCount": 0, "sha256": "abc",
        })
        with _gap_env(guard, render):
            with self.assertRaises(live_gap_probe.RateLimited):
                live_gap_probe.main()


class LiveIsProbeSingletonTest(unittest.TestCase):
    def test_singleton_unattributable_error_is_recorded_not_recursive(self) -> None:
        guard = mock.Mock()
        guard.client = mock.Mock()
        guard.exceeded.return_value = False
        guard.summary.return_value = {"budget": 40, "spent": 1, "remaining": 39,
                                      "annualRemaining": 100}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "live-is-probe.json"
            probe = live_is_probe.Probe(guard, "psid", out)
            probe.pending = [("isFake", "isFake(1)")]
            with mock.patch.object(
                live_is_probe, "eval_featurescript",
                return_value={"errors": ["Attempt to dereference non-container 5"]},
            ):
                # Would recurse forever on the singleton before the fix; must
                # instead record the failure and drain the pending list.
                probe.probe(probe.pending)
        self.assertEqual(probe.pending, [])
        self.assertIn("isFake", probe.results)
        self.assertEqual(probe.results["isFake"]["verdict"], "FAILED")


def _feature_with_body(body: str) -> str:
    """A minimal valid custom feature whose body is `body`."""
    return _HEADER + (
        'annotation { "Feature Type Name" : "T" }\n'
        "export const t = defineFeature(function(context is Context, id is Id, definition is map)\n"
        "    precondition\n"
        "    {\n"
        '        annotation { "Name" : "Size" }\n'
        "        isLength(definition.size, { (millimeter) : [1, 2, 3] } as LengthBoundSpec);\n"
        "    }\n"
        "    {\n"
        f"        {body}\n"
        "    });\n"
    )


class DefinitionMapArgumentTest(unittest.TestCase):
    """A definition-map call's third argument must be a map literal.

    The server accepts a scalar here at save time and only reports
    `featureStatus=ERROR` at instantiation, so this class of defect is invisible
    without a local rule.
    """

    def test_scalar_third_argument_is_warned(self) -> None:
        checked = check_text(_feature_with_body('opExtrude(context, id + "e", 5);'))
        self.assertTrue(
            any("not a map literal" in warning for warning in checked.warnings),
            checked.warnings,
        )
        self.assertFalse(checked.errors)

    def test_string_third_argument_is_warned(self) -> None:
        checked = check_text(_feature_with_body('opExtrude(context, id + "e", "nope");'))
        self.assertTrue(
            any("not a map literal" in warning for warning in checked.warnings),
            checked.warnings,
        )

    def test_map_literal_third_argument_is_not_warned(self) -> None:
        checked = check_text(_feature_with_body(
            'opExtrude(context, id + "e", { "entities" : qCreatedBy(id, EntityType.BODY) });'
        ))
        self.assertFalse(
            [warning for warning in checked.warnings if "not a map literal" in warning]
        )

    def test_variable_third_argument_is_never_second_guessed(self) -> None:
        checked = check_text(_feature_with_body(
            'const definition = { "entities" : qCreatedBy(id, EntityType.BODY) };\n'
            '        opExtrude(context, id + "e", definition);'
        ))
        self.assertFalse(
            [warning for warning in checked.warnings if "not a map literal" in warning]
        )

    def test_nested_map_value_does_not_confuse_argument_split(self) -> None:
        checked = check_text(_feature_with_body(
            'opExtrude(context, id + "e", { "entities" : qCreatedBy(id, EntityType.BODY), '
            '"direction" : vector(1, 0, 0) });'
        ))
        self.assertFalse(
            [warning for warning in checked.warnings if "not a map literal" in warning]
        )


class UnitMixingTest(unittest.TestCase):
    """Dimensioned arithmetic joined to a plain number is flagged."""

    def test_dimensioned_plus_plain_number_is_warned(self) -> None:
        checked = check_text(_feature_with_body("var len = 5 * millimeter + 2;"))
        self.assertTrue(
            any("mixed dimensions" in warning for warning in checked.warnings),
            checked.warnings,
        )

    def test_plain_number_plus_dimensioned_is_warned(self) -> None:
        checked = check_text(_feature_with_body("var len = 2 + 5 * millimeter;"))
        self.assertTrue(
            any("mixed dimensions" in warning for warning in checked.warnings),
            checked.warnings,
        )

    def test_genuine_unit_arithmetic_is_not_warned(self) -> None:
        checked = check_text(_feature_with_body("var len = 5 * millimeter + 2 * centimeter;"))
        self.assertFalse(
            [warning for warning in checked.warnings if "mixed dimensions" in warning]
        )

    def test_plain_arithmetic_is_not_warned(self) -> None:
        checked = check_text(_feature_with_body("var count = 5 + 2;"))
        self.assertFalse(
            [warning for warning in checked.warnings if "mixed dimensions" in warning]
        )


class LiveLabeledCorpusTest(unittest.TestCase):
    """The checker's acceptance against the live-labeled sample corpus.

    `dev/tools/fs_corpus_check.py` renders the recorded experiment templates and
    compares the local verdict with the recorded live outcome. It exits 0 only
    when every sample that the live server accepted and later failed at
    instantiation is flagged locally, and no valid sample is flagged.
    """

    def test_labeled_corpus_meets_acceptance(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "dev" / "tools" / "fs_corpus_check.py")],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("result: PASS", result.stdout)
        self.assertIn("valid samples clean    : 6/6", result.stdout)


if __name__ == "__main__":
    unittest.main()
