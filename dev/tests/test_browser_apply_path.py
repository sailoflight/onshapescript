#!/usr/bin/env python3
"""Offline tests for the Part Studio custom-feature apply path.

The apply path used to end in three fixed sleeps (3s, 10s, 15s): slow enough to
make a passing run feel broken, and still too short when a workbench regenerates
slowly. It now waits on bounded browser conditions and reports what it waited
for, and `inserted` means the feature actually appeared in the feature tree
rather than that a click landed.

Everything here is offline: a fake page records the waits and answers the
`evaluate` calls by intent. No browser, no session, no Onshape REST call.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from onshape_browser_mode import actions, interaction, semantic, selectors, transactions  # noqa: E402


class FakeClock:
    """A monotonic clock that advances only when the page is waited on.

    ``actions.wait_for_dialog_fields`` polls on real time, and the double's
    ``wait_for_timeout`` returns instantly, so an expression that never resolves
    would spin for the wait's whole budget in real seconds. Tying the clock to the
    waits keeps the loop's shape (poll, read, check, stop) while making it free.
    """

    def __init__(self, step_ms: int = 1000) -> None:
        self.now = 0.0
        self.step = step_ms / 1000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self) -> None:
        self.now += self.step


class FakeField:
    """One named control inside the parameter dialog.

    ``fill``/``is_checked``/``click`` write straight into the page's
    ``dialog_fields``, so the readback that ``fill_dialog_fields`` performs reads
    exactly what was typed — the same round trip the live dialog does.

    A live boolean parameter is TWO elements: the native
    ``<input type="checkbox" class="os-param-checkbox-input">`` that carries the
    parameter id but is measured NOT VISIBLE, and a visible styled ancestor that owns
    the click. ``visible=False`` plus ``wrapper`` models that pair, because the first
    implementation clicked the id-carrying input directly and timed out waiting for a
    hidden element.

    A text fill is modelled the way the live directive behaves: ``fill`` sets the text
    and records it as PENDING, and only ``blur`` commits it into ``dialog_fields``.
    That is the measured behaviour that made the last field of a dialog silently keep
    its default (see ``_commit_field``), so a fake that committed on ``fill`` would
    hide the very bug this double exists to catch.

    A key listed in the page's ``expression_keys`` is a QUANTITY widget: a ``#``
    value resolves asynchronously, so one read after the fill still shows the old
    text and the read after that shows what the widget settled on -- the typed
    expression, or the number it evaluates to when the page lists it in
    ``evaluated_expressions`` (both measured live 2026-09-21).
    ``expression_never_resolves`` models the case that never settles.
    """

    def __init__(self, page: "FakePage", key: str, *, visible: bool = True,
                 wrapper: "FakeField | None" = None) -> None:
        self.page = page
        self.key = key
        self.visible = visible
        self.wrapper = wrapper
        self.pending: str | None = None
        self.fill_calls: list[str] = []
        self.blur_calls: list[dict] = []
        self.click_calls: list[dict] = []
        self.press_calls: list[str] = []
        self.typed_calls: list[dict] = []

    def fill(self, value: str) -> None:
        self.fill_calls.append(str(value))
        self.pending = str(value)

    def blur(self, **kwargs) -> None:
        self.blur_calls.append(kwargs)
        if self.pending is None:
            return
        if self.key in self.page.expression_keys and "#" in self.pending:
            # An expression RESOLVES ASYNCHRONOUSLY: the widget will hold the typed
            # text, but the next read still shows the old one. Measured live
            # 2026-09-21, the read straight after the fill was the field's old
            # `0 mm` while the same dialog later read `#gf_pitch * 2` back exactly.
            self.page.pending_expressions[self.key] = self.pending
        else:
            self.page.dialog_fields[self.key] = self.pending
        self.pending = None

    def is_visible(self) -> bool:
        return self.visible

    def is_checked(self) -> bool:
        return str(self.page.dialog_fields.get(self.key, "")).lower() == "true"

    def click(self, **kwargs) -> None:
        self.click_calls.append(kwargs)
        if not self.visible:
            raise TimeoutError("element is not visible")
        # Only a checkbox toggles on click; a text/quantity field merely takes focus.
        if self.key in self.page.checkbox_keys:
            self.page.dialog_fields[self.key] = "false" if self.is_checked() else "true"

    def locator(self, selector: str) -> "FakeLocator":
        if self.wrapper is not None and selector.startswith("xpath="):
            return FakeLocator([self.wrapper], page=self.page, selector=selector)
        return FakeLocator([], page=self.page, selector=selector)


class FakeDialog:
    """The ``.feature-dialog`` element: resolves a parameter-id selector to one field."""

    FIELD_SELECTOR_KEY = re.compile(r'data-parameter-id="([^"]+)"')

    def __init__(self, page: "FakePage") -> None:
        self.page = page
        self.selector = selectors.PS_FEATURE_DIALOG

    def locator(self, selector: str) -> "FakeLocator":
        match = self.FIELD_SELECTOR_KEY.search(selector)
        key = match.group(1) if match else ""
        if key and key in self.page.dialog_fields:
            return FakeLocator([self.page.dialog_field(key)], page=self.page, selector=selector)
        return FakeLocator([], page=self.page, selector=selector)


class FakeItem:
    """One element: a menu row, a dialog button, or a feature-list row."""

    def __init__(self, text: str = "", *, visible: bool = True, page: "FakePage | None" = None,
                 selector: str = "", label: str = "") -> None:
        self.text = text
        self.visible = visible
        self.page = page
        self.selector = selector
        # A workspace row renders a two-letter Feature Studio badge before the
        # label, so its innerText is "Bf\nBounded fillet" while the NAME lives
        # in the `.tool-label` child. `label` models that child; "" models a row
        # with no label element, which is what the text fallback must handle.
        self.label = label
        self.click_calls: list[dict] = []
        self.wait_calls: list[dict] = []

    def is_visible(self) -> bool:
        return self.visible

    def inner_text(self) -> str:
        return self.text

    def locator(self, selector: str) -> "FakeLocator":
        if selector == selectors.CUSTOM_FEATURE_MENU_LABEL and self.label:
            return FakeLocator(
                [FakeItem(self.label, page=self.page, selector=selector)],
                page=self.page,
                selector=selector,
            )
        return FakeLocator([], page=self.page, selector=selector)

    def click(self, **kwargs) -> None:
        self.click_calls.append(kwargs)
        if self.page is not None and self.selector == selectors.CUSTOM_FEATURE_MENU_ITEM:
            # The dropdown click ALREADY adds the row (measured live 2026-09-20: a
            # row with an unaccepted dialog is real and even survives a reload), so
            # the row previews while its dialog is open. That is the state an
            # expression's resolve wait reads; without it the double would hide the
            # preview the wait exists for.
            self.page.features = self.page.inserted_features

    def wait_for(self, **kwargs) -> None:
        self.wait_calls.append(kwargs)
        if self.page is not None:
            self.page.waits.append({"selector": self.selector, **kwargs})
            if self.page.waits_fail_for and self.selector in self.page.waits_fail_for:
                raise TimeoutError(f"{self.selector} never reached state {kwargs.get('state')!r}")


class FakeLocator:
    def __init__(self, items: list[FakeItem], *, page: "FakePage", selector: str) -> None:
        self.items = items
        self.page = page
        self.selector = selector
        self.filter_text: str | None = None

    @property
    def first(self) -> FakeItem:
        return self.nth(0)

    def nth(self, index: int) -> FakeItem:
        if 0 <= index < len(self.items):
            return self.items[index]
        return FakeItem("", page=self.page, selector=self.selector)

    def filter(self, has_text: str = "") -> "FakeLocator":
        self.filter_text = has_text
        filtered = [
            item for item in self.items if str(has_text).lower() in item.text.lower()
        ]
        return FakeLocator(filtered, page=self.page, selector=self.selector)

    def locator(self, selector: str) -> "FakeLocator":
        """Resolve a selector relative to the element, as Playwright's locator does.

        The boolean click path walks up from the id-carrying input with
        ``locator("xpath=..")``, so the fake has to answer that relative query.
        """
        for item in self.items:
            found = getattr(item, "locator", lambda _selector: FakeLocator([], page=self.page, selector=_selector))(selector)
            if found.count():
                return found
        return FakeLocator([], page=self.page, selector=selector)

    def count(self) -> int:
        return len(self.items)


class FakePage:
    """A page that answers `evaluate` by intent and records bounded waits."""

    def __init__(self, *, menu_items=("Bc",), menu_labels=None, features=None, accept=True,
                 tabs=("Feature Studio 1", "Part Studio 1"), menu_opens=True,
                 features_before_insert=None, features_after_reload=None,
                 reload_fails=False, dialog_fields=None, checkbox_keys=(),
                 expression_keys=(), evaluated=None) -> None:
        self.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"
        # A key named here is a styled checkbox: its native input is not visible, and
        # the visible element that owns the click is an ancestor. Every other key is a
        # plainly visible text field.
        self.checkbox_keys = set(checkbox_keys)
        # A key named here is a quantity widget that a programmatic `fill` cannot
        # carry an expression into; see FakeField.
        self.expression_keys = set(expression_keys)
        # Filled expressions waiting for the widget to resolve them, and how many
        # times each has been read since.
        self.pending_expressions: dict[str, str] = {}
        self.expression_reads: dict[str, int] = {}
        # A widget that never resolves its reference, for the refusal paths.
        self.expression_never_resolves = False
        # Typed expression -> the readback a SETTLED widget renders. A quantity
        # widget resolves a `#variable` to its value, so a dimension reads back the
        # number while a Variable feature's own value field keeps the expression
        # (both measured live 2026-09-21).
        self.evaluated_expressions: dict[str, str] = dict(evaluated or {})
        labels = list(menu_labels) if menu_labels is not None else [""] * len(menu_items)
        self.menu_items = [
            FakeItem(text, page=self, selector=selectors.CUSTOM_FEATURE_MENU_ITEM,
                     label=labels[index])
            for index, text in enumerate(menu_items)
        ]
        # `features_before_insert` is the Part Studio BEFORE the click (the commit
        # baseline); `features` is the DOM after the accept click; a reload may
        # then reveal `features_after_reload`. Modelling the three separately is
        # what lets a test tell "the row this call created" from "a row that was
        # already there".
        self.features_before_insert = features_before_insert if features_before_insert is not None else {
            "headerText": "特征 (0)",
            "features": [],
            "partsText": "零件数 (0)",
        }
        self.inserted_features = features if features is not None else {
            "headerText": "特征",
            "features": [{"name": "Bc", "isUserFeature": True}],
            "partsText": "零件数 (1) Bc",
        }
        self.features = self.features_before_insert
        self.accept = accept
        self.tabs = [{"id": f"e{index}", "name": name, "active": index == 1}
                     for index, name in enumerate(tabs)]
        self.menu_opens = menu_opens
        self.waits_fail_for: set[str] = set()
        if not menu_opens:
            # "never opens" means a visibility wait on the dropdown times out.
            self.waits_fail_for.add(selectors.CUSTOM_FEATURE_MENU_ITEM)
        self.waits: list[dict] = []
        self.timeouts: list[int] = []
        self.evaluate_calls: list[str] = []
        self.accept_clicks: list[dict] = []
        # The parameter dialog's named fields, keyed by parameter id. Seeding it
        # with the values the dialog opens on is what makes the "before" read and
        # the readback after a fill both meaningful.
        self.dialog_fields: dict[str, str] = dict(dialog_fields or {})
        self.dialog_field_calls: list[FakeField] = []
        self.keyboard = mock.Mock()
        # The commit-verify reload: `features_after_reload` models the workspace
        # truth a reload reveals (None keeps the post-insert list), and
        # `reload_fails` models a navigation that never completes.
        self.features_after_reload = features_after_reload
        self.reload_fails = reload_fails
        self.reload_calls: list[dict] = []
        self.load_states: list[dict] = []
        self.wait_function_calls: list[dict] = []
        self.never_satisfied_minimum: int | None = None
        #: Whether the document shell has rendered after a reload. Live 2026-09-21 a
        #: reload fired straight after an accept left the tab strip and the Feature
        #: List unrendered for more than 30 s, so the double has to be able to model
        #: a shell that never comes up.
        self.document_ready = True
        self.clock = FakeClock()

    # -- reload surface (the commit-verify step) -------------------------
    def reload(self, **kwargs) -> None:
        self.reload_calls.append(kwargs)
        if self.reload_fails:
            raise RuntimeError("navigation interrupted")
        if self.features_after_reload is not None:
            self.features = self.features_after_reload

    def wait_for_load_state(self, state: str = "load", **kwargs) -> None:
        self.load_states.append({"state": state, **kwargs})

    # -- in-page count predicate -----------------------------------------
    def wait_for_function(
        self,
        expression: str,
        *,
        arg=None,
        timeout=None,
        polling=None,
    ) -> bool:
        """Mirror the real signature: Playwright makes ``arg`` keyword-only.

        Getting this wrong live is exactly how the first count-based wait
        shipped a ``TypeError`` (2026-09-20); the double must not be more
        permissive than the client it stands in for.
        """
        self.wait_function_calls.append(
            {
                "expression": expression,
                "arg": arg,
                "timeout": timeout,
                "polling": polling,
            }
        )
        if expression == actions._TAB_ACTIVE_PREDICATE:
            # The tab switch's verdict is that tab's own active class, for the exact
            # data-id — not a duration and not a position.
            wanted = str((arg or {}).get("id", ""))
            if any(tab.get("id") == wanted and tab.get("active") for tab in self.tabs):
                return True
            raise TimeoutError(f"tab {wanted!r} never became the active tab")
        if (arg or {}).get("selector") == selectors.DOCUMENT_TABS_BUTTON:
            # The document shell's readiness, which is its own gate and NOT a row
            # count: a slow boot must never be read as a missing feature.
            if self.document_ready:
                return True
            raise TimeoutError("the document shell never rendered")
        minimum = int((arg or {}).get("minimum", 1))
        # Two different in-page predicates reach this method, and the double
        # dispatches on the same thing the page does: which rows the JS counts.
        # `ns-user-feature` is the user-row count (regeneration, survival);
        # anything else is the panel-readiness row count, which includes the
        # default planes, the part list and the count markers.
        if "ns-user-feature" in expression:
            # ``never_satisfied_minimum`` models THE ROW COUNT never reaching N, so
            # it applies here and nowhere else: applying it to every wait would also
            # fail the shell gate and change which verdict a test is exercising.
            if (
                self.never_satisfied_minimum is not None
                and minimum >= self.never_satisfied_minimum
            ):
                raise TimeoutError(f"row count never reached {minimum}")
            wanted = str((arg or {}).get("text", "")).strip().lower()
            seen = self._matching_rows(wanted)
        else:
            seen = len(self.features.get("features", []))
        if seen >= minimum:
            return True
        raise TimeoutError(f"row count never reached {minimum}")

    def _matching_rows(self, wanted: str = "bc") -> int:
        """Matching user rows in the current list, mirroring the JS predicate."""
        rows = 0
        for item in self.features.get("features", []):
            if not item.get("isUserFeature"):
                continue
            text = str(item.get("name", "")).lower()
            if not wanted or wanted in text:
                rows += 1
        return rows

    def dialog_field(self, key: str) -> FakeField:
        """The control for one parameter id, in its live shape.

        A key listed in ``checkbox_keys`` comes back as the hidden id-carrying input
        with a visible wrapper, which is the ancestor the click path must walk up to.
        """
        field = FakeField(self, key, visible=key not in self.checkbox_keys)
        if not field.visible:
            field.wrapper = FakeField(self, key, visible=True)
        self.dialog_field_calls.append(field)
        return field

    def dialog_field_calls_for(self, key: str) -> list[FakeField]:
        return [field for field in self.dialog_field_calls if field.key == key]

    # -- locator surface -------------------------------------------------
    def locator(self, selector: str) -> FakeLocator:
        if selector == selectors.CUSTOM_FEATURE_MENU_ITEM and not self.menu_opens:
            return FakeLocator([], page=self, selector=selector)
        if selector == selectors.CUSTOM_FEATURE_MENU_ITEM:
            return FakeLocator(self.menu_items, page=self, selector=selector)
        if selector == selectors.PARTSTUDIO_FEATURE_ITEM:
            return FakeLocator(
                [FakeItem(str(row.get("name", "")), page=self, selector=selector)
                 for row in self.features.get("features", [])],
                page=self,
                selector=selector,
            )
        if selector == selectors.PS_FEATURE_DIALOG:
            return FakeLocator([FakeDialog(self)], page=self, selector=selector)
        return FakeLocator([], page=self, selector=selector)

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.timeouts.append(milliseconds)
        self.clock.advance()

    # -- evaluate surface ------------------------------------------------
    def evaluate(self, expression: str, *args):
        self.evaluate_calls.append(expression)
        if args:
            # dismiss_stale_context_menu
            return {"present": False, "blocking": False}
        if "workspace-custom-features button not found" in expression:
            return {"clicked": True}
        if ".feature-dialog" in expression:
            # The dialog read behind dialog_values / fill_dialog_fields. A pending
            # expression settles ONE read after it was filled, which is the measured
            # shape of the race the accept gate waits out.
            for key, value in list(self.pending_expressions.items()):
                self.expression_reads[key] = self.expression_reads.get(key, 0) + 1
                if self.expression_reads[key] >= 2 and not self.expression_never_resolves:
                    self.dialog_fields[key] = self.evaluated_expressions.get(value, value)
                    del self.pending_expressions[key]
                    self.expression_reads.pop(key, None)
            return dict(self.dialog_fields)
        if "accept button not found" in expression:
            self.accept_clicks.append({})
            if not self.accept:
                return {"clicked": False, "reason": "accept button not found"}
            # A landed accept makes the new row appear in the workbench DOM.
            self.features = self.inserted_features
            return {"clicked": True}
        if "ns-user-feature" in expression:
            return self.features
        if "os-tab-bar-tab" in expression:
            return {"tabs": self.tabs, "hasDocumentTabsToolButton": False}
        raise AssertionError(f"unexpected evaluate: {expression.strip()[:60]}")


class InsertCustomFeatureTest(unittest.TestCase):
    def apply(self, page: FakePage, **kwargs) -> dict:
        return actions.insert_custom_feature(page, kwargs.pop("feature_name", "Bc"), **kwargs)

    def test_apply_waits_on_conditions_instead_of_fixed_sleeps(self) -> None:
        page = FakePage()
        features_read = 0  # the default fake page starts with no custom features
        result = self.apply(page)
        self.assertTrue(result["inserted"])
        self.assertTrue(result["listed"])
        self.assertEqual(result["waits"]["menu"]["waited"], True)
        self.assertEqual(result["waits"]["dialog"]["waited"], True)
        self.assertEqual(result["waits"]["regeneration"]["waited"], True)
        # No blind sleep survives on the path.
        self.assertEqual(page.timeouts, [])
        # Each bounded wait uses a real selector from selectors.py.
        by_selector = {wait["selector"]: wait for wait in page.waits}
        self.assertEqual(
            set(by_selector),
            {selectors.CUSTOM_FEATURE_MENU_ITEM, selectors.FEATURE_DIALOG_OK},
        )
        self.assertEqual(
            by_selector[selectors.CUSTOM_FEATURE_MENU_ITEM]["timeout"],
            actions.CUSTOM_FEATURE_MENU_TIMEOUT_MS,
        )
        self.assertEqual(
            by_selector[selectors.FEATURE_DIALOG_OK]["timeout"],
            actions.FEATURE_DIALOG_TIMEOUT_MS,
        )
        self.assertEqual(len(page.accept_clicks), 1)
        # Three in-page waits, in this order: the regeneration count, the
        # document-shell gate the reload needs, then the survival count. The shell
        # gate sits between them because live 2026-09-21 a reload fired straight
        # after an accept left the Feature List unrendered for longer than the
        # survival budget, which counted 0 rows for a reason unrelated to the row.
        self.assertEqual(
            [call["arg"].get("selector") for call in page.wait_function_calls],
            [
                selectors.PARTSTUDIO_FEATURE_ITEM,
                selectors.DOCUMENT_TABS_BUTTON,
                selectors.PARTSTUDIO_FEATURE_ITEM,
            ],
        )
        # Both count waits ask for one row more than the baseline, each on its own
        # adaptive budget (the double reports one custom feature, so the budget is
        # base + 1 step); the shell gate is not a recompute and uses its own.
        self.assertEqual(
            [call["timeout"] for call in page.wait_function_calls],
            [
                actions.partstudio_wait_budget_ms(
                    actions.PARTSTUDIO_REGENERATE_WAIT, features_read
                ),
                actions.DOCUMENT_READY_TIMEOUT_MS,
                actions.partstudio_wait_budget_ms(
                    actions.PARTSTUDIO_RELOAD_WAIT, features_read
                ),
            ],
        )
        self.assertEqual(
            [
                call["arg"]["minimum"]
                for call in page.wait_function_calls
                if "minimum" in call["arg"]
            ],
            [1, 1],
        )
        self.assertEqual(result["baselineRows"], 0)
        self.assertEqual(
            result["budgets"],
            {
                "customFeaturesRead": features_read,
                "regenerationMs": page.wait_function_calls[0]["timeout"],
                "commitSurvivalMs": page.wait_function_calls[2]["timeout"],
            },
        )
        # And the insert is confirmed by exactly one bounded reload.
        self.assertEqual(
            page.reload_calls, [{"wait_until": "commit", "timeout": 15000}]
        )
        self.assertEqual(
            page.load_states, [{"state": "domcontentloaded", "timeout": 15000}]
        )

    def test_parameters_fill_the_dialog_before_it_is_accepted(self) -> None:
        """A thin row IS a few numbers, so ONE call must create it carrying them.

        Insert-then-edit would be two browser transactions per row and would leave
        the row committed with the dialog's defaults in between.
        """
        page = FakePage(dialog_fields={"width": "100 mm", "corner_radius": "0 mm"})
        result = self.apply(page, parameters={"width": "84 mm", "corner_radius": "4 mm"})
        self.assertTrue(result["inserted"])
        self.assertEqual(page.dialog_fields, {"width": "84 mm", "corner_radius": "4 mm"})
        self.assertEqual(
            result["parameters"]["before"], {"width": "100 mm", "corner_radius": "0 mm"}
        )
        self.assertEqual(result["parameters"]["updated"], ["width", "corner_radius"])
        self.assertEqual(result["parameters"]["missing"], [])
        self.assertTrue(result["parameters"]["readbackOk"])
        self.assertEqual(len(page.accept_clicks), 1)

    def test_a_parameter_the_dialog_does_not_expose_refuses_the_insert(self) -> None:
        page = FakePage(dialog_fields={"width": "100 mm"})
        result = self.apply(page, parameters={"width": "84 mm", "nope": "1 mm"})
        self.assertFalse(result["inserted"])
        self.assertEqual(result["parameters"]["missing"], ["nope"])
        # The dialog is left unaccepted, so no default-valued row is committed and
        # the failure is diagnosable from the missing id alone.
        self.assertEqual(page.accept_clicks, [])
        self.assertIn("not filled exactly", result["reason"])

    def test_every_filled_field_is_committed_before_the_dialog_is_accepted(self) -> None:
        """A text fill must fire the change event the live dialog needs.

        ``Locator.fill`` focuses the field, sets the text, and fires ``input``; the
        browser fires ``change`` only when the element loses focus, and Onshape's
        parameter directive commits on ``change``. The last field filled in a dialog
        was therefore the one field that never reached the model. Measured live
        2026-09-21: ``corner_radius`` and ``draft_angle`` read back as 4 mm and 45 deg
        in the dialog and were stored as 0 mm and 0 deg, which built a plate with
        sharp corners and a socket whose 45 deg ramps had no taper at all.
        """
        page = FakePage(dialog_fields={"width": "100 mm", "corner_radius": "0 mm"})
        result = self.apply(page, parameters={"width": "84 mm", "corner_radius": "4 mm"})
        self.assertTrue(result["inserted"])
        self.assertEqual(result["parameters"]["committed"], ["width", "corner_radius"])
        self.assertEqual(result["parameters"]["uncommitted"], [])
        self.assertEqual(page.dialog_fields["corner_radius"], "4 mm")
        self.assertEqual(
            len(page.dialog_field_calls_for("corner_radius")[0].blur_calls), 1
        )

    def test_a_field_that_cannot_be_committed_refuses_the_insert(self) -> None:
        """A pending fill is not evidence: an uncommittable field is a refusal."""
        page = FakePage(dialog_fields={"width": "100 mm"})
        with mock.patch.object(actions, "_commit_field", return_value=False):
            result = self.apply(page, parameters={"width": "84 mm"})
        self.assertFalse(result["inserted"])
        self.assertEqual(result["parameters"]["uncommitted"], ["width"])
        self.assertEqual(page.accept_clicks, [])

    def test_an_expression_is_waited_for_until_the_dialog_reads_it_back(self) -> None:
        """The accept gate is the dialog's own readback, taken after a bounded wait.

        Measured live 2026-09-21: filling `#gf_pitch * 2` into a thin Variable row's
        Value field read back `0 mm` -- the field's own default, silently -- while
        the SAME dialog read the typed expression back verbatim once the widget had
        resolved it (~1.5 s later), and accepting before that stored the `0 mm` as
        the variable's value. So the read that decides is the one taken after the
        wait, and it is not exempt from anything: the wait's verdict IS the fill's
        verdict.
        """
        after = {
            "headerText": "特征 (3)",
            "features": [
                {"name": "TV #gf_pitch = 42 mm", "isUserFeature": True},
                {"name": "TV #gf_plate_size = 84 mm", "isUserFeature": True},
            ],
            "partsText": "零件数 (0)",
        }
        before = {
            "headerText": "特征 (2)",
            "features": [{"name": "TV #gf_pitch = 42 mm", "isUserFeature": True}],
            "partsText": "零件数 (0)",
        }
        page = FakePage(
            menu_items=("Thin Variable",),
            dialog_fields={"name": "", "value": "0 mm", "description": ""},
            expression_keys={"value"},
            evaluated={"#gf_pitch * 2": "84 mm"},
            features_before_insert=before,
            features=after,
            features_after_reload=after,
        )
        result = self.apply(
            page,
            feature_name="Thin Variable",
            parameters={
                "name": "gf_plate_size",
                "value": "#gf_pitch * 2",
                "description": "2x2 plate outline",
            },
            expect_row="#gf_plate_size = 84 mm",
            expect_values={"value": "84 mm"},
        )
        self.assertTrue(result["inserted"])
        self.assertEqual(result["expressionFields"], ["value"])
        self.assertTrue(result["rowVerified"])
        self.assertEqual(result["createdRows"],
                         [{"name": "TV #gf_plate_size = 84 mm", "hasError": False}])
        # The fill's own read was the stale one; the resolve wait replaced it with the
        # value the expression evaluates to, which is the only signal it accepts.
        self.assertTrue(result["parameters"]["readbackOk"])
        self.assertTrue(result["parameters"]["resolved"])
        self.assertEqual(result["parameters"]["after"]["value"], "84 mm")
        self.assertEqual(result["expectValues"], {"value": "84 mm"})
        self.assertEqual(result["parameters"]["mismatched"], [])
        self.assertEqual(result["parameters"]["committed"],
                         ["name", "value", "description"])
        self.assertEqual(len(page.accept_clicks), 1)
        # The wait settles on its first read, so it costs no poll at all.
        self.assertTrue(result["waits"]["expressionResolve"]["waited"])
        self.assertEqual(result["waits"]["expressionResolve"]["condition"],
                         "dialog_fields_readback")
        self.assertEqual(result["waits"]["expressionResolve"]["keys"], ["value"])
        self.assertEqual(result["waits"]["expressionResolve"]["elapsedMs"], 0)
        self.assertEqual(page.timeouts, [])

    def test_a_resolving_expression_needs_a_stated_value_but_no_expect_row(self) -> None:
        """The dialog's own readback confirms it, which every thin row can do.

        A row whose feature has no `Feature Name Template` displays no numbers at
        all, so requiring a row expectation would make such a step unbuildable; the
        dialog always can confirm -- but only against the value the expression
        evaluates to, never against the text that was typed into it.
        """
        page = FakePage(
            menu_items=("Thin Sketch Rectangle",),
            dialog_fields={"width": "0 mm"},
            expression_keys={"width"},
            evaluated={"#gf_plate_size": "84 mm"},
        )
        result = self.apply(
            page, feature_name="Thin Sketch Rectangle",
            parameters={"width": "#gf_plate_size"},
            expect_values={"width": "84 mm"},
        )
        self.assertTrue(result["inserted"])
        self.assertEqual(result["expressionFields"], ["width"])
        self.assertEqual(result["expectRow"], "")
        self.assertTrue(result["parameters"]["readbackOk"])
        self.assertEqual(result["parameters"]["after"]["width"], "84 mm")
        self.assertEqual(len(page.accept_clicks), 1)

    def test_an_expression_without_a_stated_value_refuses_before_accepting(self) -> None:
        """An expression cannot be confirmed by its own text, so such a step refuses.

        Measured live 2026-09-21: the widget shows the typed text for a moment and the
        accept that follows commits the field's PREVIOUS value, so the dialog is left
        unaccepted and the refusal says what is missing.
        """
        page = FakePage(
            menu_items=("Thin Variable",),
            dialog_fields={"value": "0 mm"},
            expression_keys={"value"},
        )
        page.expression_never_resolves = True
        with mock.patch.object(actions.time, "monotonic", page.clock.monotonic):
            result = self.apply(
                page, feature_name="Thin Variable", parameters={"value": "#a * 2"}
            )
        self.assertFalse(result["inserted"])
        self.assertEqual(page.accept_clicks, [])
        self.assertIn("expect_values", result["reason"])
        self.assertEqual(result["expressionFields"], ["value"])
        self.assertEqual(result["parameters"]["mismatched"], ["value"])
        self.assertFalse(result["wait"]["waited"], "the field was never confirmed")
        self.assertEqual(result["wait"]["condition"], "unstated_expression")
        self.assertEqual(page.timeouts, [], "it refuses instead of spending the budget")

    def test_a_row_without_the_expected_text_is_not_an_insert(self) -> None:
        """Accepting is not enough: the row must state the value that was asked for.

        A resolved dialog is not a promise about the model's evaluation, so the row
        the model wrote is checked as well and a row stating another value is a real,
        default-valued row that must be deleted.
        """
        after = {
            "headerText": "特征 (1)",
            "features": [{"name": "TV #gf_plate_size = 0 mm", "isUserFeature": True}],
            "partsText": "",
        }
        page = FakePage(
            menu_items=("Thin Variable",),
            dialog_fields={"name": "", "value": "0 mm"},
            expression_keys={"value"},
            evaluated={"#gf_pitch * 2": "84 mm"},
            features=after,
            features_after_reload=after,
        )
        result = self.apply(
            page,
            feature_name="Thin Variable",
            parameters={"name": "gf_plate_size", "value": "#gf_pitch * 2"},
            expect_row="#gf_plate_size = 84 mm",
            expect_values={"value": "84 mm"},
        )
        self.assertFalse(result["inserted"])
        self.assertTrue(result["commit"]["committed"])
        self.assertTrue(result["waits"]["expressionResolve"]["waited"],
                        "the dialog did read the resolved value back")
        self.assertFalse(result["rowVerified"])
        self.assertIn("must be deleted", result["reason"])
        self.assertIn("0 mm", result["reason"])

    def test_the_commit_reload_can_be_skipped_without_claiming_success(self) -> None:
        """A step whose confirmation outlives the transport returns no verdict.

        Both waits are skipped, not just the reload. The regeneration wait's budget
        scales with the element (30 s plus 2 s per custom feature), so on a large tree
        it is itself longer than one call's transport budget: measured live 2026-09-21,
        three short-path attempts at one heavy cut returned NOTHING, because the call
        was cut off before it could return from the accept it had already clicked. The
        short path therefore returns as soon as the accept landed and reports
        `inserted: None` with `applyState: pending_verification`, so the caller confirms
        the row itself instead of reading a false success or learning nothing.
        """
        page = FakePage()
        result = self.apply(page, verify_commit=False)
        self.assertIsNone(result["inserted"])
        self.assertEqual(result["applyState"], "pending_verification")
        self.assertFalse(result["verifyCommit"])
        self.assertTrue(result["accepted"]["clicked"])
        self.assertEqual(page.reload_calls, [], "the confirming reload was skipped")
        self.assertEqual(
            page.wait_function_calls, [], "the regeneration wait was skipped too"
        )
        self.assertTrue(result["waits"]["regeneration"]["skipped"])
        self.assertEqual(result["waits"]["regeneration"]["minimum"], 1)
        self.assertTrue(result["commit"]["skipped"])
        self.assertFalse(result["commit"]["verified"])
        self.assertIsNone(result["commit"]["committed"])
        self.assertIn("confirm the new row", result["reason"])
        # The read taken after the accept is still reported, as evidence only.
        self.assertTrue(result["workbenchAppeared"])

    def test_the_short_path_still_refuses_a_fill_that_did_not_land(self) -> None:
        """Skipping the confirmation must not soften the fill verdict."""
        page = FakePage(dialog_fields={"value": "0 mm"})
        with mock.patch.object(actions, "dialog_values",
                               return_value={"value": "0 mm"}):
            result = self.apply(
                page, parameters={"value": "42 mm"}, verify_commit=False
            )
        self.assertFalse(result["inserted"])
        self.assertEqual(result["applyState"], "not_inserted")
        self.assertEqual(page.accept_clicks, [])
        self.assertIn("not filled exactly", result["reason"])

    def test_a_skipped_call_reports_an_accept_that_did_not_land_as_failure(self) -> None:
        """Only an accept that landed is `unknown`; a missing one is a failure."""
        page = FakePage(accept=False)
        result = self.apply(page, verify_commit=False)
        self.assertFalse(result["inserted"], "a missing accept is not unknown")
        self.assertEqual(result["applyState"], "not_inserted")
        self.assertFalse(result["accepted"]["clicked"])

    def test_a_plain_field_that_does_not_read_back_still_refuses(self) -> None:
        """The expression exemption must not become a general exemption.

        A stale read is modelled directly: the dialog is filled and the blur fires
        (so the field is ``committed``) while the read still shows the old text. Only
        a field holding an expression is allowed to disagree with its readback.
        """
        page = FakePage(dialog_fields={"value": "0 mm"})
        with mock.patch.object(actions, "dialog_values",
                               return_value={"value": "0 mm"}):
            result = self.apply(page, parameters={"value": "42 mm"})
        self.assertFalse(result["inserted"])
        self.assertEqual(page.accept_clicks, [])
        self.assertIn("not filled exactly", result["reason"])
        self.assertEqual(result["expressionFields"], [])
        self.assertEqual(result["parameters"]["mismatched"], ["value"])
        self.assertEqual(result["parameters"]["committed"], ["value"])

    def test_expect_row_is_checked_whenever_it_is_given(self) -> None:
        """`expect_row` describes the ROW, so it does not depend on the fill.

        A parameterless step still creates a row, and a caller that states what that
        row must say gets the check rather than a silent pass.
        """
        row = {
            "headerText": "特征 (1)",
            "features": [{"name": "TV #gf_x = 1 mm", "isUserFeature": True}],
            "partsText": "",
        }
        page = FakePage(features=row, features_after_reload=row)
        result = self.apply(page, expect_row="#gf_x = 2 mm")
        self.assertFalse(result["inserted"])
        self.assertFalse(result["rowVerified"])
        self.assertIn("must be deleted", result["reason"])

        matching = self.apply(
            FakePage(features=row, features_after_reload=row),
            expect_row="#gf_x = 1 mm",
        )
        self.assertTrue(matching["inserted"])
        self.assertTrue(matching["rowVerified"])

    def test_a_boolean_parameter_is_set_through_the_checkbox(self) -> None:
        page = FakePage(
            dialog_fields={"draft_inwards": "false", "depth": "10 mm"},
            checkbox_keys={"draft_inwards"},
        )
        result = self.apply(page, parameters={"draft_inwards": True, "depth": "0.7 mm"})
        self.assertTrue(result["inserted"])
        self.assertEqual(page.dialog_fields["draft_inwards"], "true")
        self.assertEqual(result["parameters"]["desired"]["draft_inwards"], "true")
        # The id-carrying input is not visible, so the click must land on the visible
        # ancestor. Clicking the input is what timed out live (30 s waiting for an
        # element measured "not visible" on every retry).
        hidden = page.dialog_field_calls_for("draft_inwards")[0]
        self.assertFalse(hidden.is_visible())
        self.assertEqual(hidden.click_calls, [])
        self.assertTrue(hidden.wrapper.click_calls)

    def test_the_edit_transaction_calls_the_shared_fill(self) -> None:
        """One implementation of "which control carries this parameter id".

        The selector table now lives once, in actions.py, so a field the insert
        path can fill is a field the edit path can fill.
        """
        page = FakePage(dialog_fields={"width": "84 mm"})
        self.assertEqual(transactions._dialog_values(page), {"width": "84 mm"})
        self.assertEqual(transactions._dialog_values(page), actions.dialog_values(page))
        source = (ROOT / "onshape_browser_mode" / "transactions.py").read_text(encoding="utf-8")
        self.assertIn("actions.fill_dialog_fields(", source)
        self.assertIn("actions.dialog_values(", source)
        self.assertNotIn("data-parameter-id=", source)

    def test_the_wait_budgets_grow_with_the_custom_feature_count(self) -> None:
        """A bigger element needs a bigger post-insert budget.

        The live measurement (5 custom features, 18 431 ms of a fixed 30 000 ms
        budget) is the reason: the same reload on a Part Studio with 40 custom
        features spends far more, and a fixed budget would call a committed
        feature missing.
        """
        many = [
            {"name": f"Sr Spiral ridge {index}", "isUserFeature": True}
            for index in range(1, 41)
        ]
        before = {
            "headerText": "特征 (45)",
            "features": many + [{"name": "Origin", "isUserFeature": False}],
            "partsText": "零件数 (40)",
        }
        # The tree KEEPS its rows: the post-accept list is the 40 existing rows plus
        # the new one, which is why the count gate is baseline + 1 rather than 1.
        after = {
            "headerText": "特征 (46)",
            "features": many + [{"name": "Bc", "isUserFeature": True}],
            "partsText": "零件数 (41)",
        }
        page = FakePage(
            features_before_insert=before, features=after, features_after_reload=after
        )
        result = self.apply(page)
        self.assertTrue(result["inserted"])
        self.assertEqual(result["budgets"]["customFeaturesRead"], 40)
        self.assertEqual(result["budgets"]["regenerationMs"], 110_000)
        self.assertEqual(result["budgets"]["commitSurvivalMs"], 350_000)
        self.assertEqual(
            [call["timeout"] for call in page.wait_function_calls],
            [
                result["budgets"]["regenerationMs"],
                actions.DOCUMENT_READY_TIMEOUT_MS,
                result["budgets"]["commitSurvivalMs"],
            ],
        )

    def test_an_unreadable_feature_count_keeps_the_previous_fixed_budget(self) -> None:
        """A read taken mid-render must not shorten either wait."""
        page = FakePage(
            features_before_insert={"headerText": "", "features": None, "partsText": ""}
        )
        result = self.apply(page)
        self.assertTrue(result["inserted"])
        self.assertEqual(result["budgets"]["customFeaturesRead"], 0)
        for key in ("regenerationMs", "commitSurvivalMs"):
            self.assertEqual(
                result["budgets"][key], actions.PARTSTUDIO_RELOAD_TIMEOUT_MS
            )

    def test_all_waits_are_longer_than_the_sleeps_they_replaced(self) -> None:
        self.assertGreater(actions.CUSTOM_FEATURE_MENU_TIMEOUT_MS, 3_000)
        self.assertGreater(actions.FEATURE_DIALOG_TIMEOUT_MS, 10_000)
        # A budget with no feature count is the previous fixed budget, so the
        # adaptive change can never shorten a wait.
        for profile in (actions.PARTSTUDIO_REGENERATE_WAIT, actions.PARTSTUDIO_RELOAD_WAIT):
            self.assertGreater(actions.partstudio_wait_budget_ms(profile, 0), 15_000)
            self.assertEqual(
                actions.partstudio_wait_budget_ms(profile, 0),
                actions.PARTSTUDIO_RELOAD_TIMEOUT_MS,
            )

    def test_dropdown_that_never_opens_is_an_explicit_non_success(self) -> None:
        page = FakePage(menu_opens=False)
        result = self.apply(page)
        self.assertFalse(result["inserted"])
        self.assertIn("did not open", result["reason"])
        self.assertNotIn("waits", result)
        self.assertFalse(result["menu"]["waited"])
        # Nothing was clicked inside a dropdown that never appeared.
        self.assertEqual([item.click_calls for item in page.menu_items], [[]])
        self.assertEqual(page.accept_clicks, [])

    def test_feature_name_must_match_exactly_one_menu_item(self) -> None:
        for items, expected in ((("Bc", "Bc"), "exactly one"), (("Other",), "exactly one")):
            page = FakePage(menu_items=items)
            result = self.apply(page)
            self.assertFalse(result["inserted"])
            self.assertIn(expected, result["reason"])
            self.assertEqual(page.accept_clicks, [])

    def test_a_rejected_accept_is_never_reported_as_inserted(self) -> None:
        page = FakePage(accept=False)
        result = self.apply(page)
        self.assertFalse(result["inserted"])
        self.assertFalse(result["accepted"]["clicked"])
        # An accept that did not land still leaves the row the dropdown click added
        # (measured live 2026-09-20: an unaccepted row is real and survives a reload),
        # so `listed` reports it -- which is exactly why `listed` alone is not the
        # verdict and `inserted` is.
        self.assertTrue(result["listed"])
        self.assertIn("accept click did not land", result["reason"])

    def test_row_badge_does_not_hide_the_feature_name(self) -> None:
        """A live row's innerText is "Bf\\nBounded fillet", not the name.

        Measured 2026-09-19: `<div class="tool-initials-icon">Bf</div>` precedes
        `<span class="tool-label">Bounded fillet</span>`, so exact equality
        against the row text never matched a real workspace feature.
        """
        page = FakePage(
            menu_items=("Bf\nBounded fillet",),
            menu_labels=("Bounded fillet",),
            features={
                "headerText": "特征",
                "features": [{"name": "Bf Bounded fillet 1", "isUserFeature": True, "hasError": False}],
                "partsText": "零件数 (1) Spiral ridge cylinder",
            },
        )
        result = actions.insert_custom_feature(page, "Bounded fillet")
        self.assertTrue(result["inserted"])
        self.assertEqual(len(page.menu_items[0].click_calls), 1)
        self.assertEqual(page.accept_clicks, [{}])

    def test_a_row_without_a_label_element_falls_back_to_its_last_line(self) -> None:
        page = FakePage(
            menu_items=("Sr\nSpiral ridge",),
            features={
                "headerText": "特征",
                "features": [{"name": "Sr Spiral ridge 1", "isUserFeature": True, "hasError": False}],
                "partsText": "零件数 (1) Spiral ridge cylinder",
            },
        )
        result = actions.insert_custom_feature(page, "Spiral ridge")
        self.assertTrue(result["inserted"])
        self.assertEqual(len(page.menu_items[0].click_calls), 1)

    def test_a_non_match_reports_the_labels_that_were_available(self) -> None:
        page = FakePage(
            menu_items=("Bf\nBounded fillet", "Bh\nBounded hole"),
            menu_labels=("Bounded fillet", "Bounded hole"),
        )
        result = self.apply(page, feature_name="Bounded chamfer")
        self.assertFalse(result["inserted"])
        self.assertIn("exactly one", result["reason"])
        self.assertEqual(result["available"], ["Bounded fillet", "Bounded hole"])
        self.assertEqual(page.accept_clicks, [])

    def test_two_rows_sharing_a_label_are_never_guessed(self) -> None:
        page = FakePage(
            menu_items=("Bf\nBounded fillet", "Bf\nBounded fillet"),
            menu_labels=("Bounded fillet", "Bounded fillet"),
        )
        result = actions.insert_custom_feature(page, "Bounded fillet")
        self.assertFalse(result["inserted"])
        self.assertIn("exactly one", result["reason"])
        self.assertEqual([item.click_calls for item in page.menu_items], [[], []])
        self.assertEqual(page.accept_clicks, [])

    def test_a_feature_that_never_regenerates_is_reported_as_not_listed(self) -> None:
        page = FakePage(features={"headerText": "", "features": [], "partsText": ""})
        page.never_satisfied_minimum = 1
        result = self.apply(page)
        self.assertFalse(result["inserted"])
        self.assertFalse(result["listed"])
        self.assertFalse(result["waits"]["regeneration"]["waited"])
        self.assertEqual(result["waits"]["regeneration"]["condition"],
                         "user_feature_row_count")
        self.assertTrue(result["accepted"]["clicked"])

    def test_part_studio_tab_must_exist(self) -> None:
        page = FakePage(tabs=("Feature Studio 1",))
        result = self.apply(page, part_studio_tab="Part Studio 9")
        self.assertFalse(result["inserted"])
        self.assertIn("not found", result["reason"])

    def test_tab_switch_waits_for_the_feature_panel(self) -> None:
        page = FakePage()
        result = self.apply(page, part_studio_tab="Part Studio 1")
        self.assertTrue(result["inserted"])
        self.assertIn(".features-title", [wait["selector"] for wait in page.waits])
        # The switch also waits for the rows and the toolbar button before using
        # either: live 2026-09-20 a switched-to Part Studio produced a
        # "workspace-custom-features button not found" click and a baseline read
        # of 0 rows on an element holding 8 custom features.
        self.assertEqual(result["panelReady"]["condition"], "partstudio_row_count")
        self.assertTrue(result["toolbarReady"]["waited"])
        self.assertTrue(result["toolbarReady"]["selector"].startswith(".tool[title="))

    def test_a_panel_that_rendered_its_rows_is_read_as_the_baseline(self) -> None:
        before = {
            "headerText": "特征 (3)",
            "features": [
                {"name": "默认几何图元", "isUserFeature": False},
                {"name": "Bc 1", "isUserFeature": True},
                {"name": "Bc 2", "isUserFeature": True},
            ],
            "partsText": "零件数 (2)",
        }
        after = {
            "headerText": "特征 (4)",
            "features": [
                {"name": "默认几何图元", "isUserFeature": False},
                {"name": "Bc 1", "isUserFeature": True},
                {"name": "Bc 2", "isUserFeature": True},
                {"name": "Bc 3", "isUserFeature": True},
            ],
            "partsText": "零件数 (3)",
        }
        page = FakePage(
            features_before_insert=before, features=after, features_after_reload=after
        )
        result = self.apply(page, part_studio_tab="Part Studio 1")
        self.assertTrue(result["panelReady"]["waited"])
        self.assertEqual(result["panelReady"]["minimum"], 1)
        # The baseline is the count read AFTER the readiness wait, not a zero.
        self.assertEqual(result["baselineRows"], 2)
        self.assertEqual(result["budgets"]["customFeaturesRead"], 2)
        self.assertEqual(
            [call["arg"]["minimum"] for call in page.wait_function_calls
             if "ns-user-feature" in call["expression"]],
            [3, 3],
        )

    def test_a_panel_that_never_renders_rows_is_reported_not_guessed(self) -> None:
        page = FakePage(
            features_before_insert={"headerText": "", "features": [], "partsText": ""}
        )
        result = self.apply(page, part_studio_tab="Part Studio 1")
        self.assertFalse(result["panelReady"]["waited"])
        self.assertIn("TimeoutError", result["panelReady"]["error"])
        # Readiness is evidence, not a gate: the rest of the transaction ran and
        # the commit check still decided the result.
        self.assertTrue(result["inserted"])
        self.assertTrue(result["commit"]["committed"])

    def test_without_a_tab_switch_no_readiness_wait_is_spent(self) -> None:
        page = FakePage()
        result = self.apply(page)
        self.assertIsNone(result["panelReady"])
        self.assertIsNone(result["toolbarReady"])
        self.assertEqual(
            len([call for call in page.wait_function_calls
                 if "ns-user-feature" in call["expression"]]),
            2,
            "only the regeneration and survival waits",
        )


class AdaptiveWaitBudgetTest(unittest.TestCase):
    """The post-insert budgets scale with the element's recompute load."""

    def test_a_zero_or_unreadable_count_reproduces_the_previous_budget(self) -> None:
        for profile in (actions.PARTSTUDIO_REGENERATE_WAIT, actions.PARTSTUDIO_RELOAD_WAIT):
            for count in (0, None, "nope", -5, []):
                with self.subTest(profile=profile["baseMs"], count=count):
                    self.assertEqual(
                        actions.partstudio_wait_budget_ms(profile, count),
                        actions.PARTSTUDIO_RELOAD_TIMEOUT_MS,
                    )

    def test_the_budget_is_linear_then_capped(self) -> None:
        profile = actions.PARTSTUDIO_RELOAD_WAIT
        self.assertEqual(actions.partstudio_wait_budget_ms(profile, 1), 38_000)
        self.assertEqual(actions.partstudio_wait_budget_ms(profile, 10), 110_000)
        self.assertEqual(
            actions.partstudio_wait_budget_ms(profile, 1_000_000), profile["maxMs"]
        )
        self.assertEqual(actions.partstudio_wait_budget_ms(profile, "7"), 86_000)

    def test_the_measured_live_case_now_has_a_real_margin(self) -> None:
        # The live survival wait needed 18 431 ms of the old fixed 30 000 ms
        # budget on 5 custom features; the scaled budget must be well clear of it.
        budget = actions.partstudio_wait_budget_ms(actions.PARTSTUDIO_RELOAD_WAIT, 5)
        self.assertGreaterEqual(budget, 18_431 * 2)

    def test_count_custom_features_ignores_parts_defaults_and_garbage(self) -> None:
        features = {
            "features": [
                {"name": "默认几何图元", "isUserFeature": False},
                {"name": "Sr Spiral ridge 1", "isUserFeature": True},
                {"name": "Sr Spiral ridge 2", "isUserFeature": True},
                {"name": "零件数 (2)", "isUserFeature": False},
                {"name": "Spiral ridge cylinder", "isUserFeature": False},
                {"name": "曲线数 (2)", "isUserFeature": False},
            ]
        }
        self.assertEqual(actions.count_custom_features(features), 2)
        self.assertEqual(actions.count_custom_features({"features": None}), 0)
        self.assertEqual(actions.count_custom_features(None), 0)
        self.assertEqual(actions.count_custom_features({"features": ["nope", 5]}), 0)


