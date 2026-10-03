#!/usr/bin/env python3
"""Offline tests for the browser-leg STEP import (zero quota, no Playwright).

The live Import dialog has never been opened by this code, so what is tested here is the part that can
be: the PLAN's honesty, and the VERDICT RULE. The rule has one invariant worth stating twice -- a
finished translation is not an imported element, and the dialog's own UI is not evidence -- so the
tests drive fakes that can report a changed row list, an unchanged one, two new rows, or a failed read,
and assert that only the first of those ever becomes ``imported=True``.
"""

from __future__ import annotations

import json
import sys
import hashlib
import tempfile
import unittest
from typing import Any
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_browser_mode import selectors, step_import  # noqa: E402
from onshape_browser_mode.step_import import (  # noqa: E402
    plan_browser_step_import,
    source_facts,
)


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class FakePause:
    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls: list[int] = []

    def __call__(self, milliseconds: int) -> None:
        self.calls.append(milliseconds)
        self.clock.now += milliseconds / 1000.0


class FakeLocator:
    def __init__(self, page: "FakePage", selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> "FakeLocator":
        return self

    def wait_for(self, state: str | None = None, timeout: int | None = None) -> bool:
        self.page.waits.append({"selector": self.selector, "state": state})
        if not self.page.present(self.selector):
            raise RuntimeError(f"locator not present: {self.selector}")
        return True

    def click(self, **kwargs) -> None:
        self.page.clicks.append(self.selector)
        if not self.page.present(self.selector):
            raise RuntimeError(f"cannot click missing locator: {self.selector}")

    def set_input_files(self, path: str) -> None:
        self.page.input_files.append({"selector": self.selector, "path": path})
        if not self.page.file_input_attachable:
            raise RuntimeError("file input is not attachable")


class FakePage:
    """A page whose proof-row reads are scripted, so each verdict path is reachable."""

    def __init__(
        self,
        *,
        tab_reads: list = None,
        feature_reads: list = None,
        entry_present: bool = True,
        file_input_attachable: bool = True,
        raise_on_read_after: int | None = None,
        active_tab_name: str = "",
    ) -> None:
        self.url = "https://cad.onshape.com/documents/did/w/wid/e/eid"
        self.tab_reads = list(tab_reads or [])
        self.feature_reads = list(feature_reads or [])
        self.entry_present = entry_present
        self.file_input_attachable = file_input_attachable
        self.raise_on_read_after = raise_on_read_after
        self.active_tab_name = active_tab_name
        self.evaluate_calls = 0
        self.clicks: list[str] = []
        self.waits: list[dict] = []
        self.input_files: list[dict] = []

    def present(self, selector: str) -> bool:
        if selector.startswith("text="):
            return self.entry_present
        if selector == selectors.IMPORT_FILE_INPUT or selector == "input[type=file]":
            return True
        if selector == selectors.IMPORT_SUBMIT:
            return True
        return True

    def get_by_text(self, text: str, exact: bool = False) -> FakeLocator:
        return FakeLocator(self, f"text={text}")

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)

    def evaluate(self, script: str, arg=None):
        # The active-tab read backs the target_tab guard; it must not consume a proof-row read either.
        if "active-tab-name" in script:
            return self.active_tab_name
        # The measured import entry is a HIDDEN dropdown item: its click is scripted here exactly as the
        # live page answered on 2026-10-03, and it must not consume a proof-row read.
        if "dropdown-item" in script:
            return {
                "clicked": self.entry_present,
                "text": "导入…" if self.entry_present else "",
                "itemId": "upload-button" if self.entry_present else "",
                "items": ["导入…"] if self.entry_present else [],
            }
        self.evaluate_calls += 1
        index = self.evaluate_calls - 1
        if self.raise_on_read_after is not None and index >= self.raise_on_read_after:
            raise RuntimeError("page read failed")
        if "os-tab-bar-tab" in script:
            reads = self.tab_reads
        else:
            reads = self.feature_reads
        if not reads:
            return []
        if index < len(reads):
            return reads[index]
        return reads[-1]


