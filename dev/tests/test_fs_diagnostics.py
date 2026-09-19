#!/usr/bin/env python3
"""Offline tests for FeatureScript diagnostic normalization and retention.

Everything here is offline and deterministic: the vendored ErrorStringEnum
module is either the real one shipped in this repository or a temporary
stand-in, never a live Onshape surface. The tests cover the four gaps the
FeatureScript diagnostic loop had -- a stable code per diagnostic, every
paragraph of a multi-message notice, the offending source line, and a
deduplicated frequency summary with a retained labeled corpus entry.

The node-based stub-DOM test for the notice collector itself lives in
dev/tests/test_fs_notice_collector.py.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_browser_mode import diagnostics  # noqa: E402

# Text observed verbatim in dev/button-map/scan-fs-notices.json (real notice
# pane, English UI). These pin the compiler-message families to evidence.
OBSERVED_NOTICES = (
    "Nonconforming feature function 'helicalBeamCoupling': precondition analysis failed",
    "Variable POSITIVE_LENGTH_BOUNDS not found.",
    "definition.outerDiameter: Expected bounds to be a map",
    "definition.outerDiameter: Expected a range",
)

_TEMP_ENUM = """FeatureScript 3044;
export enum ErrorStringEnum
{
    NO_ERROR,
    /* Cannot resolve entities. */
    CANNOT_RESOLVE_ENTITIES,
    /* Invalid input selections. */
    INVALID_INPUT,
    /* Error regenerating. */
    REGEN_ERROR,
    /* Error regenerating. */
    AMBIGUOUS_TWIN,
    NO_DESCRIPTION_HERE
}
"""


def _write_enum(tmp: str, content: str = _TEMP_ENUM) -> Path:
    root = Path(tmp) / "onshape_docs" / "reference" / "raw" / "std-library"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "errorstringenum.gen.fs"
    path.write_text(content, encoding="utf-8")
    return path


class ErrorStringEnumIndexTest(unittest.TestCase):
    def test_vendored_enum_is_present_and_parsed(self) -> None:
        index = diagnostics.error_string_enum_index()
        self.assertTrue(index.available, index.reason)
        self.assertTrue(index.path.endswith("errorstringenum.gen.fs"))
        self.assertIn("CANNOT_RESOLVE_ENTITIES", index.codes)
        # The generated FsDoc index drops ErrorStringEnum (upstream marks it
        # @internal), so the raw module is the only local source for these codes.
        self.assertGreater(len(index.codes), 1000)

    def test_ambiguous_descriptions_are_excluded_not_guessed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = diagnostics.error_string_enum_index(_write_enum(tmp))
        self.assertEqual(index.descriptions["cannot resolve entities"], "CANNOT_RESOLVE_ENTITIES")
        # "Error regenerating." is owned by two codes, so it must not resolve.
        self.assertIn("error regenerating", index.ambiguous_descriptions)
        self.assertNotIn("error regenerating", index.descriptions)
        self.assertIn("ambiguousDescriptionCount", diagnostics.code_table_status(index))

    def test_commentless_values_are_counted_and_still_usable_as_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = diagnostics.error_string_enum_index(_write_enum(tmp))
        # NO_ERROR and the comma-less final value carry no docblock.
        self.assertEqual(index.commentless_count, 2)
        # The final enum value has no trailing comma in the generated module; it
        # must still be parsed, or one real error code is unreachable.
        self.assertEqual(
            diagnostics.normalize_diagnostic("NO_DESCRIPTION_HERE", index)["code"],
            "NO_DESCRIPTION_HERE",
        )
        self.assertIn("NO_DESCRIPTION_HERE", index.codes)

    def test_missing_module_degrades_with_a_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "absent.fs"
            index = diagnostics.error_string_enum_index(missing)
        self.assertFalse(index.available)
        self.assertIn("cannot read", index.reason)
        self.assertEqual(index.codes, frozenset())
        status = diagnostics.code_table_status(index)
        self.assertFalse(status["available"])
        self.assertEqual(status["codeCount"], 0)

    def test_non_enum_source_is_reported_not_silently_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = diagnostics.error_string_enum_index(
                _write_enum(tmp, "FeatureScript 3044;\n// no enum here\n")
            )
        self.assertFalse(index.available)
        self.assertIn("no ErrorStringEnum declaration", index.reason)

    def test_environment_override_locates_the_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_enum(tmp)
            previous = os.environ.get(diagnostics.FS_ERROR_ENUM_ENV)
            os.environ[diagnostics.FS_ERROR_ENUM_ENV] = str(path)
            try:
                self.assertEqual(diagnostics.error_string_enum_path(), path)
            finally:
                if previous is None:
                    os.environ.pop(diagnostics.FS_ERROR_ENUM_ENV, None)
                else:
                    os.environ[diagnostics.FS_ERROR_ENUM_ENV] = previous


class NormalizeDiagnosticTest(unittest.TestCase):
    def test_observed_compiler_messages_get_stable_families(self) -> None:
        expected = {
            OBSERVED_NOTICES[0]: "FS_PRECONDITION_ANALYSIS_FAILED",
            OBSERVED_NOTICES[1]: "FS_UNRESOLVED_NAME",
            OBSERVED_NOTICES[2]: "FS_EXPECTED_TYPE",
            OBSERVED_NOTICES[3]: "FS_EXPECTED_TYPE",
        }
        for text, code in expected.items():
            normalized = diagnostics.normalize_diagnostic(text)
            self.assertEqual(normalized["code"], code, text)
            self.assertEqual(normalized["codeBasis"], "compilerMessage", text)
            # Our own families are labeled unstable so nobody mistakes them for
            # a server-defined error code.
            self.assertFalse(normalized["codeStable"], text)

    def test_enum_token_is_reported_as_a_server_defined_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = diagnostics.error_string_enum_index(_write_enum(tmp))
            normalized = diagnostics.normalize_diagnostic("Some context: INVALID_INPUT", index)
        self.assertEqual(normalized["code"], "INVALID_INPUT")
        self.assertEqual(normalized["codeBasis"], "errorstringenum")
        self.assertTrue(normalized["codeStable"])

    def test_enum_description_resolves_only_when_unambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index = diagnostics.error_string_enum_index(_write_enum(tmp))
            resolved = diagnostics.normalize_diagnostic("Cannot resolve entities.", index)
            ambiguous = diagnostics.normalize_diagnostic("Error regenerating.", index)
        self.assertEqual(resolved["code"], "CANNOT_RESOLVE_ENTITIES")
        self.assertEqual(resolved["codeBasis"], "errorstringenumDescription")
        self.assertTrue(resolved["codeStable"])
        self.assertEqual(ambiguous["code"], "UNCLASSIFIED")
        self.assertEqual(ambiguous["codeBasis"], "unclassified")

    def test_unknown_prose_stays_unclassified_rather_than_forced(self) -> None:
        normalized = diagnostics.normalize_diagnostic("The solver gave up in a novel way")
        self.assertEqual(normalized["code"], "UNCLASSIFIED")
        self.assertEqual(normalized["codeBasis"], "unclassified")
        self.assertFalse(normalized["codeStable"])

    def test_user_name_that_is_not_an_enum_code_is_not_misread(self) -> None:
        # A user's own ALL_CAPS constant is not a server code: the token rule
        # only fires on values the vendored enum actually defines.
        normalized = diagnostics.normalize_diagnostic("Variable POSITIVE_LENGTH_BOUNDS not found.")
        self.assertEqual(normalized["code"], "FS_UNRESOLVED_NAME")

    def test_non_string_input_does_not_raise(self) -> None:
        self.assertEqual(diagnostics.normalize_diagnostic(None)["code"], "UNCLASSIFIED")


class DiagnosticSourceContextTest(unittest.TestCase):
    SOURCE = "line one\n\tvar d = 5 * millimeter + 2;\nline three"

    def test_row_and_column_produce_a_self_contained_caret(self) -> None:
        context = diagnostics.diagnostic_source_context(self.SOURCE, 1, 9)
        self.assertTrue(context["available"])
        self.assertEqual(context["lineNumber"], 2)
        self.assertEqual(context["sourceLine"], "\tvar d = 5 * millimeter + 2;")
        # Tabs are preserved in the caret prefix so the caret keeps its column.
        self.assertEqual(context["caret"], "\t" + " " * 8)
        self.assertFalse(context["truncated"])

    def test_column_beyond_the_line_end_is_clamped(self) -> None:
        context = diagnostics.diagnostic_source_context(self.SOURCE, 2, 500)
        self.assertEqual(context["caret"], " " * len("line three"))

    def test_out_of_range_row_is_reported_without_a_line(self) -> None:
        context = diagnostics.diagnostic_source_context(self.SOURCE, 99)
        self.assertFalse(context["available"])
        self.assertIn("outside", context["reason"])
        self.assertEqual(context["lineCount"], 3)
        self.assertNotIn("sourceLine", context)

    def test_missing_source_is_reported_without_raising(self) -> None:
        self.assertFalse(diagnostics.diagnostic_source_context(None, 0)["available"])
        self.assertFalse(diagnostics.diagnostic_source_context("", 0)["available"])

    def test_long_lines_are_truncated_and_flagged(self) -> None:
        line = "x = " + "1" * (diagnostics.MAX_SOURCE_LINE_LENGTH + 50) + ";"
        context = diagnostics.diagnostic_source_context(line, 0)
        self.assertEqual(len(context["sourceLine"]), diagnostics.MAX_SOURCE_LINE_LENGTH)
        self.assertTrue(context["truncated"])

    def test_caret_is_omitted_when_the_column_is_unknown(self) -> None:
        context = diagnostics.diagnostic_source_context(self.SOURCE, 0, None)
        self.assertTrue(context["available"])
        self.assertNotIn("caret", context)


def _status(**overrides: object) -> dict:
    status = {
        "found": True,
        "compiled": False,
        "noticeReadComplete": True,
        "annotationCount": 1,
        "noticeCount": 1,
        "errorCount": 1,
        "warningCount": 1,
        "errors": [],
    }
    status.update(overrides)
    return status


class SummarizeDiagnosticsTest(unittest.TestCase):
    SOURCE = "\n".join([
        'export const f = defineFeature(function(context is Context, id is Id, definition is map)',
        '    precondition { annotation { "Name" : "F" } }',
        "    {",
        "        var d = 5 * millimeter + 2;",
        '        opExtrude(context, id + "e", 5);',
        "    });",
    ])

    def test_the_same_defect_on_two_channels_becomes_one_group(self) -> None:
        shared = {
            "text": "definition.outerDiameter: Expected a range",
            "type": "error",
            "row": 3,
            "col": 8,
            "line": 4,
            "column": 9,
        }
        summary = diagnostics.summarize_diagnostics(
            _status(errors=[
                {"source": "aceAnnotation", **shared},
                {"source": "featureScriptNotice", "tabName": "FS1", **shared},
            ]),
            self.SOURCE,
        )
        self.assertEqual(summary["entryCount"], 2)  # raw observation preserved
        self.assertEqual(summary["groupCount"], 1)  # deduplicated for triage
        group = summary["groups"][0]
        self.assertEqual(group["count"], 2)
        self.assertEqual(group["sources"], ["aceAnnotation", "featureScriptNotice"])
        self.assertEqual(group["code"], "FS_EXPECTED_TYPE")

    def test_every_message_paragraph_reaches_the_group(self) -> None:
        summary = diagnostics.summarize_diagnostics(
            _status(errors=[{
                "source": "featureScriptNotice",
                "type": "error",
                "text": "first paragraph",
                "messages": ["first paragraph", "second paragraph"],
                "row": 3,
                "col": 8,
            }]),
            self.SOURCE,
        )
        self.assertEqual(summary["groups"][0]["messages"], ["first paragraph", "second paragraph"])
        self.assertEqual(summary["entries"][0]["messages"], ["first paragraph", "second paragraph"])

    def test_each_entry_carries_its_source_line(self) -> None:
        summary = diagnostics.summarize_diagnostics(
            _status(errors=[{
                "source": "aceAnnotation",
                "type": "error",
                "text": "opExtrude expects a map",
                "row": 4,
                "col": 8,
            }]),
            self.SOURCE,
        )
        context = summary["entries"][0]["sourceContext"]
        self.assertEqual(context["lineNumber"], 5)
        self.assertIn("opExtrude(context", context["sourceLine"])

    def test_missing_source_still_summarizes(self) -> None:
        summary = diagnostics.summarize_diagnostics(
            _status(errors=[{"source": "aceAnnotation", "type": "error", "text": "bad", "row": 0}])
        )
        self.assertFalse(summary["entries"][0]["sourceContext"]["available"])

    def test_severity_and_basis_counts_are_reported(self) -> None:
        summary = diagnostics.summarize_diagnostics(
            _status(errors=[
                {"source": "aceAnnotation", "type": "error", "text": "Variable A not found.", "row": 0},
                {"source": "aceAnnotation", "type": "warning", "text": "mystery", "row": 1},
                {"source": "aceAnnotation", "type": "info", "text": "note", "row": 2},
            ]),
            self.SOURCE,
        )
        self.assertEqual(summary["severityCounts"], {"error": 1, "warning": 1, "info": 1})
        self.assertEqual(summary["unclassifiedCount"], 2)
        self.assertEqual(summary["unstableCodeCount"], 3)
        self.assertEqual(
            summary["codeBasisCounts"], {"compilerMessage": 1, "unclassified": 2}
        )

    def test_group_and_message_bounds_are_reported_when_hit(self) -> None:
        errors = [
            {"source": "aceAnnotation", "type": "error", "text": f"mystery {index}", "row": 0}
            for index in range(diagnostics.MAX_GROUPS + 5)
        ]
        summary = diagnostics.summarize_diagnostics(_status(errors=errors), self.SOURCE)
        self.assertEqual(len(summary["groups"]), diagnostics.MAX_GROUPS)
        self.assertTrue(summary["groupsTruncated"])

        many = [{
            "source": "featureScriptNotice",
            "type": "error",
            "text": "primary",
            "messages": [f"paragraph {index}" for index in range(diagnostics.MAX_GROUP_MESSAGES + 3)],
            "row": 0,
        }]
        bounded = diagnostics.summarize_diagnostics(_status(errors=many), self.SOURCE)
        group = bounded["groups"][0]
        self.assertEqual(len(group["messages"]), diagnostics.MAX_GROUP_MESSAGES)
        self.assertTrue(group["messagesTruncated"])

    def test_inline_summary_is_bounded_for_a_tool_result(self) -> None:
        errors = [
            {"source": "aceAnnotation", "type": "error", "text": f"mystery {index}", "row": 0}
            for index in range(diagnostics.MAX_INLINE_GROUPS + 4)
        ]
        summary = diagnostics.summarize_diagnostics(_status(errors=errors), self.SOURCE)
        inline = diagnostics.inline_diagnostic_summary(summary)
        self.assertEqual(len(inline["groups"]), diagnostics.MAX_INLINE_GROUPS)
        self.assertTrue(inline["groupsTruncated"])
        self.assertEqual(inline["groupCount"], len(errors))

    def test_non_object_compile_status_does_not_raise(self) -> None:
        summary = diagnostics.summarize_diagnostics(None, self.SOURCE)
        self.assertEqual(summary["entryCount"], 0)
        self.assertEqual(summary["groups"], [])


class DiagnosticCaptureTest(unittest.TestCase):
    SOURCE = (
        'FeatureScript 3044;\n'
        'export const f = defineFeature(function(context is Context, id is Id, definition is map)\n'
        '    precondition { annotation { "Name" : "F" } }\n'
        "    {\n"
        "        opExtrude(context, id + \"e\", 5);\n"
        "    });\n"
    )

    def _capture(self, tmp: str, **overrides: object) -> dict:
        status = _status(errors=[{
            "source": "featureScriptNotice",
            "type": "error",
            "text": "opExtrude expected a map",
            "messages": ["opExtrude expected a map", "second detail"],
            "row": 4,
            "col": 20,
            "line": 5,
            "column": 21,
            "tabName": "FS1",
        }])
        status.update(overrides)
        return diagnostics.save_featurescript_diagnostic(
            source=self.SOURCE,
            compile_status=status,
            page_url="https://cad.onshape.com/documents/d1/w/w1/e/e1",
            phase="manual-capture",
            output_root=Path(tmp),
            captured_at="2026-09-19T10:00:00.000000Z",
        )

    def test_capture_writes_a_normalized_summary_beside_the_raw_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._capture(tmp)
            capture_dir = Path(result["captureDirectory"])
            document = json.loads((capture_dir / "diagnostics.json").read_text(encoding="utf-8"))
            manifest = json.loads((capture_dir / "manifest.json").read_text(encoding="utf-8"))
            raw = json.loads((capture_dir / "compile-result.json").read_text(encoding="utf-8"))

        self.assertTrue(result["captured"])
        self.assertEqual(document["artifactType"], "featurescript-diagnostic-summary")
        self.assertEqual(document["captureId"], result["captureId"])
        self.assertFalse(document["serverConclusion"]["compiled"])
        self.assertTrue(document["serverConclusion"]["noticeReadComplete"])
        entry = document["summary"]["entries"][0]
        self.assertEqual(entry["messages"], ["opExtrude expected a map", "second detail"])
        self.assertEqual(entry["sourceContext"]["sourceLine"], '        opExtrude(context, id + "e", 5);')
        # The verbatim browser observation is retained unchanged.
        self.assertFalse(raw["compiled"])
        self.assertEqual(raw["errors"][0]["text"], "opExtrude expected a map")
        self.assertEqual(manifest["diagnosticsFile"], "diagnostics.json")
        self.assertEqual(manifest["diagnosticCount"], 1)
        self.assertEqual(result["diagnosticCount"], 1)

    def test_capture_returns_a_bounded_entry_for_the_local_analyzer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._capture(tmp)
        entry = result["corpusEntry"]
        self.assertEqual(entry["kind"], "featurescript-compile-corpus-entry")
        self.assertEqual(entry["sourceSha256"], result["sourceSha256"])
        self.assertFalse(entry["serverConclusion"]["compiled"])
        self.assertEqual(entry["diagnostics"]["groupCount"], 1)
        self.assertEqual(result["diagnosticSummary"]["groups"][0]["code"], "FS_EXPECTED_TYPE")

    def test_capture_reports_the_code_table_it_normalized_against(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self._capture(tmp)
        self.assertIn("path", result["codeTable"])
        self.assertIn("codeCount", result["codeTable"])
        self.assertTrue(result["codeTable"]["available"])

    def test_capture_validation_and_collision_handling_are_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            first = self._capture(tmp)
            second = self._capture(tmp)
            self.assertNotEqual(first["captureId"], second["captureId"])
            with self.assertRaises(TypeError):
                diagnostics.save_featurescript_diagnostic(
                    source=1, compile_status={}, page_url="", phase="p", output_root=Path(tmp)
                )
            with self.assertRaises(ValueError):
                diagnostics.save_featurescript_diagnostic(
                    source="s", compile_status={}, page_url="", phase="  ", output_root=Path(tmp)
                )


class RetainedDiagnosticsTest(unittest.TestCase):
    SOURCE = "FeatureScript 3044;\n"

    def test_missing_root_is_reported_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = diagnostics.load_retained_diagnostics(Path(tmp) / "absent")
        self.assertFalse(result["found"])
        self.assertEqual(result["count"], 0)
        self.assertIn("no diagnostic captures", result["reason"])

    def test_captures_are_returned_newest_first_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for day in ("2026-09-17", "2026-09-18", "2026-09-19"):
                diagnostics.save_featurescript_diagnostic(
                    source=self.SOURCE,
                    compile_status=_status(errors=[{
                        "source": "aceAnnotation", "type": "error",
                        "text": f"Variable V_{day} not found.", "row": 0,
                    }]),
                    page_url="https://cad.onshape.com/documents/d1/w/w1/e/e1",
                    phase="semantic-deploy",
                    output_root=root,
                    captured_at=f"{day}T10:00:00.000000Z",
                )
            everything = diagnostics.load_retained_diagnostics(root, limit=10)
            newest_two = diagnostics.load_retained_diagnostics(root, limit=2)

        self.assertEqual(everything["count"], 3)
        self.assertFalse(everything["truncated"])
        self.assertTrue(everything["entries"][0]["capturedAt"].startswith("2026-09-19"))
        self.assertTrue(everything["entries"][-1]["capturedAt"].startswith("2026-09-17"))
        self.assertEqual(newest_two["count"], 2)
        self.assertTrue(newest_two["truncated"])
        self.assertEqual(
            everything["entries"][0]["diagnostics"]["groups"][0]["code"],
            "FS_UNRESOLVED_NAME",
        )

    def test_a_pre_summary_capture_is_reported_as_legacy_not_lost(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            legacy = root / "20260916T100000000000-abcd1234ef56"
            legacy.mkdir(parents=True)
            (legacy / "manifest.json").write_text(json.dumps({
                "captureId": "legacy-1",
                "capturedAt": "2026-09-16T10:00:00.000000Z",
                "phase": "manual-capture",
                "pageUrl": "https://cad.onshape.com/documents/d1/w/w1/e/e1",
                "sourceSha256": "a" * 64,
            }), encoding="utf-8")
            broken = root / "20260915T100000000000-deadbeef0000"
            broken.mkdir(parents=True)
            (broken / "diagnostics.json").write_text("{not json", encoding="utf-8")

            result = diagnostics.load_retained_diagnostics(root, limit=10)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["legacyCount"], 1)
        self.assertEqual(result["skippedCount"], 1)
        self.assertFalse(result["entries"][0]["normalized"])
        self.assertEqual(result["entries"][0]["captureId"], "legacy-1")

    def test_limit_must_be_positive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                diagnostics.load_retained_diagnostics(Path(tmp), limit=0)


if __name__ == "__main__":
    unittest.main()