class InsertCommitVerificationTest(unittest.TestCase):
    """``inserted`` means the workspace KEPT the feature, not that a row showed.

    Measured 2026-09-20: a browser-inserted custom feature is absent from the
    element's REST feature list until the page is reloaded, while a REST-added
    feature appears immediately. A visible row is therefore not a commit, and the
    confirming reload is what separates the two. Evidence:
    ``onshape_docs/verification/browser-rest-handoff-2026-09-20.json``.

    Both waits compare a row COUNT against the pre-click baseline, because the
    same day's live run showed the name-only forms failing in both directions: a
    Part Studio that already held two `Spiral ridge` rows satisfied the old
    regeneration wait in 12 ms (false success), and a read taken right after the
    reload saw the title before the rows (false failure, on an insert that had in
    fact committed).
    """

    def test_the_post_reload_read_is_what_the_result_reports(self) -> None:
        after = {
            "headerText": "特征 (1)",
            "features": [{"name": "Bc 1", "isUserFeature": True, "hasError": False}],
            "partsText": "零件数 (1) Bc",
        }
        page = FakePage(features_after_reload=after)
        result = actions.insert_custom_feature(page, "Bc")
        self.assertIs(result["features"], after)
        self.assertTrue(result["commit"]["verified"])
        self.assertTrue(result["commit"]["committed"])
        self.assertTrue(result["inserted"])
        self.assertNotIn("reason", result)

    def test_a_same_named_row_that_was_already_there_is_not_the_new_feature(self) -> None:
        """The live false-success: two existing rows satisfied a name-only wait.

        The Part Studio already showed `Bc 1` and `Bc 2`; the accept lands but the
        workspace keeps nothing, so the row count stays at the baseline of two. A
        name-matching wait would have been satisfied instantly by the OLD rows, so
        the check counts rows instead: the reload brings back only the two that were
        already there, and the insert is not reported.
        """
        existing = {
            "headerText": "特征 (7)",
            "features": [
                {"name": "Bc 1", "isUserFeature": True, "hasError": False},
                {"name": "Bc 2", "isUserFeature": True, "hasError": False},
            ],
            "partsText": "零件数 (2) Bc Bc",
        }
        page = FakePage(
            features_before_insert=existing,
            features=existing,
            features_after_reload=existing,
        )
        page.never_satisfied_minimum = 3
        result = actions.insert_custom_feature(page, "Bc")
        self.assertEqual(result["baselineRows"], 2)
        self.assertFalse(result["inserted"])
        self.assertFalse(result["commit"]["committed"])
        self.assertTrue(result["commit"]["verified"])
        self.assertIn("never settled", result["reason"])
        # Nothing new is in the reloaded list either, so no row is claimed as created.
        self.assertEqual(result["createdRows"], [])
        self.assertFalse(result["commit"]["createdRows"])

    def test_a_template_named_row_is_a_commit_even_though_its_name_never_matches(
        self,
    ) -> None:
        """The live false-failure: a Feature Name Template hides the type name.

        Measured 2026-09-21, a `Thin Variable` row reads `TV #gf_probe = 42 mm`, so
        a gate that looks for "Thin Variable" times out after the whole survival
        budget on a row that is really there. Counting rows and subtracting the
        pre-insert names is the same check with the blind spot removed.
        """
        before = {
            "headerText": "特征 (0)",
            "features": [],
            "partsText": "零件数 (0)",
        }
        after = {
            "headerText": "特征 (1)",
            "features": [{"name": "TV #gf_probe = 42 mm", "isUserFeature": True}],
            "partsText": "",
        }
        page = FakePage(
            menu_items=("Thin Variable",),
            features_before_insert=before,
            features=after,
            features_after_reload=after,
        )
        result = actions.insert_custom_feature(page, "Thin Variable")
        self.assertTrue(result["inserted"])
        self.assertTrue(result["commit"]["committed"])
        self.assertTrue(result["listed"])
        self.assertFalse(result["errored"])
        self.assertEqual(
            result["createdRows"], [{"name": "TV #gf_probe = 42 mm", "hasError": False}]
        )
        # The survival wait asks for a row COUNT, so its text filter is empty and
        # the wait cannot be defeated by the template's display text.
        survival = page.wait_function_calls[-1]["arg"]
        self.assertEqual(survival["text"], "")
        self.assertEqual(survival["minimum"], 1)

    def test_a_template_named_row_that_disappears_is_never_called_inserted(
        self,
    ) -> None:
        """The count check must not turn into a weaker check.

        A template-named row is confirmed by counting, so the failure direction has
        to stay strict: a row that the reload does not bring back is not an insert.
        """
        after = {
            "headerText": "特征 (1)",
            "features": [{"name": "TV #gf_probe = 42 mm", "isUserFeature": True}],
            "partsText": "",
        }
        page = FakePage(
            menu_items=("Thin Variable",),
            features=after,
            features_after_reload={"headerText": "特征 (0)", "features": [], "partsText": ""},
        )
        page.never_satisfied_minimum = 1
        result = actions.insert_custom_feature(page, "Thin Variable")
        self.assertFalse(result["inserted"])
        self.assertTrue(result["commit"]["verified"])
        self.assertFalse(result["commit"]["committed"])
        self.assertFalse(result["listed"])
        self.assertIn("never settled", result["reason"])

    def test_a_third_row_beyond_two_existing_ones_is_a_commit(self) -> None:
        before = {
            "headerText": "特征 (7)",
            "features": [
                {"name": "Bc 1", "isUserFeature": True},
                {"name": "Bc 2", "isUserFeature": True},
            ],
            "partsText": "零件数 (2) Bc Bc",
        }
        after = {
            "headerText": "特征 (8)",
            "features": [
                {"name": "Bc 1", "isUserFeature": True},
                {"name": "Bc 2", "isUserFeature": True},
                {"name": "Bc 3", "isUserFeature": True},
            ],
            "partsText": "零件数 (3) Bc Bc Bc",
        }
        page = FakePage(
            features_before_insert=before, features=after, features_after_reload=after
        )
        result = actions.insert_custom_feature(page, "Bc")
        self.assertEqual(result["baselineRows"], 2)
        self.assertEqual(
            [
                call["arg"]["minimum"]
                for call in page.wait_function_calls
                if "minimum" in call["arg"]
            ],
            [3, 3],
            "both count waits ask for one row more than the 2-row baseline; the "
            "document-shell gate between them carries no count",
        )
        self.assertTrue(result["inserted"])

    def test_the_survival_wait_absorbs_a_slow_post_reload_render(self) -> None:
        """The live false-failure: the title renders before the rows.

        A read taken the instant the panel appears is empty. The survival wait is
        what makes that safe, so the check must pass on a page whose rows appear
        only after the wait has been entered.
        """
        before = {"headerText": "特征 (0)", "features": [], "partsText": "零件数 (0)"}
        after = {
            "headerText": "特征 (1)",
            "features": [{"name": "Bc 1", "isUserFeature": True}],
            "partsText": "零件数 (1) Bc",
        }
        page = FakePage(
            features_before_insert=before, features=after, features_after_reload=after
        )
        result = actions.insert_custom_feature(page, "Bc")
        self.assertTrue(result["inserted"])
        self.assertEqual(
            page.wait_function_calls[-1]["arg"]["minimum"], 1,
            "the survival wait must ask for the baseline plus one",
        )
        self.assertEqual(
            page.wait_function_calls[-1]["timeout"],
            actions.partstudio_wait_budget_ms(actions.PARTSTUDIO_RELOAD_WAIT, 0),
        )
        self.assertTrue(result["waits"]["commitSurvival"]["waited"])

    def test_a_row_that_does_not_survive_the_reload_is_not_an_insert(self) -> None:
        page = FakePage(features_after_reload={
            "headerText": "特征 (0)", "features": [], "partsText": "",
        })
        page.never_satisfied_minimum = 1
        result = actions.insert_custom_feature(page, "Bc")
        self.assertFalse(result["inserted"])
        self.assertTrue(result["commit"]["verified"])
        self.assertFalse(result["commit"]["committed"])
        self.assertFalse(result["listed"])
        self.assertIn("never settled", result["reason"])

    def test_a_failed_reload_is_unverified_rather_than_a_success(self) -> None:
        page = FakePage(reload_fails=True)
        result = actions.insert_custom_feature(page, "Bc")
        self.assertFalse(result["inserted"])
        self.assertFalse(result["commit"]["verified"])
        self.assertFalse(result["commit"]["committed"])
        self.assertIn("did not complete", result["reason"])
        # The pre-reload row survives as evidence, never as acceptance.
        self.assertTrue(result["listed"])
        self.assertIsNone(result["commit"]["survived"])

    def test_the_post_accept_read_is_evidence_and_not_the_gate(self) -> None:
        """A mid-re-render read must not decide the insert.

        Measured live 2026-09-21: the read taken straight after an accepted insert
        returned ZERO user rows while the same insert survived the confirming reload
        -- the accept starts a re-render that clears the list first. So the reload is
        always spent once the accept landed, and the count it reads decides.
        """
        after = {"headerText": "特征 (1)",
                 "features": [{"name": "Bc", "isUserFeature": True}],
                 "partsText": "零件数 (1) Bc"}
        # The read right after the accept is empty; the reload brings the row back.
        page = FakePage(
            features={"headerText": "", "features": [], "partsText": ""},
            features_after_reload=after,
        )
        result = actions.insert_custom_feature(page, "Bc")
        self.assertFalse(result["workbenchAppeared"],
                         "the transient read is reported, and it was empty")
        self.assertEqual(len(page.reload_calls), 1, "the reload is the deciding read")
        self.assertTrue(result["commit"]["verified"])
        self.assertTrue(result["commit"]["committed"])
        self.assertTrue(result["inserted"])

    def test_a_row_that_really_never_landed_is_still_rejected(self) -> None:
        """The reload decides, so a genuinely absent row cannot pass either."""
        page = FakePage(
            features={"headerText": "", "features": [], "partsText": ""},
            features_after_reload={"headerText": "", "features": [], "partsText": ""},
        )
        page.never_satisfied_minimum = 1
        result = actions.insert_custom_feature(page, "Bc")
        self.assertFalse(result["inserted"])
        self.assertTrue(result["commit"]["verified"])
        self.assertFalse(result["commit"]["committed"])
        self.assertIn("never settled", result["reason"])

    def test_a_slow_post_reload_boot_is_a_non_verdict_not_a_missing_row(self) -> None:
        """The shell gate keeps a slow boot out of the row verdict.

        Measured live 2026-09-21: a reload fired straight after an accept left the
        tab strip and the Feature List unrendered for more than 30 s on a document
        that carries a live Feature Studio, so the survival wait counted 0 user rows
        and reported every step of a 23-row build as ``inserted: False`` while the
        rows were in fact committed. A page that never rendered is evidence about
        the page, so the insert claims neither outcome and says which read failed.
        """
        row = {
            "headerText": "特征 (1)",
            "features": [{"name": "Bc 1", "isUserFeature": True}],
            "partsText": "零件数 (1) Bc",
        }
        page = FakePage(
            features=row,
            features_before_insert={"headerText": "特征 (0)", "features": [], "partsText": ""},
            features_after_reload=row,
        )
        page.document_ready = False
        result = actions.insert_custom_feature(page, "Bc")
        self.assertIsNone(result["inserted"], "an unrendered page proves nothing")
        self.assertEqual(result["applyState"], "pending_verification")
        self.assertFalse(result["commit"]["bootReady"])
        self.assertFalse(result["commit"]["committed"])
        self.assertIn("had not rendered", result["reason"])
        self.assertIn("neither success nor failure", result["reason"])
        # The row wait is never issued on an unrendered page: there is no list to
        # count, and a count taken now is what produced the false failure.
        self.assertEqual(
            [call["arg"].get("selector") for call in page.wait_function_calls],
            [selectors.PARTSTUDIO_FEATURE_ITEM, selectors.DOCUMENT_TABS_BUTTON],
        )

    def test_the_verifier_alone_reports_uncommitted_and_unverified(self) -> None:
        listed = {
            "headerText": "特征 (1)",
            "features": [{"name": "Bc 1", "isUserFeature": True}],
            "partsText": "零件数 (1) Bc",
        }
        page = FakePage(features_before_insert=listed)
        uncommitted = actions.verify_insert_committed(page, "Bc", minimum=1)
        self.assertFalse(uncommitted["verified"])
        self.assertFalse(uncommitted["committed"])
        self.assertIsNone(uncommitted["reload"])
        self.assertEqual(page.reload_calls, [])
        committed = actions.verify_insert_committed(
            page, "Bc", minimum=1, appeared=True
        )
        self.assertTrue(committed["verified"])
        self.assertTrue(committed["committed"])
        self.assertEqual(len(page.reload_calls), 1)
        self.assertTrue(committed["reload"]["reloaded"])
        self.assertTrue(committed["survived"]["waited"])

    def test_the_survival_wait_can_drop_the_name_filter_it_cannot_satisfy(self) -> None:
        """`match_name=False` is the arg shape the commit check depends on."""
        page = FakePage(features_before_insert={
            "headerText": "特征 (1)",
            "features": [{"name": "TV #gf_probe = 42 mm", "isUserFeature": True}],
            "partsText": "",
        })
        outcome = actions.wait_for_feature_rows(page, "Thin Variable", 1, 30_000,
                                                match_name=False)
        self.assertTrue(outcome["waited"])
        self.assertFalse(outcome["matchName"])
        self.assertEqual(
            page.wait_function_calls[0]["arg"],
            {"selector": selectors.PARTSTUDIO_FEATURE_ITEM, "text": "", "minimum": 1},
        )
        # And the name-matched form of the SAME wait cannot see that row at all,
        # which is the live false-failure this argument exists to remove.
        named = actions.wait_for_feature_rows(page, "Thin Variable", 1, 5)
        self.assertFalse(named["waited"])
        self.assertEqual(
            page.wait_function_calls[-1]["arg"],
            {"selector": selectors.PARTSTUDIO_FEATURE_ITEM,
             "text": "Thin Variable", "minimum": 1},
        )

    def test_the_created_row_is_identified_by_name_set_difference(self) -> None:
        """A count alone cannot say WHICH row is new, so the names are subtracted.

        Two user rows exist before the insert and three after; the third one is the
        created row even though none of the three names matches the feature type.
        """
        before = {
            "headerText": "特征 (2)",
            "features": [
                {"name": "TV #a = 1 mm", "isUserFeature": True},
                {"name": "TV #b = 2 mm", "isUserFeature": True},
            ],
            "partsText": "",
        }
        after = {
            "headerText": "特征 (3)",
            "features": [
                {"name": "TV #a = 1 mm", "isUserFeature": True},
                {"name": "TV #b = 2 mm", "isUserFeature": True},
                {"name": "TV #c = 3 mm", "isUserFeature": True},
            ],
            "partsText": "",
        }
        page = FakePage(
            features_before_insert=before, features=after, features_after_reload=after
        )
        commit = actions.verify_insert_committed(
            page,
            "Thin Variable",
            survival_minimum=3,
            baseline_names=[row["name"] for row in actions.user_feature_rows(before)],
            appeared=True,
        )
        self.assertTrue(commit["verified"])
        self.assertTrue(commit["committed"])
        self.assertEqual(commit["createdRows"],
                         [{"name": "TV #c = 3 mm", "hasError": False}])
        # The name-matched state still reports nothing, which is precisely why the
        # verdict cannot be taken from it.
        self.assertFalse(commit["featureRows"] == commit["createdRows"])
        self.assertEqual(len(commit["featureRows"]), 0)
        # The wait asked for a count, not a name. The LAST in-page call is the
        # document-shell gate, which carries no row count, so this looks at the
        # survival wait itself.
        self.assertEqual(
            [
                call["arg"]["text"]
                for call in page.wait_function_calls
                if "minimum" in call["arg"]
            ][-1],
            "",
        )

    def test_a_created_row_is_the_excess_over_a_baseline_multiset(self) -> None:
        """A name two rows share must not hide the row this call created.

        Measured live 2026-09-21: a run reported as a relay timeout kept running
        server-side, its resume raced it, and the element ended up with two identical
        ``TV #gf_lock = 37.7 mm 锁定面方孔边长`` rows. The set-difference verdict then
        said the NEW row was "not created" because its name was already in the
        baseline, which made the project runner fail that step on every resume. The
        excess over the baseline NAME COUNTS is the row in question.
        """
        duplicated = "TV #gf_lock = 37.7 mm 锁定面方孔边长"
        after = {
            "headerText": "特征 (3)",
            "features": [
                {"name": duplicated, "isUserFeature": True},
                {"name": duplicated, "isUserFeature": True},
                {"name": duplicated, "isUserFeature": True},
            ],
            "partsText": "",
        }
        page = FakePage(features_after_reload=after)
        commit = actions.verify_insert_committed(
            page,
            "Thin Variable",
            survival_minimum=3,
            baseline_names=[duplicated, duplicated],
            appeared=True,
        )
        self.assertTrue(commit["verified"])
        self.assertTrue(commit["committed"], "the third row is the one this call added")
        self.assertEqual(commit["createdRows"],
                         [{"name": duplicated, "hasError": False}])
        self.assertEqual(commit["reason"], "")

    def test_a_row_short_of_the_count_gate_is_a_non_verdict(self) -> None:
        """A partial post-reload read must not be reported as a missing feature.

        The Feature List is VIRTUALISED, so the read taken after the survival wait can
        see fewer rows than the wait's own DOM predicate just counted (measured live
        2026-09-21: a survival wait that had counted 7 user rows was followed by a
        shorter read, and the old single message called the insert "not survived"
        while the row was on screen twice). The verdict stays False -- an unreadable
        page is never a success -- and the reason now names the READ that fell short
        instead of blaming the workspace.
        """
        page = FakePage(features_after_reload={
            "headerText": "特征 (2)",
            "features": [
                {"name": "TV #c = 3 mm", "isUserFeature": True},
                {"name": "TV #d = 4 mm", "isUserFeature": True},
            ],
            "partsText": "",
        })
        partial = {
            "headerText": "特征 (2)",
            "features": [{"name": "TV #c = 3 mm", "isUserFeature": True}],
            "partsText": "",
        }
        with mock.patch.object(
            actions, "read_partstudio_features", return_value=partial
        ):
            commit = actions.verify_insert_committed(
                page, "Thin Variable", survival_minimum=2, appeared=True
            )
        self.assertTrue(commit["verified"])
        self.assertFalse(commit["committed"], "one row is short of the two-row gate")
        self.assertIn("partial window", commit["reason"])

    def test_the_survival_wait_reports_its_own_timeout_as_evidence(self) -> None:
        page = FakePage()
        page.never_satisfied_minimum = 1
        outcome = actions.wait_for_feature_rows(page, "Bc", 1, 30_000)
        self.assertFalse(outcome["waited"])
        self.assertEqual(outcome["condition"], "user_feature_row_count")
        self.assertEqual(outcome["minimum"], 1)
        self.assertEqual(outcome["timeoutMs"], 30_000)
        self.assertIn("TimeoutError", outcome["error"])
        self.assertEqual(
            page.wait_function_calls[0]["arg"],
            {"selector": selectors.PARTSTUDIO_FEATURE_ITEM, "text": "Bc", "minimum": 1},
        )

    def test_an_errored_row_still_reports_its_error_after_the_reload(self) -> None:
        page = FakePage(features_after_reload={
            "headerText": "特征 (1)",
            "features": [{"name": "Bc 1", "isUserFeature": True, "hasError": True}],
            "partsText": "",
        })
        result = actions.insert_custom_feature(page, "Bc")
        self.assertTrue(result["listed"])
        self.assertTrue(result["errored"])
        self.assertIn("unresolved error", result["reason"])


