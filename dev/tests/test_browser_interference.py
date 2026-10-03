#!/usr/bin/env python3
"""Offline tests for the browser-leg interference check (issue #20).

Everything here runs without Playwright (which is not even installed in this
virtual environment): the module is driven through fake page / locator objects and
scripted probe responses. No browser is launched, no Onshape REST request is made,
and ``LIVE_API_ENABLED`` is never set.

The point of these tests is the VERDICT RULE and the self-diagnosis contract, not
the panel's real DOM (which is unverified and cannot be tested offline):

* ``clean`` requires a present panel, a completed detection WITH a documented
  completion proof, and an empty read-back; and
* two invariants are tested explicitly -- a missing panel never yields ``clean``,
  and an empty read with an unfinished/unproven detection never yields ``clean``.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_browser_mode import actions, interference, selectors  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes (no Playwright import anywhere)
# ---------------------------------------------------------------------------

class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class FakePause:
    """A pause that advances the injected clock, so a budget really expires."""

    def __init__(self, clock: FakeClock) -> None:
        self.clock = clock
        self.calls: list[int] = []

    def __call__(self, milliseconds: int) -> None:
        self.calls.append(milliseconds)
        self.clock.now += milliseconds / 1000.0


class FakeKeyboard:
    def __init__(self, page: "FakePage") -> None:
        self.page = page

    def press(self, key: str) -> None:
        self.page.key_presses.append(key)
        self.page.apply_effects("keyboard", key)


class FakeLocator:
    def __init__(self, page: "FakePage", selector: str, has_text: str | None = None) -> None:
        self.page = page
        self.selector = selector
        self.has_text = has_text

    @property
    def first(self) -> "FakeLocator":
        return self

    def filter(self, has_text: str = "") -> "FakeLocator":
        return FakeLocator(self.page, self.selector, has_text)

    def count(self) -> int:
        return self.page.count_for(self.selector, self.has_text)

    def click(self, **kwargs) -> None:
        self.page.clicks.append(
            {"selector": self.selector, "hasText": self.has_text, "kwargs": kwargs}
        )
        self.page.apply_effects(self.selector, self.has_text)

    def fill(self, value: str) -> None:
        self.page.fills.append({"selector": self.selector, "value": value})
        self.page.fill_value = value

    def input_value(self) -> str:
        return self.page.fill_readback if self.page.fill_readback is not None else self.page.fill_value

    def wait_for(self, state: str | None = None, timeout: int | None = None) -> bool:
        self.page.waits.append({"selector": self.selector, "state": state, "timeout": timeout})
        if self.page.count_for(self.selector, self.has_text) == 0:
            raise TimeoutError(f"{self.selector} never became {state}")
        return True


class FakePage:
    """A scripted Onshape page: tab strip, probe response, panel-read sequence.

    ``probe`` is the response to the ``interference:probe`` read; ``panel_reads`` is
    a sequence consumed by successive ``interference:panel`` reads (the last entry
    repeats, which is how a stalled panel is modelled). Clicks are recorded and
    optional ``effects`` mutate the scripted state, so a click ladder really has to
    click the right control.
    """

    def __init__(
        self,
        *,
        probe: dict | None = None,
        panel_reads: list[dict] | None = None,
        tabs: list[dict] | None = None,
        counts: dict[str, int] | None = None,
        texts: dict[str, list[str]] | None = None,
        tab_activates: bool = True,
    ) -> None:
        self.probe = probe if probe is not None else assembly_probe()
        self.panel_reads = panel_reads if panel_reads is not None else [panel_not_found()]
        self.panel_index = 0
        self.tabs = [dict(tab) for tab in (tabs if tabs is not None else default_tabs())]
        self.counts = dict(counts or {})
        self.texts = dict(texts or {})
        self.substring_counts: list[tuple[str, int]] = [(selectors.TAB_BAR_TAB, 1)]
        self.tab_activates = tab_activates
        self.effects: list[tuple[str, object]] = []
        self.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"
        self.clicks: list[dict] = []
        self.fills: list[dict] = []
        self.waits: list[dict] = []
        self.key_presses: list[str] = []
        self.evaluate_calls: list[str] = []
        self.wait_function_calls: list[dict] = []
        self.wait_timeout_calls: list[int] = []
        self.fill_value = ""
        self.fill_readback: str | None = None
        self.keyboard = FakeKeyboard(self)

    # -- state helpers ------------------------------------------------------
    def count_for(self, selector: str, has_text: str | None = None) -> int:
        if selector in self.counts:
            base = self.counts[selector]
        else:
            base = 0
            for substring, count in self.substring_counts:
                if substring in selector:
                    base = count
                    break
        if has_text is None:
            return base
        candidates = self.texts.get(selector, [])
        if not candidates:
            for substring, values in self.texts.items():
                if substring in selector:
                    candidates = values
                    break
        return base if any(has_text in text for text in candidates) else 0

    def apply_effects(self, selector: str, has_text: str | None) -> None:
        for substring, effect in self.effects:
            if substring in selector:
                effect(selector, has_text)

    def activate_tab_effect(self, selector: str, has_text: str | None) -> None:
        marker = 'data-id="'
        if marker not in selector:
            return
        wanted = selector.split(marker, 1)[1].split('"', 1)[0]
        self.tabs = [{**tab, "active": tab.get("id") == wanted} for tab in self.tabs]

    # -- the read path ------------------------------------------------------
    def next_panel_read(self) -> dict:
        if not self.panel_reads:
            return panel_not_found()
        index = min(self.panel_index, len(self.panel_reads) - 1)
        read = dict(self.panel_reads[index])
        if self.panel_index < len(self.panel_reads) - 1:
            self.panel_index += 1
        return read

    def evaluate(self, expression, *args):
        self.evaluate_calls.append(expression)
        if "interference:probe" in expression:
            return dict(self.probe)
        if "interference:panel" in expression:
            return self.next_panel_read()
        if "os-tab-bar-tab" in expression:
            return {"tabs": [dict(tab) for tab in self.tabs], "hasDocumentTabsToolButton": True}
        if "pointerEvents" in expression:
            return {"present": False, "blocking": False}
        raise AssertionError(f"unexpected evaluate expression: {expression[:120]!r}")

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self, selector)

    def get_by_text(self, text: str, exact: bool = False) -> FakeLocator:
        return FakeLocator(self, f"text={text}")

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.wait_timeout_calls.append(milliseconds)

    def wait_for_function(self, expression, *, arg=None, timeout=None, polling=None) -> bool:
        self.wait_function_calls.append({"expression": expression, "arg": arg, "timeout": timeout})
        if expression == actions._TAB_ACTIVE_PREDICATE:
            wanted = str((arg or {}).get("id", ""))
            if self.tab_activates:
                self.tabs = [{**tab, "active": tab.get("id") == wanted} for tab in self.tabs]
                return True
            raise TimeoutError(f"tab {wanted!r} never became active")
        raise AssertionError("unexpected wait_for_function")


# ---------------------------------------------------------------------------
# Scripted page fragments
# ---------------------------------------------------------------------------

def default_tabs() -> list[dict]:
    return [{"id": "e1", "name": "Assembly 1", "elementType": "assembly", "active": True}]


def partstudio_tabs() -> list[dict]:
    return [{"id": "e0", "name": "Part Studio 1", "elementType": "partstudio", "active": True}]


def assembly_probe(**overrides) -> dict:
    probe = {
        "pageUrl": "https://cad.onshape.com/documents/d1/w/w1/e/e1",
        "title": "doc | Assembly 1",
        "assembly": {
            "treeRootCount": 1,
            "instanceRowCount": 3,
            "visibleInstanceRowCount": 3,
            "instanceNames": ["Rotor", "Cage", "Pin"],
            "insertButtonCount": 1,
            "insertButtonVisible": True,
        },
        "analysisButton": {"count": 1, "visible": True},
        "analysisPopup": {"count": 0, "visible": False},
        "analysisPopupItemTexts": [],
        "visibleToolbarTexts": ["插入零件和装配体", "固定"],
        "keywordTexts": [],
        "containerCandidates": [],
    }
    probe.update(overrides)
    return probe


def partstudio_probe() -> dict:
    return {
        "pageUrl": "https://cad.onshape.com/documents/d1/w/w1/e/e1",
        "title": "doc | Part Studio 1",
        "assembly": {
            "treeRootCount": 0,
            "instanceRowCount": 0,
            "visibleInstanceRowCount": 0,
            "instanceNames": [],
            "insertButtonCount": 0,
            "insertButtonVisible": False,
        },
        "analysisButton": {"count": 1, "visible": True},
        "analysisPopup": {"count": 0, "visible": False},
        "analysisPopupItemTexts": [],
        "visibleToolbarTexts": ["圆角", "倒角", "拔模"],
        "keywordTexts": [],
        "containerCandidates": [],
    }


def panel_not_found(**overrides) -> dict:
    read = {
        "found": False,
        "rootTag": "",
        "rootClass": "",
        "rootText": "",
        "observedCandidates": ["干涉检测…"],
        "keywordNodes": [],
    }
    read.update(overrides)
    return read


def panel_found(
    *,
    row_texts: list[str] | None = None,
    summary_texts: list[str] | None = None,
    empty_texts: list[str] | None = None,
    progress_visible: bool = False,
    inputs: list[dict] | None = None,
    buttons: list[dict] | None = None,
) -> dict:
    rows = row_texts if row_texts is not None else []
    return {
        "found": True,
        "rootTag": "div",
        "rootClass": "interference-view",
        "rootText": "干涉检测 容差 计算",
        "inputs": inputs
        if inputs is not None
        else [{"tag": "input", "type": "text", "value": "0.01", "placeholder": "容差", "ariaLabel": "", "title": "", "visible": True}],
        "buttons": buttons
        if buttons is not None
        else [{"text": "计算", "disabled": False, "cls": "os-primary", "visible": True}],
        "runButtonTextsMatched": ["计算"],
        "rowCount": len(rows),
        "rowTexts": list(rows),
        "summaryTexts": list(summary_texts or []),
        "emptyTexts": list(empty_texts or []),
        "progressVisible": progress_visible,
        "keywordNodes": [{"tag": "div", "visible": True, "text": "干涉检测"}],
        "closeCandidates": [],
    }


def run_button_counts() -> dict[str, int]:
    return {interference.SELECTORS["panelButton"]: 1}


def run_button_texts() -> dict[str, list[str]]:
    return {interference.SELECTORS["panelButton"]: ["计算"]}


def close_button_counts() -> dict[str, int]:
    return {interference.SELECTORS["panelClose"]: 1}


def check(page: FakePage, **kwargs) -> dict:
    clock = FakeClock()
    pause = FakePause(clock)
    kwargs.setdefault("clock", clock)
    kwargs.setdefault("pause", pause)
    result = interference.browser_interference_check(page, **kwargs)
    result["_pause"] = pause
    result["_clock"] = clock
    return result


# ---------------------------------------------------------------------------
# The verdict rule: four mappings
# ---------------------------------------------------------------------------

class VerdictMappingTest(unittest.TestCase):
    """clean / interference / indeterminate / unavailable are the only verdicts."""

    def test_clean_needs_a_present_panel_a_proof_and_an_empty_read(self):
        page = FakePage(
            panel_reads=[
                panel_found(empty_texts=["未检测到干涉"]),
                panel_not_found(),
            ],
            counts=close_button_counts(),
        )
        result = check(page)
        self.assertEqual(result["verdict"], interference.VERDICT_CLEAN)
        self.assertTrue(result["panel_available"])
        self.assertTrue(result["detection_completed"])
        self.assertEqual(result["interference_count"], 0)
        self.assertEqual(result["pairs"], [])
        self.assertEqual(result["failureClass"], interference.FAILURE_NONE)
        self.assertEqual(result["evidence"]["proofBasis"], "empty_marker")
        self.assertEqual(result["evidence"]["emptyStateText"], "未检测到干涉")
        self.assertTrue(result["evidence"]["panelRestored"])
        self.assertEqual(result["evidence"]["apiRequests"], 0)
        self.assertFalse(result["evidence"]["mutating"])

    def test_a_stated_count_of_zero_is_also_a_completion_proof(self):
        page = FakePage(
            panel_reads=[panel_found(summary_texts=["0 处干涉"]), panel_not_found()],
            counts=close_button_counts(),
        )
        result = check(page)
        self.assertEqual(result["verdict"], interference.VERDICT_CLEAN)
        self.assertEqual(result["evidence"]["proofBasis"], "summary_count")
        self.assertEqual(result["evidence"]["summaryCount"], 0)

    def test_interference_is_reported_with_names_volume_and_raw_text(self):
        rows = [
            "1. Rotor ↔ Cage  0.500000 mm³",
            "2. Pin ↔ Plate  0.125000 cm³",
        ]
        page = FakePage(
            panel_reads=[
                panel_found(row_texts=rows, summary_texts=["2 处干涉"]),
                panel_not_found(),
            ],
            counts=close_button_counts(),
        )
        result = check(page)
        self.assertEqual(result["verdict"], interference.VERDICT_INTERFERENCE)
        self.assertEqual(result["interference_count"], 2)
        self.assertEqual(len(result["pairs"]), 2)
        first = result["pairs"][0]
        self.assertEqual(first["entityA"], "Rotor")
        self.assertEqual(first["entityB"], "Cage")
        self.assertEqual(first["intersectionVolume"]["value"], 0.5)
        self.assertEqual(first["intersectionVolume"]["unit"], "mm³")
        # Whitespace runs are folded, exactly as the repo's other browser reads do.
        self.assertEqual(first["rawText"], "1. Rotor ↔ Cage 0.500000 mm³")
        self.assertFalse(first["zeroVolumeContact"])
        self.assertEqual(result["pairs"][1]["intersectionVolume"]["unit"], "cm³")
        self.assertTrue(result["panel_available"])
        self.assertTrue(result["detection_completed"])
        self.assertEqual(result["evidence"]["resultConsistency"]["status"], "consistent")

    def test_unavailable_when_the_target_tab_is_not_an_assembly(self):
        page = FakePage(probe=partstudio_probe(), tabs=partstudio_tabs())
        result = check(page)
        self.assertEqual(result["verdict"], interference.VERDICT_UNAVAILABLE)
        self.assertEqual(result["failureClass"], interference.FAILURE_NOT_ASSEMBLY)
        self.assertFalse(result["panel_available"])
        self.assertFalse(result["detection_completed"])
        self.assertEqual(result["tab_name"], "Part Studio 1")
        environment = result["evidence"]["assemblyEnvironment"]
        self.assertFalse(environment["present"])
        self.assertEqual(environment["signals"], [])
        self.assertIn("Part Studio 1", result["evidence"]["observedTabNames"])

    def test_indeterminate_when_the_page_probe_itself_fails(self):
        page = FakePage()
        probe_holder = {"fail": True}

        class Exploding(FakePage):
            def evaluate(self, expression, *args):
                if "interference:probe" in expression and probe_holder["fail"]:
                    raise RuntimeError("target closed")
                return super().evaluate(expression, *args)

        result = check(Exploding())
        self.assertEqual(result["verdict"], interference.VERDICT_INDETERMINATE)
        self.assertEqual(result["failureClass"], interference.FAILURE_PAGE_PROBE_FAILED)
        self.assertIn("RuntimeError", result["reason"])


# ---------------------------------------------------------------------------
# The two invariants
# ---------------------------------------------------------------------------

class NeverCleanInvariantTest(unittest.TestCase):
    """The reason this tool exists: never a false ``clean``."""

    def test_a_missing_panel_is_never_clean_even_when_zero_rows_would_be_read(self):
        """The panel miss must not be reported as "no interference".

        The probe here even SHOWS the "干涉检测…" label in a menu, so the code has
        every excuse to guess the panel is fine; it still must not.
        """
        probe = assembly_probe(
            analysisPopupItemTexts=["曲线/曲面分析…", "偏差分析…", "干涉检测…"],
            analysisPopup={"count": 1, "visible": True},
            visibleToolbarTexts=["插入零件和装配体", "干涉检测"],
            keywordTexts=[{"tag": "span", "cls": "tool-label", "visible": False, "text": "干涉检测…"}],
            containerCandidates=[{"tag": "div", "cls": "analysisControlPopup", "visible": False, "text": "曲线/曲面分析… 干涉检测…"}],
        )
        page = FakePage(probe=probe, panel_reads=[panel_not_found()])
        result = check(page)
        self.assertNotEqual(result["verdict"], interference.VERDICT_CLEAN)
        self.assertEqual(result["verdict"], interference.VERDICT_INDETERMINATE)
        self.assertEqual(result["failureClass"], interference.FAILURE_PANEL_UNAVAILABLE)
        self.assertFalse(result["panel_available"])
        self.assertFalse(result["detection_completed"])
        self.assertEqual(result["pairs"], [])
        self.assertEqual(result["interference_count"], 0)

    def test_an_empty_read_without_a_completion_proof_is_never_clean(self):
        """Zero rows prove nothing unless the run is shown to have happened."""
        page = FakePage(
            # The panel stays present and empty for the whole wait: only the run's
            # completion proof is missing, which is exactly the dangerous case.
            panel_reads=[
                panel_found(row_texts=[], summary_texts=[], empty_texts=[], progress_visible=False)
            ],
            counts={**run_button_counts(), **close_button_counts()},
            texts=run_button_texts(),
        )
        result = check(page)
        self.assertNotEqual(result["verdict"], interference.VERDICT_CLEAN)
        self.assertEqual(result["verdict"], interference.VERDICT_INDETERMINATE)
        self.assertEqual(result["failureClass"], interference.FAILURE_DETECTION_NOT_COMPLETED)
        self.assertFalse(result["detection_completed"])
        self.assertTrue(result["panel_available"])
        self.assertEqual(result["evidence"]["detection"]["proof"]["basis"], "")
        self.assertIn("not proof", result["evidence"]["detection"]["proof"]["reason"])
        self.assertEqual(result["pairs"], [])

    def test_a_detection_that_never_finishes_times_out_and_is_never_clean(self):
        page = FakePage(
            panel_reads=[
                panel_found(summary_texts=[], empty_texts=[]),
                panel_not_found(),
            ],
            counts={**run_button_counts(), **close_button_counts()},
            texts=run_button_texts(),
        )
        result = check(page)
        self.assertNotEqual(result["verdict"], interference.VERDICT_CLEAN)
        self.assertEqual(result["failureClass"], interference.FAILURE_DETECTION_NOT_COMPLETED)
        self.assertFalse(result["detection_completed"])

    def test_an_unreachable_proof_is_still_required_by_completion_proof(self):
        """Direct check of the predicate the invariant rests on."""
        proof = interference._completion_proof(
            {"found": True, "rowTexts": [], "summaryTexts": [], "emptyTexts": []},
            progress_seen=False,
        )
        self.assertEqual(proof["basis"], "")
        self.assertIn("not proof", proof["reason"])

    def test_filters_that_remove_every_row_are_not_reported_as_clean(self):
        page = FakePage(
            panel_reads=[
                panel_found(row_texts=["Cage ↔ Rotor 0.5 mm³"], summary_texts=["1 处干涉"]),
                panel_not_found(),
            ],
            counts=close_button_counts(),
        )
        result = check(page, part_names=["NoSuchPart"])
        self.assertNotEqual(result["verdict"], interference.VERDICT_CLEAN)
        self.assertEqual(result["verdict"], interference.VERDICT_INDETERMINATE)
        self.assertEqual(result["failureClass"], interference.FAILURE_PART_FILTER_EXCLUDED_ALL)
        self.assertEqual(result["pairs"], [])
        self.assertEqual(result["evidence"]["unfilteredPairCount"], 1)


# ---------------------------------------------------------------------------
# Bounded waits
# ---------------------------------------------------------------------------

class BoundedWaitTest(unittest.TestCase):
    """Budgets are explainable and really interrupted; they are never guessed."""

    def test_the_detection_wait_is_scaled_by_instance_count_and_capped(self):
        profile = interference.DETECTION_WAIT
        self.assertEqual(interference.detection_wait_budget_ms(profile, 0), profile["baseMs"])
        self.assertEqual(
            interference.detection_wait_budget_ms(profile, 40),
            profile["baseMs"] + profile["perInstanceMs"] * 40,
        )
        self.assertEqual(interference.detection_wait_budget_ms(profile, 100_000), profile["maxMs"])
        # An unreadable count reproduces the floor instead of extending the budget.
        self.assertEqual(interference.detection_wait_budget_ms(profile, None), profile["baseMs"])
        self.assertEqual(interference.detection_wait_budget_ms(profile, "nope"), profile["baseMs"])

    def test_a_stalled_detection_is_interrupted_by_the_budget(self):
        page = FakePage(
            panel_reads=[panel_found(summary_texts=[], empty_texts=[]), panel_not_found()],
            counts={**run_button_counts(), **close_button_counts()},
            texts=run_button_texts(),
        )
        result = check(page)
        wait = result["evidence"]["detection"]["wait"]
        self.assertTrue(wait["timedOut"])
        self.assertGreaterEqual(wait["elapsedMs"], wait["budgetMs"])
        self.assertEqual(wait["budgetMs"], result["evidence"]["budgets"]["detectionWaitMs"])
        self.assertEqual(wait["pollMs"], interference.DETECTION_POLL_MS)
        # The loop is bounded in iterations as well as in time, so a clock that
        # never advances cannot spin forever.
        self.assertLessEqual(wait["attempts"], wait["maxIterations"])
        self.assertLessEqual(len(result["_pause"].calls), wait["maxIterations"])
        self.assertTrue(all(call == interference.DETECTION_POLL_MS for call in result["_pause"].calls))

    def test_a_non_advancing_clock_still_terminates_on_the_iteration_cap(self):
        page = FakePage(
            panel_reads=[panel_found(summary_texts=[], empty_texts=[]), panel_not_found()],
            counts={**run_button_counts(), **close_button_counts()},
            texts=run_button_texts(),
        )
        frozen = FakeClock()
        result = interference.browser_interference_check(
            page,
            clock=frozen,
            pause=lambda milliseconds: None,  # clock never advances
        )
        wait = result["evidence"]["detection"]["wait"]
        self.assertTrue(wait["timedOut"])
        self.assertEqual(wait["attempts"], wait["maxIterations"])
        self.assertEqual(result["verdict"], interference.VERDICT_INDETERMINATE)

    def test_the_budgets_block_explains_where_every_number_comes_from(self):
        page = FakePage(
            panel_reads=[panel_found(empty_texts=["未检测到干涉"]), panel_not_found()],
            counts=close_button_counts(),
        )
        result = check(page)
        budgets = result["evidence"]["budgets"]
        self.assertEqual(budgets["panelOpenTimeoutMs"], interference.PANEL_OPEN_TIMEOUT_MS)
        self.assertEqual(budgets["panelMenuTimeoutMs"], interference.PANEL_MENU_TIMEOUT_MS)
        self.assertEqual(budgets["panelCloseTimeoutMs"], interference.PANEL_CLOSE_TIMEOUT_MS)
        self.assertEqual(budgets["instanceCountBasis"], 3)
        self.assertEqual(
            budgets["detectionWaitMs"],
            interference.DETECTION_WAIT["baseMs"] + interference.DETECTION_WAIT["perInstanceMs"] * 3,
        )
        self.assertIn("baseMs", budgets["basis"])

    def test_a_run_observed_in_progress_and_then_settled_is_a_completion_proof(self):
        page = FakePage(
            panel_reads=[
                panel_found(summary_texts=[], empty_texts=[], progress_visible=False),
                panel_found(summary_texts=[], empty_texts=[], progress_visible=True),
                panel_found(summary_texts=[], empty_texts=[], progress_visible=False),
                panel_not_found(),
            ],
            counts={**run_button_counts(), **close_button_counts()},
            texts=run_button_texts(),
        )
        result = check(page)
        self.assertEqual(result["verdict"], interference.VERDICT_CLEAN)
        self.assertEqual(result["evidence"]["proofBasis"], "progress_completed")
        self.assertTrue(result["evidence"]["detection"]["progressObserved"])


# ---------------------------------------------------------------------------
# Zero-volume contacts and part_names filtering
# ---------------------------------------------------------------------------

class ZeroVolumeTest(unittest.TestCase):
    """A proven zero-volume contact is included or excluded by the switch."""

    ROWS = ["A ↔ B 0 mm³", "C ↔ D 0.400000 mm³"]

    def _run(self, include_zero_volume: bool) -> dict:
        page = FakePage(
            panel_reads=[
                panel_found(row_texts=self.ROWS, summary_texts=["2 处干涉"]),
                panel_not_found(),
            ],
            counts=close_button_counts(),
        )
        return check(page, include_zero_volume=include_zero_volume)

    def test_zero_volume_contacts_are_excluded_by_default(self):
        result = self._run(False)
        self.assertEqual(result["verdict"], interference.VERDICT_INTERFERENCE)
        self.assertEqual(result["interference_count"], 1)
        self.assertEqual(result["pairs"][0]["entityA"], "C")
        self.assertEqual(result["evidence"]["zeroVolume"]["excludedZeroVolumePairs"], 1)
        self.assertEqual(result["evidence"]["rowCount"], 2)

    def test_zero_volume_contacts_are_included_on_request(self):
        result = self._run(True)
        self.assertEqual(result["interference_count"], 2)
        self.assertEqual(result["pairs"][0]["zeroVolumeContact"], True)
        self.assertEqual(result["evidence"]["zeroVolume"]["includedZeroVolumePairs"], 1)
        self.assertEqual(result["evidence"]["zeroVolume"]["excludedZeroVolumePairs"], 0)

    def test_an_explicit_contact_marker_is_proof_of_a_zero_volume_contact(self):
        built = interference.build_pairs(["A ↔ B 仅接触"], include_zero_volume=False)
        self.assertEqual(built["pairs"], [])
        self.assertEqual(built["excludedZeroVolumePairs"], 1)
        built = interference.build_pairs(["A ↔ B 仅接触"], include_zero_volume=True)
        self.assertEqual(built["pairs"][0]["zeroVolumeContact"], True)

    def test_an_all_contact_panel_is_clean_when_contacts_were_excluded_by_request(self):
        """A panel whose only rows are proven touches is not an interference."""
        page = FakePage(
            panel_reads=[
                panel_found(row_texts=["A ↔ B 0 mm³", "C ↔ D 仅接触"], summary_texts=["2 处干涉"]),
                panel_not_found(),
            ],
            counts=close_button_counts(),
        )
        result = check(page, include_zero_volume=False)
        self.assertEqual(result["verdict"], interference.VERDICT_CLEAN)
        self.assertEqual(result["evidence"]["zeroVolume"]["excludedZeroVolumePairs"], 2)
        self.assertEqual(result["evidence"]["rowCount"], 2)
        self.assertEqual(result["evidence"]["unfilteredPairCount"], 0)
        self.assertFalse(result["evidence"]["partFilter"]["filterApplied"])
        self.assertIn("zero-volume", result["reason"])

    def test_a_row_the_panel_does_not_quantify_is_kept_and_marked_unknown(self):
        """Never silently drop a row just because its volume is unreadable."""
        built = interference.build_pairs(["RotorCageOverlap"], include_zero_volume=False)
        self.assertEqual(len(built["pairs"]), 1)
        self.assertIsNone(built["pairs"][0]["zeroVolumeContact"])
        self.assertIsNone(built["pairs"][0]["intersectionVolume"])
        self.assertFalse(built["pairs"][0]["namesParsed"])
        self.assertIsNone(built["pairs"][0]["entityA"])
        self.assertEqual(built["pairs"][0]["rawText"], "RotorCageOverlap")
        self.assertEqual(built["unknownZeroVolumePairs"], 1)


class PartNameFilterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.page = FakePage(
            panel_reads=[
                panel_found(
                    row_texts=["Cage ↔ Rotor 0.5 mm³", "Pin ↔ Plate 0.2 mm³"],
                    summary_texts=["2 处干涉"],
                ),
                panel_not_found(),
            ],
            counts=close_button_counts(),
        )

    def test_only_pairs_one_of_the_named_parts_participates_in_are_returned(self):
        result = check(self.page, part_names=["Cage"])
        self.assertEqual(result["verdict"], interference.VERDICT_INTERFERENCE)
        self.assertEqual(result["interference_count"], 1)
        self.assertEqual(result["pairs"][0]["entityA"], "Cage")
        part_filter = result["evidence"]["partFilter"]
        self.assertTrue(part_filter["filterApplied"])
        self.assertEqual(part_filter["filterMode"], "either_side_substring")
        self.assertEqual(part_filter["matchedPartNames"], ["Cage"])
        self.assertEqual(part_filter["filteredOutCount"], 1)
        self.assertEqual(result["evidence"]["unfilteredPairCount"], 2)

    def test_a_name_that_matched_nothing_is_reported_not_silently_absorbed(self):
        result = check(
            FakePage(
                panel_reads=[
                    panel_found(row_texts=["Cage ↔ Rotor 0.5 mm³"], summary_texts=["1 处干涉"]),
                    panel_not_found(),
                ],
                counts=close_button_counts(),
            ),
            part_names=["Cage", "Ghost"],
        )
        self.assertEqual(result["evidence"]["partFilter"]["unmatchedPartNames"], ["Ghost"])
        self.assertEqual(result["interference_count"], 1)

    def test_no_filter_is_recorded_as_not_applied(self):
        result = check(
            FakePage(
                panel_reads=[
                    panel_found(row_texts=["Cage ↔ Rotor 0.5 mm³"], summary_texts=["1 处干涉"]),
                    panel_not_found(),
                ],
                counts=close_button_counts(),
            )
        )
        self.assertFalse(result["evidence"]["partFilter"]["filterApplied"])
        self.assertEqual(result["evidence"]["partFilter"]["filterMode"], "none")


# ---------------------------------------------------------------------------
# Self-diagnosis: a miss returns what was seen
# ---------------------------------------------------------------------------

class SelfDiagnosisTest(unittest.TestCase):
    """A selector miss returns observed page facts, not a guess."""

    def test_a_panel_miss_returns_the_active_tab_name_and_the_candidate_texts(self):
        probe = assembly_probe(
            analysisPopupItemTexts=["曲线/曲面分析…", "干涉检测…"],
            analysisPopup={"count": 1, "visible": True},
            visibleToolbarTexts=["插入零件和装配体", "干涉检测"],
            keywordTexts=[{"tag": "span", "cls": "tool-label", "visible": False, "text": "干涉检测…"}],
            containerCandidates=[
                {"tag": "div", "cls": "analysisControlPopup", "visible": True, "text": "曲线/曲面分析… 干涉检测…"}
            ],
        )
        page = FakePage(probe=probe, panel_reads=[panel_not_found()])
        result = check(page)
        evidence = result["evidence"]
        # The active tab that was actually on screen.
        self.assertEqual(evidence["observation"]["activeTab"], "Assembly 1")
        self.assertEqual(evidence["observation"]["activeTabId"], "e1")
        # The candidate texts the module looked at.
        observed = evidence["panelOpen"]["observed"]
        self.assertIn("干涉检测…", observed["analysisPopupItemTexts"])
        self.assertIn("干涉检测", observed["visibleToolbarTexts"])
        self.assertEqual(observed["keywordTexts"][0]["text"], "干涉检测…")
        self.assertEqual(observed["containerCandidates"][0]["cls"], "analysisControlPopup")
        # Every click attempt is recorded, with the selector and the try text.
        steps = [entry["step"] for entry in evidence["panelOpen"]["attempts"]]
        self.assertIn("click_popup_item", steps)
        self.assertIn("click_toolbar_item", steps)
        popup_step = next(e for e in evidence["panelOpen"]["attempts"] if e["step"] == "click_popup_item")
        self.assertEqual(popup_step["attempts"][0]["selector"], interference.SELECTORS["analysisPopupItem"])
        self.assertIn("干涉检测", [entry["text"] for entry in popup_step["attempts"]])
        # The unverified selector set travels with the failure so a human can fix it.
        self.assertIn("panelRoot", result["evidence"]["unverifiedSelectors"])

    def test_the_unverified_selector_set_names_every_guessed_selector(self):
        keys = interference.unverified_selector_keys()
        for key in ("panelRoot", "panelToleranceInput", "panelButton", "panelResultRow", "panelClose"):
            self.assertIn(key, keys)
        # The anchors that ARE verified must not be listed as unverified.
        for key in ("analysisButton", "analysisPopup", "assemblyTreeRoot", "assemblyInstanceRow"):
            self.assertNotIn(key, keys)
            self.assertTrue(
                interference.SELECTOR_PROVENANCE[key].startswith("verified-live"),
                key,
            )

    def test_the_selector_map_values_come_from_the_repo_selector_module(self):
        self.assertEqual(interference.SELECTORS["assemblyInstanceRow"], selectors.ASM_INSTANCE_ROW)
        self.assertEqual(interference.SELECTORS["assemblyInsertButton"], selectors.ASM_INSERT_BUTTON)
        self.assertEqual(interference.SELECTORS["analysisPopup"], selectors.ANALYSIS_POPUP)
        self.assertEqual(interference.SELECTORS["analysisButton"], selectors.ANALYSIS_BUTTON)
        self.assertEqual(interference.SELECTORS["panelRoot"], selectors.ASM_INTERFERENCE_PANEL)
        self.assertEqual(interference.SELECTORS["panelResultRow"], selectors.ASM_INTERFERENCE_ROW)
        self.assertEqual(interference.SELECTORS["tabBarTab"], selectors.TAB_BAR_TAB)


# ---------------------------------------------------------------------------
# Tolerance
# ---------------------------------------------------------------------------

class ToleranceTest(unittest.TestCase):
    def test_a_requested_tolerance_that_cannot_be_set_withholds_a_verdict(self):
        page = FakePage(
            panel_reads=[
                panel_found(row_texts=[], empty_texts=["未检测到干涉"]),
                panel_not_found(),
            ],
            counts={interference.SELECTORS["panelToleranceInput"]: 0, **close_button_counts()},
        )
        result = check(page, tolerance_mm=0.01)
        self.assertNotEqual(result["verdict"], interference.VERDICT_CLEAN)
        self.assertEqual(result["failureClass"], interference.FAILURE_TOLERANCE_NOT_APPLIED)
        self.assertFalse(result["evidence"]["tolerance"]["applied"])
        self.assertIn("readback", result["evidence"]["tolerance"]["note"])

    def test_a_fill_whose_readback_differs_is_not_treated_as_applied(self):
        page = FakePage(
            panel_reads=[panel_found(empty_texts=["未检测到干涉"]), panel_not_found()],
            counts={interference.SELECTORS["panelToleranceInput"]: 1, **close_button_counts()},
        )
        page.fill_readback = "0.5"  # the field kept a different value
        result = check(page, tolerance_mm=0.01)
        self.assertEqual(result["failureClass"], interference.FAILURE_TOLERANCE_NOT_APPLIED)
        self.assertFalse(result["evidence"]["tolerance"]["applied"])
        self.assertFalse(result["evidence"]["tolerance"]["fill"]["readbackOk"])

    def test_an_applied_tolerance_forces_a_fresh_run_and_is_read_back(self):
        page = FakePage(
            panel_reads=[
                panel_found(summary_texts=["9 处干涉"], row_texts=["old ↔ row 1 mm³"]),
                panel_found(row_texts=[], summary_texts=[], empty_texts=["未检测到干涉"]),
                panel_not_found(),
            ],
            counts={
                interference.SELECTORS["panelToleranceInput"]: 1,
                **run_button_counts(),
                **close_button_counts(),
            },
            texts=run_button_texts(),
        )
        result = check(page, tolerance_mm=0.05)
        self.assertEqual(result["verdict"], interference.VERDICT_CLEAN)
        tolerance = result["evidence"]["tolerance"]
        self.assertTrue(tolerance["applied"])
        self.assertEqual(tolerance["requestedText"], "0.05")
        self.assertEqual(tolerance["basis"], "field_readback")
        self.assertEqual(page.fills[0]["value"], "0.05")
        # The stale pre-run result must not have been reused.
        self.assertEqual(result["evidence"]["detection"]["proof"]["freshness"], "after_run_click")
        self.assertEqual(result["evidence"]["detection"]["preRunProof"]["basis"], "")

    def test_a_panel_still_showing_the_pre_run_result_is_not_a_fresh_detection(self):
        """A stale displayed result must not be read as a measurement at the new tolerance."""
        stale = panel_found(summary_texts=["9 处干涉"], row_texts=["old ↔ row 1 mm³"])
        page = FakePage(
            panel_reads=[stale],  # the display never moves
            counts={
                interference.SELECTORS["panelToleranceInput"]: 1,
                **run_button_counts(),
                **close_button_counts(),
            },
            texts=run_button_texts(),
        )
        result = check(page, tolerance_mm=0.05)
        self.assertNotEqual(result["verdict"], interference.VERDICT_CLEAN)
        self.assertNotEqual(result["verdict"], interference.VERDICT_INTERFERENCE)
        self.assertEqual(result["failureClass"], interference.FAILURE_DETECTION_NOT_COMPLETED)
        self.assertFalse(result["detection_completed"])
        self.assertTrue(result["evidence"]["detection"]["staleResultRejected"])
        self.assertIn("pre-run", result["evidence"]["detection"]["proof"]["reason"])

    def test_no_tolerance_requested_records_that_the_panel_value_was_used(self):
        page = FakePage(
            panel_reads=[panel_found(empty_texts=["未检测到干涉"]), panel_not_found()],
            counts=close_button_counts(),
        )
        result = check(page)
        tolerance = result["evidence"]["tolerance"]
        self.assertIsNone(tolerance["requestedMm"])
        self.assertEqual(tolerance["basis"], "panel_current_value")
        self.assertFalse(tolerance["applied"])
        self.assertEqual(tolerance["panelToleranceCandidates"][0]["value"], "0.01")
        self.assertEqual(page.fills, [])

    def test_a_pre_existing_proof_is_labelled_as_pre_existing(self):
        page = FakePage(
            panel_reads=[panel_found(empty_texts=["未检测到干涉"]), panel_not_found()],
            counts=close_button_counts(),
        )
        result = check(page)
        self.assertEqual(result["evidence"]["detection"]["proof"]["freshness"], "pre_existing")
        self.assertFalse(result["evidence"]["detection"]["runClicked"])
        self.assertEqual(result["evidence"]["detection"]["wait"]["attempts"], 0)


# ---------------------------------------------------------------------------
# Cross-checks and restore
# ---------------------------------------------------------------------------

class CrossCheckTest(unittest.TestCase):
    def test_a_stated_count_that_disagrees_with_the_rows_refuses_to_pick_a_side(self):
        page = FakePage(
            panel_reads=[
                panel_found(row_texts=["A ↔ B 0.1 mm³"], summary_texts=["3 处干涉"]),
                panel_not_found(),
            ],
            counts=close_button_counts(),
        )
        result = check(page)
        self.assertEqual(result["verdict"], interference.VERDICT_INDETERMINATE)
        self.assertEqual(result["failureClass"], interference.FAILURE_RESULT_UNREADABLE)
        self.assertEqual(result["evidence"]["resultConsistency"]["status"], "mismatch")
        self.assertIn("not trustworthy", result["reason"])

    def test_a_failed_restore_is_reported_but_does_not_change_the_verdict(self):
        page = FakePage(
            panel_reads=[panel_found(empty_texts=["未检测到干涉"])],  # never closes
            counts={},  # no close control either, so Escape is the only lever
        )
        result = check(page)
        self.assertEqual(result["verdict"], interference.VERDICT_CLEAN)
        self.assertFalse(result["evidence"]["panelRestored"])
        self.assertEqual(result["failureClass"], interference.FAILURE_NONE)
        classes = [entry["class"] for entry in result["failures"]]
        self.assertIn(interference.FAILURE_PANEL_RESTORE_FAILED, classes)
        steps = [step["step"] for step in result["evidence"]["panelClose"]["attempts"]]
        self.assertIn("press_escape", steps)
        self.assertIn("press_escape_retry", steps)
        self.assertEqual(page.key_presses, ["Escape", "Escape"])

    def test_escape_is_used_to_restore_the_panel_when_no_close_control_matches(self):
        page = FakePage(
            panel_reads=[panel_found(empty_texts=["未检测到干涉"]), panel_not_found()],
            counts={},
        )
        result = check(page)
        self.assertEqual(result["verdict"], interference.VERDICT_CLEAN)
        self.assertTrue(result["evidence"]["panelRestored"])
        self.assertIn("Escape", page.key_presses)


# ---------------------------------------------------------------------------
# Tab resolution and switching (reuses the existing assembly layer)
# ---------------------------------------------------------------------------

class TabHandlingTest(unittest.TestCase):
    def test_a_tab_name_that_matches_nothing_is_unavailable_and_never_clean(self):
        page = FakePage(tabs=default_tabs())
        result = check(page, tab_name="Assembly 9")
        self.assertEqual(result["verdict"], interference.VERDICT_UNAVAILABLE)
        self.assertEqual(result["failureClass"], interference.FAILURE_TAB_NOT_FOUND)
        self.assertEqual(result["evidence"]["targetTab"]["matchCount"], 0)
        self.assertIn("Assembly 1", result["evidence"]["observedTabNames"])

    def test_an_ambiguous_tab_name_is_refused_rather_than_guessed(self):
        page = FakePage(
            tabs=[
                {"id": "e1", "name": "Assembly 1", "elementType": "assembly", "active": True},
                {"id": "e2", "name": "Assembly 1", "elementType": "assembly", "active": False},
            ]
        )
        result = check(page, tab_name="Assembly 1")
        self.assertEqual(result["verdict"], interference.VERDICT_UNAVAILABLE)
        self.assertEqual(result["evidence"]["targetTab"]["matchCount"], 2)

    def test_the_switch_reuses_semantic_open_tab_and_then_runs_the_check(self):
        tabs = [
            {"id": "e0", "name": "Part Studio 1", "elementType": "partstudio", "active": True},
            {"id": "e1", "name": "Assembly 1", "elementType": "assembly", "active": False},
        ]
        page = FakePage(
            tabs=tabs,
            panel_reads=[panel_found(empty_texts=["未检测到干涉"]), panel_not_found()],
            counts={
                selectors.ASM_INSERT_BUTTON: 1,
                **close_button_counts(),
            },
        )
        page.effects.append((selectors.TAB_BAR_TAB, page.activate_tab_effect))
        probe_reads = {"count": 0}

        original_next = page.next_panel_read

        def probe_after_switch():
            # After the switch the assembly tab is active.
            return dict(page.probe)

        result = check(page, tab_name="Assembly 1")
        self.assertEqual(result["verdict"], interference.VERDICT_CLEAN)
        activation = result["evidence"]["activation"]
        self.assertTrue(activation["switched"])
        self.assertEqual(activation["method"], "semantic._open_tab")
        self.assertTrue(activation["assemblyReadinessSignal"])
        self.assertEqual(result["tab_name"], "Assembly 1")

    def test_a_switch_that_fails_is_indeterminate_not_unavailable(self):
        tabs = [
            {"id": "e0", "name": "Part Studio 1", "elementType": "partstudio", "active": True},
            {"id": "e1", "name": "Assembly 1", "elementType": "assembly", "active": False},
        ]
        page = FakePage(tabs=tabs, tab_activates=False)
        page.substring_counts = [(selectors.TAB_BAR_TAB, 1)]
        page.counts = {selectors.ASM_INSERT_BUTTON: 0}
        result = check(page, tab_name="Assembly 1")
        self.assertEqual(result["verdict"], interference.VERDICT_INDETERMINATE)
        self.assertEqual(result["failureClass"], interference.FAILURE_TAB_SWITCH_FAILED)
        steps = [entry["step"] for entry in result["evidence"]["activation"]["attempts"]]
        self.assertEqual(steps, ["semantic._open_tab", "actions.activate_tab"])


# ---------------------------------------------------------------------------
# Pure helpers and the plan
# ---------------------------------------------------------------------------

class PureHelperTest(unittest.TestCase):
    def test_volume_parsing_reads_value_and_unit_and_nothing_when_absent(self):
        self.assertEqual(interference._parse_volume("x 1.5 mm^3 y")["value"], 1.5)
        self.assertEqual(interference._parse_volume("x 2 cm³")["unit"], "cm³")
        self.assertIsNone(interference._parse_volume("no numbers here"))

    def test_name_splitting_never_invents_names(self):
        self.assertTrue(interference.split_pair_names("Rotor ↔ Cage 0.5 mm³")["namesParsed"])
        unparsed = interference.split_pair_names("just one long row with no separator")
        self.assertFalse(unparsed["namesParsed"])
        self.assertEqual(unparsed["names"], [])
        self.assertEqual(interference.split_pair_names("A and B and C")["namesParsed"], False)

    def test_the_result_always_carries_the_contract_keys(self):
        page = FakePage(probe=partstudio_probe(), tabs=partstudio_tabs())
        result = check(page)
        for key in (
            "verdict",
            "pairs",
            "interference_count",
            "panel_available",
            "detection_completed",
            "tab_name",
            "evidence",
            "failures",
            "failureClass",
            "reason",
        ):
            self.assertIn(key, result)
        self.assertFalse(result["evidence"]["mutating"])
        self.assertEqual(result["evidence"]["apiRequests"], 0)
        self.assertTrue(result["evidence"]["readOnly"])

    def test_invalid_input_is_rejected_before_any_browser_work(self):
        page = FakePage()
        with self.assertRaises(ValueError):
            interference.browser_interference_check(page, part_names=["ok", ""])
        with self.assertRaises(ValueError):
            interference.browser_interference_check(page, tolerance_mm=0)
        with self.assertRaises(ValueError):
            interference.browser_interference_check(page, tolerance_mm="0.01")
        self.assertEqual(page.evaluate_calls, [])

    def test_the_module_imports_without_playwright(self):
        # Playwright is not installed in this virtual environment, so reaching this
        # line already proves the module has no top-level Playwright import.
        self.assertNotIn("playwright", sys.modules)


class PlanTest(unittest.TestCase):
    def test_a_plan_without_an_observation_admits_it_does_not_know(self):
        plan = interference.plan_interference_check(
            part_names=["Rotor"],
            tolerance_mm=0.05,
            include_zero_volume=True,
        )
        self.assertTrue(plan["dryRun"])
        self.assertFalse(plan["mutating"])
        self.assertEqual(plan["apiRequests"], 0)
        self.assertEqual(plan["operation"], interference.PLAN_OPERATION)
        self.assertIsNone(plan["preconditionsMet"])
        self.assertIsNone(plan["verdictIfRunNow"])
        self.assertTrue(all(item["met"] is None for item in plan["prerequisites"]))
        self.assertEqual(plan["inputs"]["toleranceMm"], 0.05)
        self.assertTrue(plan["inputs"]["includeZeroVolume"])
        self.assertTrue(plan["unverifiedSelectors"])
        self.assertIn("panelRoot", plan["unverifiedSelectors"])

    def test_a_plan_over_a_ready_assembly_met_its_preconditions(self):
        page = FakePage(
            probe=assembly_probe(analysisPopupItemTexts=["干涉检测…"], analysisPopup={"count": 1, "visible": True})
        )
        observation = interference.observe_interference_page(page)
        plan = interference.plan_interference_check(observation=observation)
        self.assertTrue(plan["preconditionsMet"])
        self.assertIsNone(plan["verdictIfRunNow"])
        self.assertTrue(plan["targetTab"]["resolved"])
        environment = next(item for item in plan["prerequisites"] if item["name"] == "target_tab_is_assembly")
        self.assertTrue(environment["met"])
        self.assertIn("assembly_tree_root", environment["evidence"]["signals"])

    def test_a_plan_over_a_part_studio_says_it_is_unavailable(self):
        page = FakePage(probe=partstudio_probe(), tabs=partstudio_tabs())
        observation = interference.observe_interference_page(page)
        plan = interference.plan_interference_check(observation=observation)
        self.assertFalse(plan["preconditionsMet"])
        self.assertEqual(plan["verdictIfRunNow"], interference.VERDICT_UNAVAILABLE)

    def test_a_plan_with_no_reachable_entry_is_indeterminate(self):
        page = FakePage(probe=assembly_probe())  # analysis button not visible, no entry text
        observation = interference.observe_interference_page(page)
        plan = interference.plan_interference_check(observation=observation)
        entry = next(item for item in plan["prerequisites"] if item["name"] == "interference_entry_available")
        self.assertFalse(entry["met"])
        self.assertEqual(plan["verdictIfRunNow"], interference.VERDICT_INDETERMINATE)

    def test_the_plan_names_the_unverified_selectors_and_the_clean_rule(self):
        plan = interference.plan_interference_check()
        self.assertTrue(plan["selectorProvenance"])
        for key in plan["unverifiedSelectors"]:
            self.assertEqual(plan["selectorProvenance"][key], "UNVERIFIED")
        self.assertIn("panel_available", plan["cleanIsOnlyAllowedWhen"])
        self.assertIn("detection_completed", plan["cleanIsOnlyAllowedWhen"])
        steps = " ".join(plan["intent"])
        self.assertIn("semantic._open_tab", steps)
        self.assertIn("no mate, constraint, fix, group or save", steps)

    def test_plan_input_validation(self):
        with self.assertRaises(ValueError):
            interference.plan_interference_check(part_names=("bad", 1))
        with self.assertRaises(ValueError):
            interference.plan_interference_check(tolerance_mm=-1)
        with self.assertRaises(ValueError):
            interference.plan_interference_check(tab_name=5)


if __name__ == "__main__":
    unittest.main()