def _source(tmp: Path, name: str = "handoff.step") -> Path:
    path = tmp / name
    path.write_bytes(b"ISO-10303-21;\nHEADER;\nENDSEC;\nEND-ISO-10303-21;\n")
    return path


class PlanTest(unittest.TestCase):
    def test_plan_states_that_a_translation_is_not_a_landing(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = step_import.plan_browser_step_import(source_path=_source(Path(tmp)))
        self.assertTrue(plan["dryRun"])
        self.assertEqual(plan["operation"], "browser-step-import")
        self.assertEqual(plan["network"], "browser")
        self.assertEqual(plan["estimatedApiRequests"], 0)
        self.assertEqual(plan["maxApiRequests"], 0)
        self.assertTrue(plan["mutating"])
        self.assertIn("exactly one new DOCUMENT ELEMENT row", plan["landingProof"]["rule"])
        self.assertIn("is not an element", plan["landingProof"]["rule"])
        self.assertIn(selectors.TAB_BAR_TAB, plan["landingProof"]["reads"])

    def test_plan_names_the_selectors_it_is_not_allowed_to_trust(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = step_import.plan_browser_step_import(source_path=_source(Path(tmp)))
        live = plan["liveAcceptance"]
        self.assertEqual(live["ledger"], step_import.LEDGER)
        self.assertEqual(live["checks"], list(step_import.LEDGER_CHECKS))
        self.assertEqual(live["status"], "pending-live-verification")
        self.assertEqual(set(live["unverifiedSelectors"]), {"dialog", "fileInput", "submit"})
        # The entry was MEASURED live 2026-10-03 (a hidden `#upload-button` dropdown item), so it must
        # no longer be listed as unverified -- while the dialog constants it never reached still are.
        self.assertNotIn("importEntryLabels", live["unverifiedSelectors"])
        self.assertEqual(plan["selectors"]["importEntry"]["item"], selectors.DOCUMENT_TABS_IMPORT_ITEM)
        self.assertEqual(plan["selectors"]["importEntry"]["menu"], selectors.DOCUMENT_TABS_CREATE_MENU)
        self.assertEqual(plan["selectors"]["importEntry"]["observedLabel"], "导入…")
        # The proof anchors must NOT be in the unverified set: that separation is the whole design.
        self.assertNotIn("tabRow", live["unverifiedSelectors"])
        self.assertNotIn("userFeatureRow", live["unverifiedSelectors"])

    def test_source_facts_are_measured_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _source(Path(tmp))
            plan = step_import.plan_browser_step_import(source_path=path)
            size = path.stat().st_size
        source = plan["source"]
        self.assertEqual(source["formatName"], "STEP")
        self.assertEqual(source["mediaType"], "model/step")
        self.assertEqual(source["byteCount"], size)
        self.assertFalse(source["sha256Stable"])
        self.assertEqual(len(source["sha256"]), 64)

    def test_non_step_sources_and_bad_arguments_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "model.igs"
            other.write_bytes(b"x")
            with self.assertRaisesRegex(ValueError, "step or .stp"):
                step_import.plan_browser_step_import(source_path=other)
            with self.assertRaises(FileNotFoundError):
                step_import.plan_browser_step_import(source_path=Path(tmp) / "nope.step")
            with self.assertRaisesRegex(ValueError, "mode must be"):
                step_import.plan_browser_step_import(source_path=_source(Path(tmp)), mode="append")
            with self.assertRaisesRegex(ValueError, "timeout_ms"):
                step_import.plan_browser_step_import(source_path=_source(Path(tmp)), timeout_ms=10)
            with self.assertRaisesRegex(ValueError, "requires target_tab"):
                step_import.plan_browser_step_import(source_path=_source(Path(tmp)), mode="into-part-studio")
            with self.assertRaisesRegex(ValueError, "requires document_id"):
                step_import.plan_browser_step_import(
                    source_path=_source(Path(tmp)), mode="into-part-studio", target_tab="Part Studio 1"
                )
            with self.assertRaisesRegex(ValueError, "opaque identifier"):
                step_import.plan_browser_step_import(
                    source_path=_source(Path(tmp)), document_id="not an id"
                )


class ImportTest(unittest.TestCase):
    def _run(self, page: FakePage, **kwargs):
        with tempfile.TemporaryDirectory() as tmp:
            clock = FakeClock()
            return step_import.import_browser_step(
                page,
                source_path=_source(Path(tmp)),
                pause=FakePause(clock),
                now=clock,
                timeout_ms=3000,
                **kwargs,
            )

    def test_one_new_tab_is_a_proven_import(self):
        page = FakePage(
            tab_reads=[
                [{"name": "Part Studio 1", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}],
                [{"name": "Part Studio 1", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}, {"name": "handoff", "elementId": "2b2b2b2b2b2b2b2b2b2b2b2b"}],
            ]
        )
        result = self._run(page)
        self.assertTrue(result["imported"])
        self.assertEqual(result["reason"], "new_tab_landed")
        self.assertEqual(result["newElement"], {"name": "handoff", "elementId": "2b2b2b2b2b2b2b2b2b2b2b2b"})
        self.assertEqual(result["spentQuota"], 0)
        self.assertEqual(result["spentApiRequests"], 0)
        self.assertEqual(page.input_files[0]["path"].endswith("handoff.step"), True)

    def test_an_unchanged_row_list_never_reads_as_success(self):
        page = FakePage(tab_reads=[[{"name": "Part Studio 1", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}]])
        result = self._run(page)
        self.assertFalse(result["imported"])
        self.assertEqual(result["reason"], "no_new_element")
        self.assertEqual(result["translationCompleted"], "unknown")
        self.assertIn("may still be running", result["detail"])

    def test_two_new_rows_are_refused_rather_than_guessed(self):
        page = FakePage(
            tab_reads=[
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}],
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}, {"name": "B", "elementId": "2b2b2b2b2b2b2b2b2b2b2b2b"},
                 {"name": "C", "elementId": "3c3c3c3c3c3c3c3c3c3c3c3c"}],
            ]
        )
        result = self._run(page)
        self.assertFalse(result["imported"])
        self.assertEqual(result["reason"], "ambiguous_new_elements")

    # --- Measured live 2026-10-03: a STEP import adds TWO tab rows --------------------------------
    # The internal `CAD 导入` row (`.os-tab-bar-tab-group`, id literally `CADImportBlobs`) appears as
    # soon as the file is uploaded, BEFORE the translated element exists. Counting any new row made the
    # tool report that bookkeeping row as the landed element -- the live call answered
    # imported=true / newElement="CAD 导入" while the real element (`model`) did not exist yet.
    def test_the_internal_bookkeeping_row_alone_is_never_the_imported_element(self):
        page = FakePage(
            tab_reads=[
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}],
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"},
                 {"name": "CAD 导入", "elementId": "CADImportBlobs", "group": True}],
            ]
        )
        result = self._run(page)
        self.assertFalse(result["imported"], "a bookkeeping row is never the imported geometry")
        self.assertEqual(result["reason"], "element_not_yet_visible")
        self.assertEqual(result["newRows"], [])
        self.assertEqual(result["internalRows"][0]["elementId"], "CADImportBlobs")
        self.assertIn("not a failed import", result["detail"])

    def test_a_late_real_element_is_attributed_while_the_internal_row_is_reported(self):
        page = FakePage(
            tab_reads=[
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}],
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"},
                 {"name": "CAD 导入", "elementId": "CADImportBlobs", "group": True}],
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"},
                 {"name": "CAD 导入", "elementId": "CADImportBlobs", "group": True},
                 {"name": "model", "elementId": "4d4d4d4d4d4d4d4d4d4d4d4d"}],
            ]
        )
        result = self._run(page)
        self.assertTrue(result["imported"])
        self.assertEqual(result["reason"], "new_tab_landed")
        self.assertEqual(result["newElement"], {"name": "model", "elementId": "4d4d4d4d4d4d4d4d4d4d4d4d"})
        self.assertEqual([row["name"] for row in result["internalRows"]], ["CAD 导入"])
        self.assertGreater(result["polls"]["reads"], 1, "the internal row alone must not end the wait")

    def test_a_group_row_stays_internal_even_with_an_element_shaped_id(self):
        page = FakePage(
            tab_reads=[
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}],
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"},
                 {"name": "疑似元素", "elementId": "5e5e5e5e5e5e5e5e5e5e5e5e", "group": True}],
            ]
        )
        result = self._run(page)
        self.assertFalse(result["imported"])
        self.assertEqual(result["reason"], "element_not_yet_visible")

    def test_a_failed_after_read_is_not_a_success(self):
        page = FakePage(
            tab_reads=[
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}],
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}, {"name": "B", "elementId": "2b2b2b2b2b2b2b2b2b2b2b2b"}],
            ],
            raise_on_read_after=1,
        )
        result = self._run(page)
        self.assertFalse(result["imported"])
        self.assertEqual(result["reason"], "element_read_failed")
        self.assertIn("page read failed", result["detail"])

    def test_a_failed_before_read_refuses_before_touching_the_page(self):
        page = FakePage(tab_reads=[], raise_on_read_after=0)
        result = self._run(page)
        self.assertEqual(result["reason"], "before_read_failed")
        self.assertEqual(page.clicks, [], "nothing may be clicked when landing cannot be judged")
        self.assertEqual(page.input_files, [])

    def test_a_missing_import_entry_reports_the_page_facts(self):
        page = FakePage(tab_reads=[[{"name": "Part Studio 1", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}]], entry_present=False)
        result = self._run(page)
        self.assertEqual(result["reason"], "import_entry_missing")
        self.assertFalse(result["importEntry"]["clicked"])
        self.assertEqual(result["pageFacts"]["url"], page.url)
        self.assertEqual(result["pageFacts"]["tabNames"], ["Part Studio 1"])

    def test_the_entry_is_clicked_through_the_measured_hidden_dropdown_item(self):
        # Measured live 2026-10-03: the entry exists in the DOM while its dropdown is closed, so a
        # visibility-gated locator misses it and the page-JavaScript click is the working route.
        page = FakePage(
            tab_reads=[
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}],
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}, {"name": "B", "elementId": "2b2b2b2b2b2b2b2b2b2b2b2b"}],
            ]
        )
        result = self._run(page)
        entry = result["importEntry"]
        self.assertTrue(entry["clicked"])
        self.assertEqual(entry["strategy"], "page_js_dropdown_item")
        self.assertEqual(entry["itemId"], "upload-button")
        self.assertEqual(entry["label"], "导入…")
        self.assertTrue(result["imported"])

    def test_the_measured_route_records_itself_before_the_label_chain(self):
        page = FakePage(tab_reads=[[{"name": "Part Studio 1", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}]], entry_present=False)
        result = self._run(page)
        self.assertFalse(result["importEntry"]["clicked"])
        self.assertIn("page_js_dropdown_item", result["importEntry"]["tried"])
        self.assertTrue(
            any(item.startswith("get_by_text:") for item in result["importEntry"]["tried"]),
            "the locator chain must still be recorded, so a miss says what was tried",
        )

    def test_an_unattachable_file_input_is_its_own_failure(self):
        page = FakePage(
            tab_reads=[
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}],
                [{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}, {"name": "B", "elementId": "2b2b2b2b2b2b2b2b2b2b2b2b"}],
            ],
            file_input_attachable=False,
        )
        result = self._run(page)
        self.assertEqual(result["reason"], "file_input_missing")
        self.assertFalse(result["imported"])
        self.assertEqual(result["importEntry"]["clicked"], True)

    def test_into_part_studio_without_a_name_match_is_unproven_not_true(self):
        page = FakePage(
            feature_reads=[["Base"], ["Base", "导入 1"]], active_tab_name="Part Studio 1",
        )
        result = self._run(page, mode="into-part-studio", target_tab="Part Studio 1", document_id="did1")
        self.assertIsNone(result["imported"])
        self.assertEqual(result["reason"], "landing_unproven")
        matched = self._run(
            FakePage(feature_reads=[["Base"], ["Base", "导入 1"]], active_tab_name="Part Studio 1"),
            mode="into-part-studio",
            target_tab="Part Studio 1",
            document_id="did1",
            expect_feature_name="导入",
        )
        self.assertTrue(matched["imported"])
        self.assertEqual(matched["reason"], "feature_row_matched")

    def test_into_part_studio_with_a_wrong_name_is_a_mismatch(self):
        page = FakePage(feature_reads=[["Base"], ["Base", "导入 1"]], active_tab_name="Part Studio 1")
        result = self._run(
            page,
            mode="into-part-studio",
            target_tab="Part Studio 1",
            document_id="did1",
            expect_feature_name="fillet",
        )
        self.assertFalse(result["imported"])
        self.assertEqual(result["reason"], "feature_row_mismatch")

    def test_a_target_tab_that_is_not_active_refuses_before_clicking_anything(self):
        # The leg never switches tabs, so the proof rows would belong to whichever element is on screen.
        page = FakePage(
            feature_reads=[["Base"], ["Base", "导入 1"]], active_tab_name="GF 4U 盒子",
        )
        result = self._run(page, mode="into-part-studio", target_tab="Part Studio 1", document_id="did1")
        self.assertFalse(result["imported"])
        self.assertEqual(result["reason"], "target_tab_not_active")
        self.assertEqual(result["activeTab"], {"name": "GF 4U 盒子", "expected": "Part Studio 1"})
        self.assertEqual(page.clicks, [], "nothing may be clicked when the target tab is not on screen")
        self.assertEqual(page.evaluate_calls, 0, "no proof rows may be read from another element")
        self.assertIsNone(result["before"])

    def test_an_unreadable_active_tab_refuses_rather_than_guessing(self):
        page = FakePage(feature_reads=[["Base"]], active_tab_name="")
        result = self._run(page, mode="into-part-studio", target_tab="Part Studio 1", document_id="did1")
        self.assertEqual(result["reason"], "active_tab_unknown")
        self.assertIn("never switches tabs", result["detail"])

    def test_the_poll_is_bounded_by_the_injected_clock(self):
        clock = FakeClock()
        page = FakePage(tab_reads=[[{"name": "A", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}]])
        with tempfile.TemporaryDirectory() as tmp:
            result = step_import.import_browser_step(
                page,
                source_path=_source(Path(tmp)),
                pause=FakePause(clock),
                now=clock,
                timeout_ms=2000,
            )
        self.assertFalse(result["imported"])
        self.assertLessEqual(result["polls"]["reads"], 5)