class FeatureListedTest(unittest.TestCase):
    def test_matching_requires_a_user_feature_and_a_non_empty_name(self) -> None:
        features = {"features": [
            {"name": "Bc (custom)", "isUserFeature": True},
            {"name": "BcDefault", "isUserFeature": False},
        ]}
        self.assertTrue(actions.feature_listed(features, "bc"))
        self.assertTrue(actions.feature_listed(features, "BC (CUSTOM)"))
        # A default feature whose name contains the text is not the custom feature.
        self.assertFalse(actions.feature_listed(features, "BcDefault"))
        # An empty name is never a match, even when user features exist.
        self.assertFalse(actions.feature_listed(features, ""))
        self.assertFalse(actions.feature_listed(features, "   "))
        self.assertFalse(actions.feature_listed(features, None))

    def test_malformed_feature_lists_are_not_matches(self) -> None:
        self.assertFalse(actions.feature_listed(None, "Bc"))
        self.assertFalse(actions.feature_listed({}, "Bc"))
        self.assertFalse(actions.feature_listed({"features": "Bc"}, "Bc"))
        self.assertFalse(actions.feature_listed({"features": [None, 5]}, "Bc"))


class SameQuantityTest(unittest.TestCase):
    """The one comparison a literal and a settled expression both have to pass."""

    def test_text_matches_case_insensitively_with_whitespace_collapsed(self):
        self.assertTrue(actions.quantities_match(" 45 deg ", "45 DEG"))
        self.assertTrue(actions.quantities_match("true", "true"))
        self.assertFalse(actions.quantities_match("true", "false"))

    def test_a_rendered_number_matches_the_same_number_written_differently(self):
        self.assertTrue(actions.quantities_match("36.3 mm", "36.30 mm"))
        self.assertTrue(actions.quantities_match("42 mm", "42 mm"))

    def test_the_unit_is_part_of_the_value(self):
        """Ignoring it would accept 36.3 in for a 36.3 mm dimension."""
        self.assertFalse(actions.quantities_match("36.3 in", "36.3 mm"))
        self.assertFalse(actions.quantities_match("36.3", "36.3 mm"))
        # An empty readback is not evidence for a value that was asked for, while
        # clearing a text field is a real request and reads back exactly empty.
        self.assertFalse(actions.quantities_match("", "36.3 mm"))
        self.assertTrue(actions.quantities_match("", ""))

    def test_text_that_is_not_a_quantity_falls_back_to_text(self):
        self.assertTrue(actions.quantities_match("#gf_socket", "#gf_socket"))
        self.assertFalse(actions.quantities_match("#gf_socket", "#gf_pitch"))


class DialogFieldResolveWaitTest(unittest.TestCase):
    """The accept gate for an expression: the dialog's own readback, after a wait."""

    def test_an_expression_with_no_stated_value_is_refused_without_a_wait(self):
        """The typed text is not a settle signal, so such a key cannot be confirmed.

        Measured live 2026-09-21: an accept taken while the field still showed the typed
        `#gf_pitch * 2` committed the field's previous value, and the row landed as
        `TV #gf_plate_size = 0 mm`. A caller that states no value therefore gets an
        immediate, explicit refusal instead of a 20 s wait that ends in the same place.
        """
        page = FakePage(dialog_fields={"value": "0 mm"}, expression_keys={"value"})
        filled = actions.fill_dialog_fields(page, {"value": "#gf_pitch * 2"})
        self.assertEqual(filled["mismatched"], ["value"])
        self.assertFalse(filled["readbackOk"])
        self.assertFalse(filled["resolved"])
        wait = filled["expressionWait"]
        self.assertEqual(wait["condition"], "unstated_expression")
        self.assertEqual(wait["unstatedExpressionKeys"], ["value"])
        self.assertEqual(wait["elapsedMs"], 0)
        self.assertEqual(page.timeouts, [], "it does not spend the expression budget")

    def test_a_settled_widget_may_render_the_evaluated_number(self):
        """A dimension reads back the resolved value, so the caller states it.

        Measured live 2026-09-21: `#gf_socket` read back as `36.3 mm` once the widget
        had resolved it, so a comparison against the typed text alone would call a
        correct dimension a permanent mismatch.
        """
        page = FakePage(
            dialog_fields={"width": "100 mm"},
            expression_keys={"width"},
            evaluated={"#gf_socket": "36.3 mm"},
        )
        filled = actions.fill_dialog_fields(
            page, {"width": "#gf_socket"}, expect_values={"width": "36.30 mm"}
        )
        self.assertEqual(filled["after"]["width"], "36.3 mm")
        self.assertEqual(filled["mismatched"], [])
        self.assertTrue(filled["readbackOk"])
        self.assertEqual(filled["expectValues"], {"width": "36.30 mm"})
        self.assertEqual(filled["expressionWait"]["resolvedValues"],
                         {"width": "36.30 mm"})
        self.assertEqual(filled["expressionWait"]["strictKeys"], ["width"])
        self.assertEqual(filled["expressionWait"]["elapsedMs"], 0,
                         "the wait's own read is the one that settled")

    def test_the_typed_expression_alone_never_confirms_a_stated_value(self):
        """The live defect: the widget showed the typed `#expression`, defaults won.

        Measured live 2026-09-21: a variable-driven `Thin Sketch Rectangle` stored its
        100 mm / 100 mm / 0 mm dialog DEFAULTS while its literal-valued sibling in the
        same document stored the requested 84 mm / 84 mm / 4 mm. The wait had accepted
        the typed expression as a settle signal and the accept then committed the
        field's previous value, so a key the caller states a value for is confirmed
        ONLY by that value.
        """
        page = FakePage(
            dialog_fields={"width": "100 mm"},
            expression_keys={"width"},
            evaluated={"#gf_lock": "#gf_lock"},
        )
        with mock.patch.object(actions.time, "monotonic", page.clock.monotonic):
            filled = actions.fill_dialog_fields(
                page, {"width": "#gf_lock"}, expect_values={"width": "37.7 mm"}
            )
        self.assertEqual(filled["after"]["width"], "#gf_lock")
        self.assertEqual(filled["mismatched"], ["width"])
        self.assertFalse(filled["readbackOk"])
        self.assertFalse(filled["resolved"])

    def test_a_literal_key_is_judged_by_its_text_and_an_expression_by_its_value(self):
        """Only an expression is strict; a literal still reads back as what was typed."""
        page = FakePage(
            dialog_fields={"value": "#gf_pitch * 2", "depth": "0.35 mm"},
            expression_keys={"value"},
        )
        with mock.patch.object(actions.time, "monotonic", page.clock.monotonic), \
                mock.patch.object(actions, "dialog_values",
                                  return_value={"value": "#gf_pitch * 2",
                                                "depth": "0.35 mm"}):
            outcome = actions.wait_for_dialog_fields(
                page, {"value": "#gf_pitch * 2", "depth": "0.35 mm"},
                ["value", "depth"], timeout_ms=0, resolved={"value": "84 mm"},
            )
        self.assertEqual(outcome["strictKeys"], ["value"])
        self.assertEqual(outcome["mismatched"], ["value"],
                         "the literal key matched its own text")

    def test_without_a_stated_value_a_rendered_number_is_a_refusal(self):
        """Nothing else can confirm it: the typed text never comes back."""
        page = FakePage(
            dialog_fields={"width": "100 mm"},
            expression_keys={"width"},
            evaluated={"#gf_socket": "36.3 mm"},
        )
        page.expression_never_resolves = True
        with mock.patch.object(actions.time, "monotonic", page.clock.monotonic):
            filled = actions.fill_dialog_fields(page, {"width": "#gf_socket"})
        self.assertEqual(filled["mismatched"], ["width"])
        self.assertFalse(filled["readbackOk"])
        self.assertFalse(filled["resolved"])

    def test_expect_values_is_only_consulted_for_expression_fields(self):
        """A literal field is judged by what was typed, never by a stray entry."""
        page = FakePage(dialog_fields={"width": "100 mm"})
        filled = actions.fill_dialog_fields(
            page, {"width": "100 mm"}, expect_values={"width": "36.3 mm"}
        )
        self.assertEqual(filled["mismatched"], [])
        self.assertEqual(filled["expectValues"], {})
        self.assertIsNone(filled["expressionWait"])
        self.assertIsNone(filled["resolved"])

    def test_an_unsettled_field_is_reported_and_never_raised(self):
        page = FakePage(dialog_fields={"value": "0 mm"}, expression_keys={"value"})
        page.expression_never_resolves = True
        with mock.patch.object(actions.time, "monotonic", page.clock.monotonic):
            outcome = actions.wait_for_dialog_fields(
                page, {"value": "#gf_pitch * 2"}, ["value"], timeout_ms=3_000, poll_ms=1_000,
                resolved={"value": "84 mm"},
            )
        self.assertFalse(outcome["waited"])
        self.assertEqual(outcome["mismatched"], ["value"])
        self.assertEqual(outcome["after"]["value"], "0 mm")
        # The loop polls on a real clock and gives up at the budget, not before.
        self.assertEqual([call for call in page.timeouts], [1_000, 1_000, 1_000])
        self.assertEqual(outcome["timeoutMs"], 3_000)

    def test_it_judges_only_the_keys_it_was_given(self):
        """A literal field's own value is the fill verdict's business, not this wait's."""
        page = FakePage(dialog_fields={"value": "0 mm", "name": "gf_plate_size"},
                        expression_keys={"value"})
        with mock.patch.object(actions, "dialog_values",
                               return_value={"value": "0 mm", "name": "gf_plate_size"}):
            outcome = actions.wait_for_dialog_fields(
                page, {"value": "#gf_pitch * 2", "name": "gf_plate_size"}, ["value"],
                timeout_ms=0, resolved={"value": "84 mm"},
            )
        self.assertFalse(outcome["waited"])
        self.assertEqual(outcome["mismatched"], ["value"])
        self.assertEqual(outcome["timeoutMs"], 0, "a zero budget reads once and stops")

    def test_the_default_budget_is_the_measured_one(self):
        self.assertEqual(actions.EXPRESSION_RESOLVE_WAIT_MS, 20_000)
        self.assertEqual(actions.EXPRESSION_RESOLVE_POLL_MS, 1_000)