class RegisterTest(unittest.TestCase):
    def test_only_a_true_verdict_can_be_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "imported=True"):
                step_import.register_imported_browser_step(
                    import_id="imp1", result={"imported": False}, document_id="did1", workspace_id="wid1",
                    output_root=Path(tmp),
                )

    def test_a_registered_manifest_carries_what_was_not_proven(self):
        result = {
            "imported": True,
            "reason": "new_tab_landed",
            "translationCompleted": "assumed",
            "source": {"sha256": "ab" * 32, "path": "/tmp/handoff.step"},
            "target": {"tab": None},
            "newElement": {"name": "handoff", "elementId": "2b2b2b2b2b2b2b2b2b2b2b2b"},
            "landingProof": {"mode": "new-tab"},
            "pageFacts": {"url": "https://cad.onshape.com/..."},
            "unverifiedSelectors": ["dialog", "fileInput"],
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = step_import.register_imported_browser_step(
                import_id="imp1", result=result, document_id="did1", workspace_id="wid1",
                output_root=Path(tmp),
            )
            manifest = json.loads(Path(out["manifestPath"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["artifactType"], "imported-browser-step")
        self.assertEqual(manifest["provenance"]["spentQuota"], 0)
        self.assertEqual(manifest["provenance"]["unverifiedSelectors"], ["dialog", "fileInput"])
        self.assertEqual(manifest["verdict"]["translationCompleted"], "assumed")

    def test_registering_twice_is_refused(self):
        result = {"imported": True, "reason": "new_tab_landed", "target": {}, "source": {}}
        with tempfile.TemporaryDirectory() as tmp:
            step_import.register_imported_browser_step(
                import_id="imp1", result=result, document_id="did1", workspace_id="wid1",
                output_root=Path(tmp),
            )
            with self.assertRaisesRegex(ValueError, "already exists"):
                step_import.register_imported_browser_step(
                    import_id="imp1", result=result, document_id="did1", workspace_id="wid1",
                    output_root=Path(tmp),
                )



class StepImportDigestAddressingTest(unittest.TestCase):
    """Address by digest, resolve by path (the boundary question ① asked, on the consuming side).

    A path alone cannot say WHICH delivery is being imported: re-exporting identical geometry produces
    different bytes (an ISO-10303-21 header timestamp lands in the file), which is exactly why the handoff
    carries a digest at all. So a declared digest is checked before anything touches the page.
    """

    def _source(self, root: Path, text: str = "ISO-10303-21;\n#1=MANIFOLD_SOLID_BREP('s',#2);\n") -> Path:
        path = root / "model.step"
        path.write_text(text, encoding="ascii")
        return path

    def _handoff(self, digest: str, **overrides: Any) -> dict:
        handoff = {
            "declaration": {
                "schema": "onshapescript.handoff/0.4-draft",
                "units": "mm",
                "identity": {"sha256": digest, "sha256_stable": False,
                             "identity_rule": {"version": "onshapescript.step-artifact-identity/1"}},
            },
            "artifact": {"sha256": digest},
        }
        handoff["declaration"]["identity"].update(overrides)
        return handoff

    def test_a_declared_digest_that_matches_is_recorded_as_the_addressing_method(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp))
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            facts = source_facts(source, expect_sha256=digest)
        self.assertEqual(facts["addressedBy"], "sha256")
        self.assertEqual(facts["expectedSha256"], digest)
        self.assertIs(facts["matchesExpected"], True)

    def test_a_file_that_is_not_the_addressed_bytes_is_refused_before_the_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp))
            with self.assertRaisesRegex(ValueError, "not the addressed artifact"):
                source_facts(source, expect_sha256="0" * 64)
        # and the refusal happens in the OFFLINE plan, so nothing is clicked
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp))
            with self.assertRaisesRegex(ValueError, "Address by digest, resolve by path"):
                plan_browser_step_import(source_path=source, expect_sha256="0" * 64)

    def test_a_handoff_manifest_addresses_the_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            manifest = root / "step-manifest.json"
            manifest.write_text(json.dumps(self._handoff(digest)), encoding="utf-8")

            plan = plan_browser_step_import(source_path=source, handoff_manifest=manifest)
            self.assertEqual(plan["source"]["addressedBy"], "sha256")
            self.assertEqual(plan["source"]["handoff"]["handoffSchema"], "onshapescript.handoff/0.4-draft")
            self.assertEqual(plan["source"]["handoff"]["handoffUnits"], "mm")
            self.assertEqual(plan["source"]["handoff"]["handoffIdentityRule"],
                             "onshapescript.step-artifact-identity/1")

            # a handoff that addresses different bytes refuses the import
            stale = root / "stale.json"
            stale.write_text(json.dumps(self._handoff("a" * 64)), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "not the addressed artifact"):
                plan_browser_step_import(source_path=source, handoff_manifest=stale)

    def test_a_handoff_that_cannot_name_its_bytes_is_refused_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._source(root)
            nameless = root / "nameless.json"
            nameless.write_text(json.dumps({"declaration": {"schema": "x", "units": "mm"}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "cannot name its bytes"):
                source_facts(source, handoff=nameless)
            bogus = root / "bogus.json"
            bogus.write_text(json.dumps({"declaration": {"identity": {"sha256": "not-a-digest"}}}),
                             encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "no usable sha256"):
                source_facts(source, handoff=bogus)

    def test_the_addressing_record_survives_a_live_import_into_the_registered_manifest(self):
        """The trace has to reach the END of the chain, not just the plan.

        The plan can name the digest correctly and the registered manifest still say nothing about it if the
        live result drops the field or the registrar picks it up from somewhere else. This drives a real
        (fake-page) import with a declared digest and then registers it, asserting the record at each hop:
        plan -> live result -> `import-manifest.json`.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = _source(root)
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            clock = FakeClock()
            page = FakePage(
                tab_reads=[
                    [{"name": "Part Studio 1", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}],
                    [{"name": "Part Studio 1", "elementId": "1a1a1a1a1a1a1a1a1a1a1a1a"}, {"name": "handoff", "elementId": "2b2b2b2b2b2b2b2b2b2b2b2b"}],
                ],
            )
            result = step_import.import_browser_step(
                page, source_path=source, expect_sha256=digest,
                pause=FakePause(clock), now=clock, timeout_ms=3000,
            )
            self.assertTrue(result["imported"], result.get("reason"))
            self.assertEqual(result["source"]["addressedBy"], "sha256")
            self.assertEqual(result["source"]["expectedSha256"], digest)
            self.assertIs(result["source"]["matchesExpected"], True)

            out = step_import.register_imported_browser_step(
                import_id="imp-addressed", result=result, document_id="did1", workspace_id="wid1",
                output_root=root / "out",
            )
            manifest = json.loads(Path(out["manifestPath"]).read_text(encoding="utf-8"))

        self.assertEqual(manifest["source"]["sha256"], digest)
        self.assertEqual(manifest["source"]["addressedBy"], "sha256")
        self.assertEqual(manifest["source"]["expectedSha256"], digest)
        self.assertIs(manifest["source"]["matchesExpected"], True)
        self.assertEqual(manifest["artifactType"], "imported-browser-step")

    def test_a_malformed_expected_digest_is_refused_rather_than_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp))
            for bad in ("ABC", "0" * 63, "Z" * 64, "  " + "0" * 64):
                with self.subTest(digest=bad):
                    with self.assertRaisesRegex(ValueError, "expect_sha256"):
                        source_facts(source, expect_sha256=bad)

    def test_an_empty_handoff_argument_means_no_handoff_rather_than_a_path(self):
        """`""` is how every caller spells "none"; it must not resolve to `Path("")` == the current directory.

        Measured while wiring the operator tool: passing `handoff=""` produced "handoff manifest is not a
        readable file: ." — a confusing statement about the working directory instead of the true one.
        """
        with tempfile.TemporaryDirectory() as tmp:
            source = self._source(Path(tmp))
            for empty in ("", "   ", None):
                with self.subTest(handoff=repr(empty)):
                    plan = plan_browser_step_import(source_path=source, handoff_manifest=empty)
                    self.assertEqual(plan["source"]["addressedBy"], "path")
                    self.assertIsNone(plan["source"]["handoff"])

    def test_no_declared_digest_means_the_path_is_the_address_and_that_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            facts = source_facts(self._source(Path(tmp)))
        self.assertEqual(facts["addressedBy"], "path")
        self.assertIsNone(facts["expectedSha256"])
        self.assertIsNone(facts["matchesExpected"])
        self.assertIsNone(facts["handoff"])


if __name__ == "__main__":
    unittest.main()