class UserFeatureRowsTest(unittest.TestCase):
    """Every user row, whatever it is called — the count the commit gate uses."""

    def test_user_rows_carry_name_and_error_and_skip_the_defaults(self) -> None:
        features = {"features": [
            {"name": "默认几何图元", "isUserFeature": False},
            {"name": "TV #gf_probe = 42 mm", "isUserFeature": True},
            {"name": "GB GF Base Plate Body 1", "isUserFeature": True, "hasError": True},
        ]}
        self.assertEqual(
            actions.user_feature_rows(features),
            [
                {"name": "TV #gf_probe = 42 mm", "hasError": False},
                {"name": "GB GF Base Plate Body 1", "hasError": True},
            ],
        )

    def test_a_missing_error_flag_is_false_not_absent(self) -> None:
        rows = actions.user_feature_rows(
            {"features": [{"name": "TV #a = 1 mm", "isUserFeature": True}]}
        )
        self.assertEqual(rows, [{"name": "TV #a = 1 mm", "hasError": False}])

    def test_malformed_feature_lists_yield_no_rows(self) -> None:
        for features in (None, {}, {"features": "TV"}, {"features": [None, 5]}):
            self.assertEqual(actions.user_feature_rows(features), [])

    def test_a_nameless_row_still_counts_so_the_gate_cannot_be_evaded(self) -> None:
        """A row with no readable name is still a row: it must inflate the count.

        ``feature_state`` finds no name match for it (so it is never called the
        feature that was asked for), but the commit gate counts it, which keeps the
        gate conservative in the "not inserted" direction.
        """
        rows = actions.user_feature_rows({"features": [{"isUserFeature": True}]})
        self.assertEqual(rows, [{"name": "", "hasError": False}])
        self.assertFalse(
            actions.feature_state({"features": [{"isUserFeature": True}]}, "Bc")["listed"]
        )


class BuildPartAcceptanceTest(unittest.TestCase):
    """`built` needs all three signals: the insert, the feature row, a part."""

    def build(self, inserted: dict, features: dict) -> dict:
        with mock.patch.object(actions, "insert_custom_feature", return_value=inserted), \
             mock.patch.object(actions, "read_partstudio_features", return_value=features):
            return semantic.build_part(mock.Mock(), "Bc")

    def test_built_requires_the_insert_the_feature_and_a_part(self) -> None:
        result = self.build(
            {"inserted": True, "features": {"features": [{"name": "Bc", "isUserFeature": True}],
                                            "partsText": "零件数 (2) a  b"}},
            {},
        )
        self.assertTrue(result["built"])
        self.assertTrue(result["featurePresent"])
        self.assertTrue(result["featureComputed"])
        self.assertFalse(result["featureError"])
        self.assertEqual(result["reason"], "")
        self.assertEqual(result["parts"], 2)

    def test_zero_parts_is_not_built(self) -> None:
        result = self.build(
            {"inserted": True, "features": {"features": [{"name": "Bc", "isUserFeature": True}],
                                            "partsText": "零件数 (0)"}},
            {},
        )
        self.assertFalse(result["built"])
        self.assertTrue(result["featurePresent"])
        self.assertEqual(result["parts"], 0)
        self.assertEqual(result["reason"], "the Part Studio reports no computed parts")

    def test_a_not_computed_row_is_not_built_even_with_parts(self) -> None:
        """The recorded failure mode: a `not-computed` row is still a row, so
        presence alone would report success once other features supply geometry."""
        result = self.build(
            {"inserted": True, "features": {"features": [
                {"name": "Bc Branch cable trophy display 1", "isUserFeature": True,
                 "hasError": True, "className": "os-list-item ns-user-feature not-computed"},
            ], "partsText": "零件数 (132) base  plaqueInsert_blank"}},
            {},
        )
        self.assertFalse(result["built"])
        self.assertTrue(result["featurePresent"])
        self.assertFalse(result["featureComputed"])
        self.assertTrue(result["featureError"])
        self.assertEqual(
            result["featureRows"],
            [{"name": "Bc Branch cable trophy display 1", "hasError": True}],
        )
        self.assertIn("unresolved error", result["reason"])
        self.assertEqual(result["parts"], 132)

    def test_a_failed_insert_is_not_built_even_when_parts_exist(self) -> None:
        result = self.build(
            {"inserted": False, "reason": "dropdown did not open",
             "features": {"features": [], "partsText": "零件数 (3) a  b  c"}},
            {},
        )
        self.assertFalse(result["built"])
        self.assertFalse(result["featurePresent"])
        self.assertIn("did not open", result["reason"])
        self.assertIn("did not open", result["insert"]["reason"])

    def test_a_missing_feature_row_is_not_built(self) -> None:
        result = self.build(
            {"inserted": True, "features": {"features": [{"name": "Other", "isUserFeature": True}],
                                            "partsText": "零件数 (1) x"}},
            {},
        )
        self.assertFalse(result["built"])
        self.assertFalse(result["featurePresent"])
        self.assertIn("is not present in the Feature List", result["reason"])

    def test_a_feature_row_without_a_part_count_is_not_built(self) -> None:
        result = self.build(
            {"inserted": True, "features": {"features": [{"name": "Bc", "isUserFeature": True}],
                                            "partsText": "无可读文本"}},
            {},
        )
        self.assertFalse(result["built"])
        self.assertTrue(result["featurePresent"])
        self.assertEqual(result["reason"], "the Part Studio reports no computed parts")


class FeatureStateTest(unittest.TestCase):
    """Presence and computedness come from one matching rule."""

    def test_presence_and_error_are_separate_signals(self) -> None:
        features = {"features": [
            {"name": "Other", "isUserFeature": True},
            {"name": "Bc 1", "isUserFeature": True},
            {"name": "Bc 2", "isUserFeature": True, "hasError": True},
        ]}
        state = actions.feature_state(features, "Bc")
        self.assertTrue(state["listed"])
        self.assertTrue(state["errored"])
        self.assertEqual(state["names"], ["Bc 1", "Bc 2"])
        self.assertEqual(state["rows"], [
            {"name": "Bc 1", "hasError": False},
            {"name": "Bc 2", "hasError": True},
        ])
        self.assertTrue(actions.feature_listed(features, "Bc"))

    def test_a_clean_row_is_listed_and_not_errored(self) -> None:
        self.assertEqual(
            actions.feature_state(
                {"features": [{"name": "Bc 1", "isUserFeature": True, "hasError": False}]}, "Bc",
            ),
            {
                "listed": True, "errored": False, "names": ["Bc 1"],
                "rows": [{"name": "Bc 1", "hasError": False}],
            },
        )

    def test_default_features_are_not_matches(self) -> None:
        state = actions.feature_state(
            {"features": [{"name": "Bc origin", "isUserFeature": False, "hasError": True}]}, "Bc",
        )
        self.assertFalse(state["listed"])
        self.assertFalse(state["errored"])

    def test_empty_names_and_malformed_lists_are_never_matches(self) -> None:
        for features, name in (
            ({"features": [{"name": "Bc", "isUserFeature": True}]}, ""),
            ({"features": [{"name": "Bc", "isUserFeature": True}]}, "   "),
            ({"features": "Bc"}, "Bc"),
            ({}, "Bc"),
            (None, "Bc"),
            ([{"name": "Bc"}], "Bc"),
            ({"features": [None, "Bc"]}, "Bc"),
        ):
            with self.subTest(features=features, name=name):
                state = actions.feature_state(features, name)
                self.assertFalse(state["listed"])
                self.assertFalse(state["errored"])
                self.assertFalse(actions.feature_listed(features, name))


class WaitConditionTextFilterTest(unittest.TestCase):
    """`text` must narrow a visibility wait to the matching element."""

    class _Locator:
        def __init__(self, *, fails: bool = False) -> None:
            self.fails = fails
            self.filter_text: str | None = None
            self.wait_calls: list[dict] = []

        def filter(self, has_text: str = "") -> "WaitConditionTextFilterTest._Locator":
            self.filter_text = has_text
            return self

        def nth(self, _index: int) -> "WaitConditionTextFilterTest._Locator":
            return self

        @property
        def first(self) -> "WaitConditionTextFilterTest._Locator":
            return self

        def wait_for(self, **kwargs) -> None:
            self.wait_calls.append(kwargs)
            if self.fails:
                raise TimeoutError("never visible")

    class _Page:
        def __init__(self, locator) -> None:
            self._locator = locator
            self.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"

        def locator(self, _selector: str):
            return self._locator

    def test_text_filters_the_target_and_is_reported(self) -> None:
        locator = self._Locator()
        result = interaction.wait_for_condition(
            self._Page(locator), condition="visible", selector=".os-list-item",
            text="Bc", timeout_ms=1_234,
        )
        self.assertTrue(result["waited"])
        self.assertEqual(result["targetText"], "Bc")
        self.assertEqual(locator.filter_text, "Bc")
        self.assertEqual(locator.wait_calls, [{"state": "visible", "timeout": 1_234}])

    def test_without_text_the_first_match_is_waited_on_unchanged(self) -> None:
        locator = self._Locator()
        result = interaction.wait_for_condition(
            self._Page(locator), condition="attached", selector=".os-list-item", timeout_ms=500,
        )
        self.assertTrue(result["waited"])
        self.assertNotIn("targetText", result)
        self.assertIsNone(locator.filter_text)

    def test_a_timeout_is_returned_as_data(self) -> None:
        locator = self._Locator(fails=True)
        result = interaction.wait_for_condition(
            self._Page(locator), condition="visible", selector=".os-list-item",
            text="Bc", timeout_ms=500,
        )
        self.assertFalse(result["waited"])
        self.assertIn("TimeoutError", result["error"])
        self.assertIn("elapsedMs", result)

    def test_a_missing_selector_still_raises(self) -> None:
        with self.assertRaises(ValueError):
            interaction.wait_for_condition(self._Page(self._Locator()), condition="visible")


class FakeDialogLocator:
    """Locator double whose counts come from the page's own model of the DOM.

    That is the point: ``read_features`` models what a READ reports and
    ``locator_user_rows`` models what the row locator counts, so a test can make
    the two disagree exactly as they did live on 2026-09-20.
    """

    def __init__(self, page: "FakeDialogPage", selector: str, index: int | None = None) -> None:
        self.page = page
        self.selector = selector
        self.index = index

    def _parameter_key(self) -> str | None:
        match = re.search(r'(?:data-parameter-id|parameter-id|name)="([^"]+)"', self.selector)
        return match.group(1) if match else None

    def count(self) -> int:
        if self.selector == selectors.PS_USER_FEATURE:
            return self.page.locator_user_rows
        if self.selector == selectors.TAB_CONTEXT_MENU:
            return 1 if self.page.context_menu_open else 0
        if self.selector == selectors.TAB_CONTEXT_MENU_ITEM:
            return len(self.page.menu_labels) if self.page.context_menu_open else 0
        if self.selector == selectors.PS_FEATURE_DIALOG:
            return 1 if self.page.dialog_visible else 0
        if self.selector == selectors.PS_FEATURE_DIALOG_ACCEPT:
            # The parameter dialog's accept button and a delete confirmation share
            # this selector live, so the double gates it on either being on screen.
            return 1 if (self.page.dialog_visible or self.page.confirm_dialog) else 0
        key = self._parameter_key()
        if key is None or not self.page.locator_sees_parameter:
            return 0
        return 1 if key in self.page.parameter_fields else 0

    def locator(self, selector: str) -> "FakeDialogLocator":
        return FakeDialogLocator(self.page, selector)

    def filter(self, **kwargs: object) -> "FakeDialogLocator":
        return self

    def nth(self, index: int) -> "FakeDialogLocator":
        return FakeDialogLocator(self.page, self.selector, index)

    @property
    def first(self) -> "FakeDialogLocator":
        return self

    def dblclick(self) -> None:
        assert self.index is not None, "the edit path must click a known row index"
        self.page.dblclicks.append(self.index)
        if self.page.dialog_opens:
            self.page.dialog_visible = True

    def wait_for(self, state: str | None = None, timeout: float | None = None) -> bool:
        self.page.dialog_waits.append({"state": state, "timeout": timeout})
        if self.selector == selectors.PS_FEATURE_DIALOG and not self.page.dialog_visible:
            raise TimeoutError("dialog not visible")
        if self.selector == selectors.TAB_CONTEXT_MENU and not self.page.context_menu_open:
            raise TimeoutError("context menu not visible")
        return True

    def fill(self, value: str) -> None:
        key = self._parameter_key()
        self.page.fills.append({"key": key, "value": value})
        if key:
            self.page.dialog_values[key] = str(value)

    def click(self, **kwargs: object) -> None:
        if self.selector == selectors.PS_FEATURE_DIALOG_ACCEPT:
            if self.page.confirm_dialog:
                self.page.confirm_clicks.append("accept")
                self.page.confirm_dialog = False
                return
            # Accepting starts a regeneration; the dialog stays on screen until
            # the condition wait observes it gone. Closing it here would make the
            # timeout fallback look like a success.
            self.page.accept_clicks.append(True)
            return
        if self.selector == selectors.PS_USER_FEATURE:
            self.page.right_clicks.append({"index": self.index, **kwargs})
            if kwargs.get("button") == "right":
                self.page.context_menu_open = self.page.menu_opens
                self.page.context_menu_row_index = self.index
            return
        if self.selector == selectors.TAB_CONTEXT_MENU_ITEM:
            labels = self.page.menu_labels
            index = self.index if self.index is not None else 0
            label = labels[index] if 0 <= index < len(labels) else ""
            self.page.menu_clicks.append(label)
            self.page.context_menu_open = False
            if label in actions.PS_FEATURE_DELETE_MENU_TEXTS:
                if self.page.deletes_row and self.page.context_menu_row_index is not None:
                    self.page.remove_row(self.page.context_menu_row_index)
            return
    def is_visible(self) -> bool:
        if self.selector == selectors.TAB_CONTEXT_MENU_ITEM:
            return self.page.context_menu_open
        if self.selector == selectors.TAB_CONTEXT_MENU:
            return self.page.context_menu_open
        return True

    def inner_text(self) -> str:
        """The row's name or the menu item's label, from the page's own model."""
        if self.selector == selectors.PS_USER_FEATURE and self.index is not None:
            rows = self.page.dom_rows
            return rows[self.index] if 0 <= self.index < len(rows) else ""
        if self.selector == selectors.TAB_CONTEXT_MENU_ITEM and self.index is not None:
            labels = self.page.menu_labels
            return labels[self.index] if 0 <= self.index < len(labels) else ""
        return ""

    def is_checked(self) -> bool:
        return False


class FakeDialogPage:
    """Page double for the feature-dialog edit path (offline, no session).

    ``rows`` are the NAMED custom-feature rows in DOM order and ``nameless_rows``
    models the extra ``.os-list-item.ns-user-feature`` node that carries no text.
    Measured live 2026-09-20, that node is on every Part Studio: a READ that drops
    empty names saw 1 and 11 rows where the row locator counted 2 and 12. The
    double therefore holds ONE node list, ``dom_rows``, and answers both the
    enumeration and the locator from it — so a test cannot quietly model the two
    views as different sets again, which is the defect class being pinned here.
    Live that node is the LAST node in document order, and the refused call failed
    on the count comparison rather than on a shifted index; the default here puts it
    FIRST, which is strictly harder than live, and ``nameless_last`` models the
    measured layout.
    """

    def __init__(
        self,
        *,
        rows: tuple[str, ...] = ("Sr Spiral ridge 5", "Sr Spiral ridge 6", "Sr Spiral ridge 7"),
        nameless_rows: int = 1,
        nameless_last: bool = False,
        locator_delta: int = 0,
        panel_renders: bool = True,
        dialog_opens: bool = True,
        dialog_closes: bool = True,
        dialog_already_open: bool = False,
        reload_fails: bool = False,
        parameter_fields: tuple[str, ...] = ("baseRadius",),
        locator_sees_parameter: bool = True,
        reload_render_polls: int = 0,
        menu_labels: tuple[str, ...] = ("编辑", "抑制", "删除", "重命名", "回滚到此"),
        menu_opens: bool = True,
        deletes_row: bool = True,
        confirm_dialog: bool = False,
    ) -> None:
        self.rows = list(rows)
        self.nameless_rows = nameless_rows
        nameless = [""] * nameless_rows
        self.dom_rows = [*self.rows, *nameless] if nameless_last else [*nameless, *self.rows]
        # `locator_delta` is the only way to make the two views disagree, and it
        # models a DOM change between the enumeration and the click (a stale read),
        # not the live +1, which was a read-side filter.
        self.locator_user_rows = len(self.dom_rows) + locator_delta
        self.read_features = {
            "headerText": "特征 (%d)" % len(self.rows),
            # A READ filters nameless nodes out; the enumeration does not. Keeping
            # both in the double is what pins that difference.
            "features": [
                {"name": name, "isUserFeature": True, "hasError": False} for name in self.rows
            ],
            "partsText": "零件数 (1)",
            "partItems": [],
        }
        self.panel_renders = panel_renders
        self.dialog_opens = dialog_opens
        self.dialog_closes = dialog_closes
        self.reload_fails = reload_fails
        self.parameter_fields = tuple(parameter_fields)
        self.locator_sees_parameter = locator_sees_parameter
        self.dialog_values = {field: "10 mm" for field in self.parameter_fields}
        #: A panel that is on screen before the call models the measured state after an
        #: accept that changed a parameter: committed, and still open.
        self.dialog_visible = dialog_already_open
        self.url = "https://cad.onshape.com/documents/d1/w/w1/e/e1"
        self.dblclicks: list[int] = []
        self.fills: list[dict] = []
        self.accept_clicks: list[bool] = []
        self.dialog_waits: list[dict] = []
        self.wait_calls: list[dict] = []
        #: A fixed sleep here would misreport a successful edit as a failure, so
        #: every sleep is recorded and the accept test asserts this stays empty.
        self.timeouts: list[int] = []
        self.reloads: list[dict] = []
        self.load_states: list[str] = []
        #: How many row-render waits a reloaded page must fail before the custom-feature
        #: rows exist. Measured live 2026-09-20: after the recovery reload the page had no
        #: feature rows, no readable tabs and no tab-strip button, yet the broad
        #: ``.os-list-item`` readiness gate was satisfied — so a page can be "ready" by the
        #: old condition and still enumerate 0 rows. 0 keeps the older behaviour (a
        #: reloaded page reads immediately); a negative value models rows that never appear.
        self.reload_render_polls = reload_render_polls
        self.rendered = True
        self.render_polls = 0
        self.keyboard = mock.Mock()
        # The feature row's context menu: a right-click on a row opens the shared
        # jQuery menu, whose items are labels. `context_menu_row_index` is the row
        # the menu belongs to, so a delete removes THAT row rather than the row now
        # sitting at the menu item's position.
        self.menu_labels = list(menu_labels)
        self.menu_opens = menu_opens
        self.deletes_row = deletes_row
        self.confirm_dialog = confirm_dialog
        self.context_menu_open = False
        self.context_menu_row_index: int | None = None
        self.right_clicks: list[dict] = []
        self.menu_clicks: list[str] = []
        self.confirm_clicks: list[str] = []

    def remove_row(self, index: int) -> None:
        """Remove one row from BOTH views of the DOM, as a live delete does.

        The enumeration reads ``dom_rows`` and a read reads ``read_features``, so
        dropping the row from only one of them would model a page that cannot
        exist and would hide exactly the disagreement the delete verdict checks.
        """
        if 0 <= index < len(self.dom_rows):
            name = self.dom_rows.pop(index)
            if name in self.rows:
                self.rows.remove(name)
            # ONE row leaves, not every row with that name: live, a delete removes the
            # row that was clicked, so a duplicated name keeps its surviving twin in
            # both views. Dropping them all here would make the read agree with a
            # name-based verdict that is wrong for exactly that case.
            kept = []
            dropped = False
            for row in self.read_features["features"]:
                if not dropped and row["name"] == name:
                    dropped = True
                    continue
                kept.append(row)
            self.read_features["features"] = kept
            self.locator_user_rows = max(0, self.locator_user_rows - 1)

    def evaluate(self, expression: str, arg: object = None) -> dict:
        if expression == actions._USER_FEATURE_ROWS_JS:
            if not self.rendered:
                # Mid-reload: the nodes are not in the DOM yet, so the SAME enumeration
                # that later finds them currently finds nothing. Reporting them early
                # would hide the race this double exists to model.
                return {"count": 0, "names": []}
            # Names and count from one node list, nameless nodes included, exactly
            # as `querySelectorAll` returns them.
            return {"count": len(self.dom_rows), "names": list(self.dom_rows)}
        if ".feature-dialog" in expression:
            return dict(self.dialog_values) if self.dialog_visible else {}
        if not self.rendered:
            return {"headerText": "", "features": [], "partsText": "", "partItems": []}
        # A READ is a SNAPSHOT: live it is a fresh DOM query, so returning the
        # page's live dict would let a later delete rewrite a read already taken
        # (and would make the before/after counts of a delete disagree).
        return {
            **self.read_features,
            "features": [dict(row) for row in self.read_features.get("features", [])],
            "partItems": list(self.read_features.get("partItems", [])),
        }

    def wait_for_function(self, expression: str, *, arg: object = None, timeout: float | None = None,
                          polling: object = None) -> bool:
        self.wait_calls.append({"expression": expression, "arg": arg, "timeout": timeout})
        if arg == selectors.PS_FEATURE_DIALOG:
            # A condition poll returns immediately when the condition already holds.
            # Only a dialog that IS on screen and never closes is a timeout: modelling
            # the opposite would make the recovery reload look like a failure.
            if not self.dialog_visible:
                return True
            if not self.dialog_closes:
                raise TimeoutError("dialog stayed open")
            self.dialog_visible = False
            return True
        if isinstance(arg, dict) and arg.get("selector") in (
            selectors.PS_USER_FEATURE,
            selectors.PS_DEFAULT_FEATURE,
        ):
            # The targeted gate the recovery branches use: it is satisfied only once the
            # custom-feature rows exist, so it cannot pass vacuously the way the broad
            # list-item gate below does.
            self.render_polls += 1
            if self.rendered:
                return True
            if self.reload_render_polls >= 0 and self.render_polls >= self.reload_render_polls:
                self.rendered = True
                return True
            raise TimeoutError("the feature rows had not rendered yet")
        if isinstance(arg, dict) and arg.get("selector") == selectors.PARTSTUDIO_FEATURE_ITEM:
            # Deliberately satisfied by ANY list item and therefore also while the feature
            # rows are absent: that is what the live gate did (2736 ms, "waited: true",
            # 0 enumerated rows), and it is why the recovery branches do not use it.
            if self.panel_renders and self.rows:
                return True
            raise TimeoutError("panel never rendered a row")
        return True

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.timeouts.append(milliseconds)

    def reload(self, **kwargs: object) -> None:
        """Model the measured recovery reload.

        Live 2026-09-20 a bounded reload discarded the still-open accepted panel and
        did NOT revert the committed value, so the double drops the panel and keeps
        ``dialog_values`` as they are. It must never be modelled as a rollback.
        ``reload_fails`` models a navigation that does not complete.
        """
        self.reloads.append(dict(kwargs))
        if self.reload_fails:
            raise RuntimeError("navigation refused")
        self.dialog_visible = False
        # A reloaded page renders in stages: with ``reload_render_polls`` > 0 the rows are
        # absent until that many targeted waits have been spent, and a negative value
        # models a page whose rows never arrive.
        self.render_polls = 0
        self.rendered = self.reload_render_polls == 0

    def wait_for_load_state(self, state: str = "load", **kwargs: object) -> bool:
        self.load_states.append(state)
        return True

    def locator(self, selector: str) -> FakeDialogLocator:
        return FakeDialogLocator(self, selector)


class EditFeatureParametersTest(unittest.TestCase):
    """The edit path takes its row NAME and its CLICK INDEX from one enumeration.

    Two live measurements on 2026-09-20, both on the real Windows browser, drove
    this class. First: on a Part Studio whose read listed nine user-feature rows,
    ``page.locator('.os-list-item.ns-user-feature').filter(has_text='Sr Spiral
    ridge 7')`` reported a count other than one for the row that read returned as
    its single match — deterministically, over four attempts and two page reloads.
    Second, after comparing the read against the counting locator instead: the read
    drops a row whose ``innerText`` and ``textContent`` are both empty while the
    locator counts it, so the two counts differed by exactly one on EVERY element
    (1 against 2, 11 against 12) and the tool refused everywhere. A set difference
    is not a page change, so comparing a filtered read with a counting locator can
    never be a valid precondition. Measured after the fix on ``Spiral ridge PS``,
    that nameless node is the LAST of 12 nodes, which is why the double covers both
    orders: the index happened not to shift live, and position is not a contract.

    These tests pin the replacement: names and click index from the same node list,
    the locator count as a staleness check, and both counts reported on disagreement.

    They also pin the two-stage contract. Accepting re-evaluates the model before the
    dialog reports closed, and a one-shot wait measured 61.7 s against a 60 s relay
    limit, so the default apply stage returns on the accept click with
    ``applyState: "pending_verification"`` and ``parametersApplied: None``; the verdict
    belongs to `browser_verify_feature_parameters`, and the constants below are the
    index the target sits at in each layout.
    """

    TARGET = "Sr Spiral ridge 7"
    TARGET_INDEX = 3

    def _edit(self, page: FakeDialogPage, **kwargs) -> dict:
        value = kwargs.pop("value", "12 mm")
        return transactions.edit_feature_parameters(
            page, self.TARGET, {"baseRadius": value}, **kwargs
        )

    def test_a_nameless_node_does_not_shift_the_clicked_row(self):
        """Harder than live: an index from a names-only list would be wrong here."""
        page = FakeDialogPage()
        result = self._edit(page)
        # Four DOM nodes, nameless one first: the target is node 3. An index taken
        # from a names-only list would be 2 and would open a different row.
        self.assertEqual(page.dblclicks, [3], "the apply stage clicks the enumerated row")
        self.assertEqual(result["featureRow"]["featureRows"], ["", *page.rows])
        self.assertEqual(result["featureRow"]["matchedRows"], [self.TARGET])
        self.assertEqual(result["featureRow"]["locatorRows"], 4)
        self.assertTrue(result["featureRow"]["panelReady"]["waited"])
        self.assertTrue(result["pendingVerification"])

    def test_in_the_measured_live_layout_the_nameless_node_is_last(self):
        """Live on Spiral ridge PS the phantom was the LAST of 12 nodes.

        The refused call therefore failed on the count comparison, not on a shifted
        index; this case pins that layout too, so both orders are covered.
        """
        page = FakeDialogPage(nameless_last=True)
        result = self._edit(page)
        self.assertEqual(page.dblclicks, [2])
        self.assertEqual(result["featureRow"]["featureRows"], [*page.rows, ""])
        self.assertEqual(result["featureRow"]["locatorRows"], 4)
        self.assertEqual(result["featureRow"]["matchedRows"], [self.TARGET])
        self.assertTrue(result["pendingVerification"])

    def test_without_a_nameless_node_the_index_is_the_plain_one(self):
        page = FakeDialogPage(nameless_rows=0)
        result = self._edit(page)
        self.assertEqual(page.dblclicks, [2])
        self.assertEqual(result["featureRow"]["featureRows"], page.rows)
        self.assertEqual(result["featureRow"]["locatorRows"], 3)
        self.assertTrue(result["pendingVerification"])

    def test_only_a_page_change_between_the_two_queries_refuses_the_click(self):
        """A DOM change between enumerating and clicking is the only valid refusal."""
        page = FakeDialogPage(locator_delta=1)
        result = self._edit(page)
        self.assertFalse(result["parametersApplied"])
        self.assertEqual(page.dblclicks, [], "no click without agreement")
        self.assertEqual(result["featureRow"]["locatorRows"], 5)
        self.assertEqual(len(result["featureRow"]["featureRows"]), 4)
        self.assertIn("refusing to click", result["reason"])

    def test_a_name_that_matches_nothing_reports_the_rows_it_could_have_matched(self):
        page = FakeDialogPage()
        result = transactions.edit_feature_parameters(page, "Bc", {"baseRadius": "12 mm"})
        self.assertFalse(result["parametersApplied"])
        self.assertEqual(page.dblclicks, [])
        self.assertEqual(result["featureRow"]["matchedRows"], [])
        self.assertIn("matched 0 of 4", result["reason"])
        self.assertEqual(result["featureRow"]["featureRows"], ["", *page.rows])

    def test_a_name_that_matches_several_rows_is_reported_not_guessed(self):
        page = FakeDialogPage(rows=("Sr Spiral ridge 1", "Sr Spiral ridge 2"))
        result = transactions.edit_feature_parameters(page, "Spiral ridge", {"baseRadius": "12 mm"})
        self.assertFalse(result["parametersApplied"])
        self.assertEqual(page.dblclicks, [])
        self.assertIn("matched 2 of 3", result["reason"])
        self.assertEqual(
            result["featureRow"]["matchedRows"], ["Sr Spiral ridge 1", "Sr Spiral ridge 2"]
        )

    def test_the_panel_is_waited_for_before_the_enumeration(self):
        page = FakeDialogPage(rows=(), nameless_rows=0, panel_renders=False)
        result = self._edit(page)
        self.assertFalse(result["parametersApplied"])
        self.assertEqual(page.dblclicks, [])
        self.assertFalse(result["featureRow"]["panelReady"]["waited"])
        self.assertIn("no custom-feature row is on screen", result["reason"])
        self.assertIn("never rendered rows", result["reason"])
        self.assertTrue(
            any(
                isinstance(call["arg"], dict)
                and call["arg"].get("selector") == selectors.PARTSTUDIO_FEATURE_ITEM
                for call in page.wait_calls
            ),
            "the panel readiness wait must query the feature-item selector",
        )

    def test_the_default_apply_stage_returns_before_the_dialog_closes(self):
        """The commit must not be held hostage by a wait that outlives the transport.

        Measured live 2026-09-20: the one-shot form took 61.7 s on an 11-user-feature
        element and the caller got `-32001 downstream_timeout` for a write that had
        very likely been applied. So the default stage returns on the accept click.
        """
        page = FakeDialogPage()
        result = self._edit(page)
        self.assertEqual(page.dblclicks, [self.TARGET_INDEX], "one click: the dialog open")
        self.assertEqual(result["applyState"], "pending_verification")
        self.assertIsNone(result["parametersApplied"], "not known to have failed")
        self.assertTrue(result["pendingVerification"])
        self.assertEqual(result["accept"], {"clicked": True, "waitMs": 0})
        self.assertTrue(result["readbackOk"])
        self.assertEqual(page.timeouts, [], "no blind sleep on the path")
        self.assertEqual(
            [
                call["expression"]
                for call in page.wait_calls
                if call["arg"] == selectors.PS_FEATURE_DIALOG
            ],
            [],
            "the apply stage must not wait for the dialog to close",
        )
        self.assertEqual(
            result["verifyWith"],
            {
                "tool": "browser_verify_feature_parameters",
                "arguments": {
                    "feature_name": self.TARGET,
                    "parameters": {"baseRadius": "12 mm"},
                },
            },
            "the result must carry the exact follow-up call",
        )

    def test_the_one_shot_form_still_waits_and_verifies_when_asked(self):
        page = FakeDialogPage()
        result = self._edit(page, wait_for_regeneration=True)
        self.assertTrue(result["accepted"])
        self.assertTrue(result["accept"]["clicked"])
        self.assertTrue(result["accept"]["waited"])
        self.assertGreaterEqual(result["accept"]["waitMs"], 0)
        self.assertEqual(page.timeouts, [], "the accept step must not sleep")
        self.assertTrue(
            any(call["arg"] == selectors.PS_FEATURE_DIALOG for call in page.wait_calls),
            "the opt-in form must wait on the dialog closing",
        )
        self.assertEqual(page.dblclicks, [self.TARGET_INDEX, self.TARGET_INDEX])
        self.assertTrue(result["readbackOk"])
        self.assertTrue(result["regenerationOk"])
        self.assertTrue(result["persistenceOk"])
        self.assertTrue(result["parametersApplied"])
        self.assertEqual(result["applyState"], "confirmed")
        self.assertFalse(result["pendingVerification"])

    def test_an_accept_that_never_closes_is_evidence_in_the_one_shot_form(self):
        page = FakeDialogPage(dialog_closes=False)
        result = self._edit(page, wait_for_regeneration=True)
        self.assertFalse(result["accepted"])
        self.assertFalse(result["parametersApplied"])
        self.assertEqual(result["applyState"], "failed")
        self.assertFalse(result["accept"]["waited"])
        self.assertIn("timeoutMs", result["accept"])

    def test_a_dialog_that_never_opens_reports_the_row_evidence_too(self):
        page = FakeDialogPage(dialog_opens=False)
        result = self._edit(page)
        self.assertFalse(result["parametersApplied"])
        self.assertIn("feature dialog did not open", result["reason"])
        self.assertEqual(result["featureRow"]["matchedRows"], [self.TARGET])

    def test_a_parameter_field_that_is_not_found_is_reported_as_missing(self):
        page = FakeDialogPage(locator_sees_parameter=False)
        result = self._edit(page)
        self.assertFalse(result["parametersApplied"])
        self.assertEqual(result["missing"], ["baseRadius"])
        self.assertEqual(page.fills, [])
        self.assertEqual(page.accept_clicks, [], "never accept with a field unfilled")

class VerifyFeatureParametersTest(unittest.TestCase):
    """The second stage answers "did the accepted edit stick", and never guesses.

    The fourth live step (2026-09-20) measured the panel's removal as a bimodal
    signal on one feature, with the accept's own before/after as the only variable:
    an accept that changed nothing satisfied the close condition in 4-5 ms, and one
    that changed a parameter had already committed while the panel was still present
    95 s later. So the condition is only a short probe, and the stage then recovers
    with one bounded page reload — the same commit check this repository already uses
    for the insert path. That reload discards the panel without reverting the commit,
    so it is never a rollback. A non-verdict reached after it is
    ``parametersApplied: None`` with ``retryVerify: true``, never a failure, because
    the reload may have raced the commit.
    """

    TARGET = "Sr Spiral ridge 7"

    def _apply_then_verify(self, page: FakeDialogPage, **kwargs) -> tuple[dict, dict]:
        applied = transactions.edit_feature_parameters(
            page, self.TARGET, {"baseRadius": "12 mm"}
        )
        verified = transactions.verify_feature_parameters(
            page, self.TARGET, {"baseRadius": "12 mm"}, **kwargs
        )
        return applied, verified

    def test_it_confirms_regeneration_and_persistence_after_the_dialog_closes(self):
        page = FakeDialogPage()
        applied, verified = self._apply_then_verify(page)
        self.assertTrue(applied["pendingVerification"])
        self.assertTrue(verified["verified"])
        self.assertTrue(verified["parametersApplied"])
        self.assertTrue(verified["dialogClosed"]["waited"])
        self.assertEqual(verified["dialogClosed"]["condition"], "feature_dialog_absent")
        self.assertTrue(verified["regenerationOk"])
        self.assertTrue(verified["persistenceOk"])
        self.assertEqual(verified["persisted"], {"baseRadius": "12 mm"})
        self.assertEqual(
            [row.get("name") for row in verified["featureState"]], [self.TARGET]
        )
        self.assertNotIn("retryVerify", verified)
        self.assertEqual(page.reloads, [], "a closed panel needs no recovery reload")

    def test_a_panel_that_stays_open_without_reload_is_unknown_not_failed(self):
        page = FakeDialogPage(dialog_closes=False)
        _applied, verified = self._apply_then_verify(page, allow_reload=False)
        self.assertFalse(verified["verified"])
        self.assertIsNone(
            verified["parametersApplied"],
            "an unfinished re-evaluation is not a failed edit",
        )
        self.assertIsNone(verified["persistenceOk"])
        self.assertTrue(verified["retryVerify"])
        self.assertFalse(verified["dialogClosed"]["waited"])
        self.assertEqual(verified["featureState"], [], "no row list is read while the dialog is open")
        self.assertEqual(page.reloads, [], "allow_reload=False must never navigate")

    def test_the_measured_stuck_panel_is_recovered_by_one_reload(self):
        """The measured live case: the accept committed and the panel stayed open.

        Live 2026-09-20 a parameter change had committed while `.feature-dialog` was
        still present 95 s later, so the close probe is not a verdict. One bounded
        reload discards the panel without reverting the value, and the stage can then
        read the persisted values and answer.
        """
        page = FakeDialogPage(dialog_closes=False)
        applied, verified = self._apply_then_verify(page)
        self.assertTrue(applied["pendingVerification"])
        self.assertEqual(len(page.reloads), 1, "exactly one bounded recovery reload")
        self.assertEqual(verified["recoveredBy"], "page_reload")
        self.assertTrue(verified["verified"])
        self.assertTrue(verified["parametersApplied"])
        self.assertTrue(verified["persistenceOk"])
        self.assertEqual(verified["persisted"], {"baseRadius": "12 mm"})
        self.assertNotIn("retryVerify", verified)

    def test_a_read_back_right_after_the_recovery_reload_is_not_a_failure(self):
        """The recovery reload can race the commit, so a mismatch stays unknown.

        It is issued seconds after the accept, so the value it reads is the one that
        had persisted when the fresh page loaded. Reporting that as
        `parametersApplied: false` would be exactly the false negative this pass
        exists to remove; it is `None` + `retryVerify` instead.
        """
        page = FakeDialogPage(dialog_closes=False)
        applied = transactions.edit_feature_parameters(
            page, self.TARGET, {"baseRadius": "12 mm"}
        )
        self.assertTrue(applied["readbackOk"])
        page.dialog_values["baseRadius"] = "10 mm"
        verified = transactions.verify_feature_parameters(
            page, self.TARGET, {"baseRadius": "12 mm"}
        )
        self.assertEqual(verified["recoveredBy"], "page_reload")
        self.assertFalse(verified["verified"])
        self.assertIsNone(
            verified["parametersApplied"],
            "a read taken right after the recovery reload may have raced the commit",
        )
        self.assertTrue(verified["retryVerify"])
        self.assertFalse(verified["persistenceOk"])
        self.assertIn("raced the commit", verified["reason"])

    def test_a_recovery_reload_that_does_not_complete_is_unverified(self):
        page = FakeDialogPage(dialog_closes=False, reload_fails=True)
        _applied, verified = self._apply_then_verify(page)
        self.assertFalse(verified["verified"])
        self.assertIsNone(verified["parametersApplied"])
        self.assertTrue(verified["retryVerify"])
        self.assertFalse(verified["recovery"]["reloaded"])
        self.assertIn("did not complete", verified["reason"])

    def test_the_recovery_reload_waits_for_the_rows_before_reading_them(self):
        """Live, the recovery reload read a page whose rows had not rendered yet.

        Measured 2026-09-20 on the real browser: the whole recovery block finished in
        151 ms, enumerated 0 custom-feature rows and answered `retryVerify` even though
        the edit had committed — a second call then read the value fine. The double
        models that page (its broad list-item gate is satisfied while the rows are
        still absent), so this pins that the stage WAITS for the custom-feature rows
        and answers in the same call instead of handing back "call again".
        """
        page = FakeDialogPage(dialog_closes=False, reload_render_polls=1)
        applied, verified = self._apply_then_verify(page)
        self.assertTrue(applied["pendingVerification"])
        self.assertGreaterEqual(page.render_polls, 1, "the stage must wait for the rows")
        self.assertEqual(len(page.reloads), 1, "still exactly one recovery reload")
        self.assertTrue(verified["featureListReady"]["waited"])
        self.assertEqual(verified["featureListReady"]["selector"], selectors.PS_USER_FEATURE)
        self.assertTrue(verified["verified"], "a rendered page must be answered in one call")
        self.assertTrue(verified["parametersApplied"])
        self.assertEqual(verified["persisted"], {"baseRadius": "12 mm"})
        self.assertNotIn("retryVerify", verified)

    def test_a_reload_whose_rows_never_render_is_never_a_failure(self):
        """Waiting must not turn "the page never rendered" into a definitive verdict."""
        page = FakeDialogPage(dialog_closes=False, reload_render_polls=-1)
        _applied, verified = self._apply_then_verify(page)
        self.assertEqual(verified["recoveredBy"], "page_reload")
        self.assertFalse(verified["featureListReady"]["waited"])
        self.assertFalse(verified["verified"])
        self.assertIsNone(
            verified["parametersApplied"],
            "an unrendered page is no evidence either way, not a failed edit",
        )
        self.assertTrue(verified["retryVerify"])
        self.assertIn("raced the commit", verified["reason"])

    def test_a_row_that_did_not_regenerate_cleanly_is_not_confirmed(self):
        page = FakeDialogPage()
        page.read_features = {"headerText": "", "features": [], "partsText": "", "partItems": []}
        _applied, verified = self._apply_then_verify(page)
        self.assertFalse(verified["verified"])
        self.assertIs(
            verified["parametersApplied"],
            False,
            "a cleanly read row list that has no matching row is a definitive failure",
        )
        self.assertFalse(verified["regenerationOk"])
        self.assertFalse(verified["persistenceOk"])
        self.assertIn("did not regenerate cleanly", verified["reason"])

    def test_a_row_renamed_by_its_edit_is_verified_under_its_new_text(self):
        """A templated row prints its values, so a successful edit RENAMES it.

        Measured live 2026-09-21: editing `TV #gf_plate_size = 0 mm` into
        `#gf_pitch * 2` produced the row `TV #gf_plate_size = 84 mm`; the name-only
        lookup then read 0 rows and reported `parametersApplied: false` for an edit that
        had committed. `expect_row` names the text the row must now carry, and the
        verdict is read from THAT row.
        """
        page = FakeDialogPage(
            rows=("TV #gf_pitch = 42 mm", "TV #gf_plate_size = 84 mm")
        )
        page.dialog_values["baseRadius"] = "12 mm"
        verified = transactions.verify_feature_parameters(
            page,
            "TV #gf_plate_size = 0 mm",
            {"baseRadius": "12 mm"},
            expect_row="#gf_plate_size = 84 mm",
        )
        self.assertEqual(verified["rowRenamed"], "TV #gf_plate_size = 84 mm")
        self.assertEqual(verified["verifiedRowName"], "TV #gf_plate_size = 84 mm")
        self.assertTrue(verified["verified"])
        self.assertTrue(verified["parametersApplied"])
        self.assertEqual(verified["persisted"], {"baseRadius": "12 mm"})

    def test_a_renamed_row_is_still_unconfirmed_when_no_new_text_is_stated(self):
        """The old name alone cannot confirm it: there is nothing to read."""
        page = FakeDialogPage(
            rows=("TV #gf_pitch = 42 mm", "TV #gf_plate_size = 84 mm")
        )
        verified = transactions.verify_feature_parameters(
            page, "TV #gf_plate_size = 0 mm", {"baseRadius": "12 mm"}
        )
        self.assertNotIn("rowRenamed", verified)
        self.assertEqual(verified["verifiedRowName"], "TV #gf_plate_size = 0 mm")
        self.assertFalse(verified["verified"])
        self.assertIs(verified["parametersApplied"], False)
        self.assertIn("did not regenerate cleanly", verified["reason"])

    def test_values_that_do_not_survive_the_reopen_are_reported(self):
        page = FakeDialogPage()
        applied = transactions.edit_feature_parameters(
            page, self.TARGET, {"baseRadius": "12 mm"}
        )
        self.assertTrue(applied["readbackOk"])
        # The dialog read back 12 mm, but the persisted value is something else: the
        # stage must report that, not the readback it already saw. The panel closed by
        # itself here, so no recovery reload raced the commit and the verdict is
        # definitive.
        page.dialog_values["baseRadius"] = "10 mm"
        verified = transactions.verify_feature_parameters(
            page, self.TARGET, {"baseRadius": "12 mm"}
        )
        self.assertFalse(verified["verified"])
        self.assertIs(verified["parametersApplied"], False)
        self.assertTrue(verified["regenerationOk"])
        self.assertFalse(verified["persistenceOk"])
        self.assertIn("persisted=", verified["reason"])
        self.assertNotIn("recoveredBy", verified)


class ReadFeatureParametersTest(unittest.TestCase):
    """Reading a feature's values must not write anything.

    The read opens the row's parameter dialog, reads its named fields and cancels it,
    so `fills` and `accept_clicks` must both stay empty. It also refuses to read a
    dialog that is already open, because such a dialog shows what was last TYPED and
    this tool cannot tell that apart from what is persisted.
    """

    TARGET = "Sr Spiral ridge 7"

    def test_it_reads_the_values_and_cancels_without_writing(self):
        page = FakeDialogPage()
        result = transactions.read_feature_parameters(page, self.TARGET)
        self.assertTrue(result["read"])
        self.assertEqual(result["parameters"], {"baseRadius": "10 mm"})
        self.assertEqual(result["parameterCount"], 1)
        self.assertEqual(result["featureName"], self.TARGET)
        self.assertEqual(page.fills, [], "a read must never fill a parameter")
        self.assertEqual(page.accept_clicks, [], "a read must never accept a dialog")
        page.keyboard.press.assert_called_with("Escape")
        self.assertEqual(page.reloads, [], "reading must not navigate")

    def test_an_already_open_dialog_is_refused_rather_than_read(self):
        page = FakeDialogPage(dialog_closes=False, dialog_already_open=True)
        result = transactions.read_feature_parameters(page, self.TARGET)
        self.assertFalse(result["read"])
        self.assertEqual(result["parameters"], {})
        self.assertTrue(result["retryable"])
        self.assertEqual(page.dblclicks, [], "nothing is opened while a panel is on screen")
        self.assertEqual(page.fills, [])
        self.assertEqual(page.reloads, [], "the default refuses to navigate")
        self.assertIn("already open", result["reason"])

    def test_allow_reload_recovers_the_open_panel_before_reading(self):
        page = FakeDialogPage(dialog_closes=False, dialog_already_open=True)
        result = transactions.read_feature_parameters(
            page, self.TARGET, allow_reload=True
        )
        self.assertEqual(len(page.reloads), 1)
        self.assertEqual(result["recovery"]["reloaded"], True)
        self.assertTrue(result["read"])
        self.assertEqual(result["parameters"], {"baseRadius": "10 mm"})
        self.assertEqual(page.fills, [])
        self.assertEqual(page.accept_clicks, [])

    def test_the_read_after_a_recovery_reload_waits_for_the_rows(self):
        """Measured live 2026-09-20: this path's wait was satisfied on the WRONG signal.

        ``wait_for_panel_rows`` counts ``.os-list-item``, which the part list and the tab
        strip also match, so it reported ``waited: True`` after 2736 ms while the
        enumeration still found 0 custom-feature rows. The recovery branch must wait for
        the rows it is about to read.
        """
        page = FakeDialogPage(
            dialog_closes=False, dialog_already_open=True, reload_render_polls=1
        )
        result = transactions.read_feature_parameters(
            page, self.TARGET, allow_reload=True
        )
        self.assertGreaterEqual(page.render_polls, 1, "it must wait for the rows")
        self.assertTrue(result["featureListReady"]["waited"])
        self.assertEqual(result["featureListReady"]["selector"], selectors.PS_USER_FEATURE)
        self.assertTrue(result["read"])
        self.assertEqual(result["parameters"], {"baseRadius": "10 mm"})

    def test_a_recovery_reload_without_rendered_rows_reads_nothing(self):
        page = FakeDialogPage(
            dialog_closes=False, dialog_already_open=True, reload_render_polls=-1
        )
        result = transactions.read_feature_parameters(
            page, self.TARGET, allow_reload=True
        )
        self.assertFalse(result["read"])
        self.assertFalse(result["featureListReady"]["waited"])
        self.assertEqual(result["parameters"], {})
        self.assertEqual(result["parameterCount"], 0)
        self.assertEqual(page.fills, [], "an unreadable page must not be filled")
        self.assertIn("no custom-feature row is on screen", result["reason"])
        # "the row is not there after a bounded wait" is a definitive negative for this
        # element, so it is deliberately NOT marked retryable (only an open panel or an
        # incomplete reload are).
        self.assertNotIn("retryable", result)

    def test_a_row_that_cannot_be_located_reads_nothing_and_says_so(self):
        page = FakeDialogPage(rows=("Sr Spiral ridge 1",))
        result = transactions.read_feature_parameters(page, self.TARGET)
        self.assertFalse(result["read"])
        self.assertEqual(result["parameters"], {})
        self.assertEqual(page.dblclicks, [])
        self.assertIn("matched", result["reason"])


    def test_the_row_is_never_identified_by_a_text_filter(self):
        """One enumeration; a filtered read is never compared with a counting locator."""
        source = Path(transactions.__file__).read_text(encoding="utf-8")
        self.assertNotIn("filter(has_text=feature_name)", source)
        locator_source = source.split("def _locate_feature_row", 1)[1].split("\ndef ", 1)[0]
        # Drop the docstring: it deliberately NAMES the two defects it documents,
        # so only the executable body may carry the invariant.
        body = locator_source.rsplit('"""', 1)[-1]
        self.assertIn("rows.nth(", body)
        self.assertIn("enumerate_user_feature_rows", body)
        self.assertIn("match_user_feature_row_indices", body)
        self.assertNotIn(
            "read_partstudio_features",
            body,
            "a read that FILTERS nameless rows and a locator that COUNTS them are "
            "different sets; comparing them refused on every element live",
        )

    def test_the_row_enumeration_walks_a_virtualised_feature_list(self):
        """A windowed Feature List hides the tail from every name-addressed tool.

        Measured live 2026-09-21 on a 25-row thin chain: the Feature List header read
        `特征 (29)` while one `querySelectorAll` pass returned exactly the first 18
        rows, so a stray row near the bottom could be neither read nor deleted (both
        resolve through this enumeration) and a reload that re-rendered the top looked
        like rows vanishing. The collector must therefore also scroll the row list.
        """
        js = actions._USER_FEATURE_ROWS_JS
        self.assertTrue(js.lstrip().startswith("async ({selector})"), js[:40])
        self.assertIn("scrollHeight - walk.clientHeight", js)
        self.assertIn("container.scrollTop = origin", js)
        self.assertIn("setTimeout", js)
        # Bounded: a computed limit and a step loop, never an open-ended wait.
        self.assertIn("for (let top = 0; top <= limit; top += step)", js)

    def test_a_single_pass_answer_keeps_its_old_shape(self):
        class _Page:
            def __init__(self, answer):
                self.answer = answer

            def evaluate(self, expression, arg=None):
                return self.answer

        plain = actions.enumerate_user_feature_rows(_Page({"count": 2, "names": ["A", "B"]}), "sel")
        self.assertEqual(plain, {"count": 2, "names": ["A", "B"]})
        scrolled = actions.enumerate_user_feature_rows(
            _Page({"count": 3, "names": ["A", "B", "C"], "scrolled": True}), "sel"
        )
        self.assertEqual(scrolled, {"count": 3, "names": ["A", "B", "C"], "scrolled": True})

    def test_a_row_below_the_rendered_window_is_scrolled_into_view(self):
        """The click layer indexes RENDERED rows, so a tail row must be rendered first.

        Live 2026-09-21: a 26-row thin chain rendered 18 rows, the enumeration saw all
        26 (after the scroll pass), and the old count comparison refused every tail row
        -- which is what made the two stray rows of that chain undeletable.
        """
        page = _WindowedRowPage(["TE Thin Extrude 1", "TE Thin Extrude 2", "TE Thin Extrude 3"], window=2)
        row, evidence = transactions._locate_feature_row(page, "TE Thin Extrude 3")
        self.assertIsNotNone(row)
        self.assertEqual(page.scrolls, ["TE Thin Extrude 3"])
        self.assertEqual(evidence["locatorRows"], 2, "only the window is rendered")
        self.assertEqual(evidence["featureRows"], page.rows, "the enumeration walks the list")
        self.assertTrue(evidence["rowScroll"]["found"])
        self.assertEqual(evidence["rowScroll"]["steps"], 2)
        row.click(button="right")
        self.assertEqual(page.clicks, [(1, "right")], "the index is the RENDERED one")

    def test_a_windowed_row_that_never_renders_is_still_refused(self):
        page = _WindowedRowPage(
            ["TE Thin Extrude 3", "TE Thin Extrude 4", "TE Thin Extrude 5"], window=1
        )
        row, evidence = transactions._locate_feature_row(page, "TE Thin Extrude 4")
        self.assertIsNone(row)
        self.assertEqual(page.clicks, [])
        self.assertIn("refusing to click a row that may be a different one", evidence["reason"])
        self.assertIn("no unique rendered match", evidence["reason"])


class _WindowedRowPage:
    """A Feature List that renders only its first ``window`` rows.

    Live-observed shape: the page enumeration walks the scroll container and sees every
    row, while ``page.locator('.os-list-item.ns-user-feature').count()`` reports only the
    rows the pane has rendered.
    """

    def __init__(self, rows, window=2):
        self.rows = list(rows)
        self.window = window
        self.scrolls: list[str] = []
        self.clicks: list[tuple[int, str]] = []

    def evaluate(self, expression, arg=None):
        if expression == actions._USER_FEATURE_ROWS_JS:
            return {"count": len(self.rows), "names": list(self.rows), "scrolled": True}
        if expression == actions._SCROLL_TO_USER_FEATURE_ROW_JS:
            wanted = str((arg or {}).get("wanted", ""))
            self.scrolls.append(wanted)
            if wanted == self.rows[-1] and len(self.rows) > self.window:
                rendered = [self.rows[-2], self.rows[-1]]
                return {
                    "found": True, "index": 1, "name": wanted, "rendered": rendered,
                    "scrolled": True, "steps": 2,
                }
            return {
                "found": False, "rendered": self.rows[: self.window], "scrolled": True,
                "steps": 3, "reason": "no unique rendered match at any scroll position",
            }
        raise AssertionError(f"unexpected evaluate: {expression.strip()[:60]}")

    def wait_for_function(self, expression, *, arg=None, timeout=None, polling=None):
        return True

    def locator(self, selector):
        return _WindowedRows(self)


class _WindowedRows:
    def __init__(self, page):
        self.page = page

    def count(self):
        return min(self.page.window, len(self.page.rows))

    def nth(self, index):
        page = self.page

        class _Row:
            def click(self, button=None):
                page.clicks.append((index, button))

        return _Row()


if __name__ == "__main__":
    unittest.main()


class DeleteFeatureTest(unittest.TestCase):
    """Deleting a feature row is an exact-identity transaction, or a refusal.

    The row exists because a live insert can be reported as a relay timeout while
    its accept HAD landed (measured 2026-09-21), and nothing else in the tool set
    removes a feature row: the REST feature-list update spends annual quota and a
    reload or rename changes nothing. So the destructive path has to be at least as
    strict as the edit path, and it is: one enumeration supplies both the name and
    the click index, the delete item must be unique in a bounded label ladder, and
    the verdict is the NAME leaving the list.
    """

    ROWS = ("TV #gf_pitch = 42 mm", "TE Thin Extrude 5", "TE Thin Extrude 6")

    def page(self, **kwargs) -> FakeDialogPage:
        kwargs.setdefault("rows", self.ROWS)
        # One nameless node FIRST is the strictly harder layout: the click index
        # must still address the row the enumeration named.
        kwargs.setdefault("nameless_rows", 1)
        return FakeDialogPage(**kwargs)

    def delete(self, page: FakeDialogPage, name: str = "TE Thin Extrude 6", **kwargs):
        return transactions.delete_feature(page, name, **kwargs)

    def test_the_named_row_is_deleted_and_verified_by_name(self) -> None:
        page = self.page()
        result = self.delete(page)
        self.assertTrue(result["deleted"])
        self.assertEqual(result["matchedName"], "TE Thin Extrude 6")
        self.assertEqual(result["rowIndex"], 3)
        self.assertEqual(result["matchedRows"], ["TE Thin Extrude 6"])
        self.assertEqual(result["matchedItem"], "删除")
        self.assertIn("删除", result["menuItems"])
        self.assertEqual(result["rowCountBefore"], 3)
        self.assertEqual(result["rowCountAfter"], 2)
        self.assertEqual(len(result["featureRows"]), 4, "the enumeration keeps the nameless node")
        self.assertNotIn("TE Thin Extrude 6", result["afterRows"])
        self.assertIn("TE Thin Extrude 5", result["afterRows"])
        self.assertEqual(result["removal"]["condition"], "user_feature_row_absent")
        self.assertTrue(result["removal"]["waited"])
        # The index came from the enumeration, and it is the row that was clicked.
        self.assertEqual(page.right_clicks, [{"index": 3, "button": "right"}])
        self.assertEqual(page.menu_clicks, ["删除"])

    def test_the_row_is_clicked_at_its_enumerated_position(self) -> None:
        """A nameless node ahead of it must not shift the click onto a row above."""
        page = self.page(nameless_last=False)
        self.delete(page, "TE Thin Extrude 5")
        self.assertEqual(page.right_clicks[0]["index"], 2)
        self.assertNotIn("TE Thin Extrude 5", page.dom_rows)
        self.assertIn("TE Thin Extrude 6", page.dom_rows)

    def test_a_menu_without_a_delete_label_refuses_and_reports_the_labels(self) -> None:
        page = self.page(menu_labels=("编辑", "抑制", "重命名", "回退"))
        result = self.delete(page)
        self.assertFalse(result["deleted"])
        self.assertEqual(result["menuItems"], ["编辑", "抑制", "重命名", "回退"])
        self.assertEqual(page.menu_clicks, [], "nothing may be clicked without a delete item")
        self.assertIn("no unique visible delete item", result["reason"])
        self.assertIn("回退", result["reason"])
        self.assertIn("TE Thin Extrude 6", page.dom_rows)

    def test_two_identical_rows_are_refused_rather_than_guessed(self) -> None:
        """Thin rows repeat: two rows can carry the very same parameters."""
        page = self.page(rows=("TE Thin Extrude 5", "TE Thin Extrude 5"))
        result = self.delete(page, "TE Thin Extrude 5")
        self.assertFalse(result["deleted"])
        self.assertEqual(result["exactMatchCount"], 2)
        self.assertIn("matched 2 of", result["reason"])
        self.assertEqual(page.right_clicks, [])
        self.assertIn("matched 2 of 3 custom-feature rows", result["reason"])

    def test_an_occurrence_selects_one_of_two_identical_rows(self) -> None:
        """A shared name is addressable when the caller says WHICH row it means.

        Measured live 2026-09-21: an interrupted run and its resume both landed the
        same ``Thin Variable`` insert, so the element held two textually identical
        ``TV #gf_lock = 37.7 mm 锁定面方孔边长`` rows and no name-addressed tool could
        remove either. The occurrence is the caller's statement; the row it selects is
        still verified by name, and the removal verdict becomes a COUNT because
        deleting one of two identical rows leaves the name in the list.
        """
        page = self.page(rows=("TE Thin Extrude 5", "TE Thin Extrude 5"))
        result = self.delete(page, "TE Thin Extrude 5", occurrence=2)
        self.assertTrue(result["deleted"])
        self.assertEqual(result["occurrence"], 2)
        self.assertEqual(result["matchedIndex"], 2)
        self.assertEqual(result["matchedName"], "TE Thin Extrude 5")
        self.assertEqual(result["rowIndex"], 2)
        self.assertEqual(page.right_clicks, [{"index": 2, "button": "right"}])
        self.assertEqual(result["removal"]["condition"], "user_feature_row_count_below")
        self.assertEqual(result["nameCountBefore"], 2)
        self.assertEqual(result["nameCountAfter"], 1)
        self.assertEqual(
            page.dom_rows.count("TE Thin Extrude 5"), 1,
            "one of the two identical rows is left in place",
        )

    def test_an_occurrence_beyond_the_matches_is_refused(self) -> None:
        """A caller asking for a row that is not there must not get a different one."""
        page = self.page(rows=("TE Thin Extrude 5", "TE Thin Extrude 5"))
        result = self.delete(page, "TE Thin Extrude 5", occurrence=3)
        self.assertFalse(result["deleted"])
        self.assertEqual(page.right_clicks, [])
        self.assertIn("fewer than the 3 occurrence(s) requested", result["reason"])
        self.assertEqual(page.dom_rows.count("TE Thin Extrude 5"), 2)

    def test_the_scroll_probe_asks_for_the_requested_occurrence(self) -> None:
        """Below the rendered window a duplicated name must be reachable by occurrence.

        The occurrence is passed into the in-page walk, not applied afterwards: only the
        walk knows how many matches a given scroll position renders, so it is what has to
        decide when the wanted occurrence is on screen.
        """

        class _Probe:
            def __init__(self) -> None:
                self.calls: list[dict] = []

            def evaluate(self, expression, arg=None):
                self.calls.append(arg)
                assert expression is actions._SCROLL_TO_USER_FEATURE_ROW_JS
                return {
                    "found": True, "index": 3, "name": "TV #dup = 1 mm", "matches": 2,
                    "rendered": ["a", "b", "TV #dup = 1 mm", "TV #dup = 1 mm"],
                    "scrolled": True, "steps": 4,
                }

        page = _Probe()
        answer = actions.scroll_to_user_feature_row(
            page, selectors.PS_USER_FEATURE, "TV #dup = 1 mm", occurrence=2
        )
        self.assertEqual(
            page.calls,
            [{"selector": selectors.PS_USER_FEATURE, "wanted": "TV #dup = 1 mm",
              "occurrence": 2}],
        )
        self.assertTrue(answer["found"])
        self.assertEqual(answer["index"], 3)
        self.assertEqual(answer["matches"], 2)
        self.assertEqual(answer["occurrence"], 2)
        self.assertIn("occurrence", actions._SCROLL_TO_USER_FEATURE_ROW_JS)

    def test_a_name_that_matches_nothing_still_names_the_rows(self) -> None:
        page = self.page()
        result = self.delete(page, "TE Thin Extrude 9")
        self.assertFalse(result["deleted"])
        self.assertIn("TE Thin Extrude 5", result["userRows"])
        self.assertIn("TE Thin Extrude 6", result["userRows"])
        self.assertEqual(result["exactMatchCount"], 0)
        self.assertEqual(page.right_clicks, [])

    def test_a_stale_enumeration_refuses_instead_of_clicking_a_different_row(self) -> None:
        """The locator re-queries the page, so a disagreement is not clicked through."""
        page = self.page(locator_delta=1)
        result = self.delete(page)
        self.assertFalse(result["deleted"])
        self.assertEqual(page.right_clicks, [])
        self.assertIn("refusing to click a row that may be a different one", result["reason"])

    def test_an_open_parameter_dialog_is_refused(self) -> None:
        """Its accept button shares the selector a delete confirmation uses."""
        page = self.page(dialog_already_open=True)
        result = self.delete(page)
        self.assertFalse(result["deleted"])
        self.assertEqual(page.right_clicks, [])
        self.assertIn("Parameter dialog is open", result["reason"])

    def test_a_menu_that_never_opens_is_reported(self) -> None:
        page = self.page(menu_opens=False)
        result = self.delete(page)
        self.assertFalse(result["deleted"])
        self.assertFalse(result["contextMenuOpened"])
        self.assertEqual(result["menuItems"], [])
        self.assertEqual(page.menu_clicks, [])

    def test_a_row_that_survives_the_removal_wait_is_not_a_delete(self) -> None:
        page = self.page(deletes_row=False)
        result = self.delete(page, timeout_ms=1)
        self.assertFalse(result["deleted"])
        self.assertFalse(result["removal"]["waited"])
        self.assertEqual(result["stillListedNames"], ["TE Thin Extrude 6"])
        self.assertIn("is still in the feature list", result["reason"])
        self.assertTrue(page.timeouts, "the removal wait polls instead of sleeping once")

    def test_a_confirmation_dialog_is_accepted_when_one_appears(self) -> None:
        page = self.page(confirm_dialog=True)
        outcome = self.delete(page)
        self.assertTrue(outcome["deleted"])
        self.assertEqual(outcome["confirmDialog"], {"present": True, "clicked": True})
        self.assertEqual(page.confirm_clicks, ["accept"])
