"""Zero-quota browser interference detection for Onshape Assemblies (issue #20).

This module drives the Onshape **Interference Detection** panel through the live
page (Playwright sync ``page``), spending **0 Onshape REST API requests**. It is
strictly read-only with respect to the model: it switches to an assembly tab, opens
the analysis panel, runs the detection, reads the reported pairs back, restores the
panel, and saves nothing. It is NOT assembly constraint solving: no mate, no
constraint, no fix/group, and no save button is ever touched -- the only cloud-visible
effect is the panel being opened and closed again.

WHAT IS REUSED, NOT REBUILT
===========================
The project already owns an assembly automation layer, and this module reuses it
instead of growing a second one:

* the tab list comes from :func:`onshape_browser_mode.actions.list_document_tabs`;
* the tab switch and the assembly readiness wait come from
  :func:`onshape_browser_mode.semantic._open_tab` (which waits for
  ``selectors.ASM_INSERT_BUTTON`` -- the assembly toolbar -- before returning true),
  with :func:`onshape_browser_mode.actions.activate_tab` as the by-``data-id``
  fallback and as the by-id path;
* every assembly selector value lives in ``onshape_browser_mode/selectors.py``
  (``ASM_*`` / ``ANALYSIS_*``), and the failure shape follows ``semantic.py``'s
  ``{"<outcome>": False, ..., "reason": ...}`` convention for the internal steps and
  a top-level ``reason`` on the result;
* the bounded-wait contract mirrors ``actions.partstudio_wait_budget_ms``.

There is **no existing code that opens the interference panel**: `semantic.py`
contains instance insertion and the fix/group context actions only. That gap is what
this module fills, and the report that accompanies it names that fact.

OFFLINE-PREPARED AND ONLY PARTLY VERIFIED
=========================================
Two live anchors exist and every anchor is labelled in
:data:`SELECTOR_PROVENANCE`:

* ``button.analysis-button`` / ``.analysisControlPopup`` and the popup item text
  ``干涉检测…`` -- measured live 2026-08-25 in ``dev/button-map/scan-app-shell.json``.
  Honest gap: that scan was taken in a **Part Studio**, so it proves the entry label,
  not the assembly path and not the panel's DOM.
* ``.ns-tree-root`` / ``.ns-tree-root .ns-assembly-instance-row.is-instance`` /
  ``.assemblyTreeName.os-list-item-name`` -- measured live 2026-08-21 in
  ``dev/button-map/scan-assembly-instances.json``.

The panel root, its tolerance input, its compute control, its result rows, its
empty-state text and its close control are **UNVERIFIED**. The response is not to
guess harder but to make the guess observable: all DOM interaction lives in
:data:`SELECTORS` plus two small read-only probes (:func:`_read_tabs` /
:func:`_probe_page`, and :func:`_read_panel`) that return **what the page actually
shows** -- active tab name, tab list, tab element types, whether an assembly
environment is mounted, the analysis popup's item texts, the visible toolbar texts,
and every short node whose text carries an interference keyword. When a selector
misses, the result carries those observations instead of a guess or a silent
``clean``.

VERDICT RULE (the point of the tool)
====================================
``clean`` is allowed ONLY when the panel was demonstrably present, the detection
demonstrably completed (a completion proof exists -- a stated count, an explicit
empty statement, or a run observed in progress that then settled), and the result
read back is zero pairs. A missing panel, a detection that never finished, a
timeout, an empty read with no completion proof, or a page that is not an assembly
all produce ``indeterminate`` (or ``unavailable`` when the target tab simply is not
an assembly) with a ``failureClass`` and the page facts observed at that moment.

This module deliberately imports no Playwright: it is importable, and fully
testable, without a browser.
"""

from __future__ import annotations

import re
import time
from typing import Any, Callable, Iterable, Sequence

from onshape_browser_mode import actions, selectors

# ---------------------------------------------------------------------------
# Verdicts and failure classes
# ---------------------------------------------------------------------------

VERDICT_CLEAN = "clean"
VERDICT_INTERFERENCE = "interference"
VERDICT_INDETERMINATE = "indeterminate"
VERDICT_UNAVAILABLE = "unavailable"

FAILURE_NONE = ""
FAILURE_PAGE_PROBE_FAILED = "page_probe_failed"
FAILURE_TAB_NOT_FOUND = "tab_not_found"
FAILURE_TAB_SWITCH_FAILED = "tab_switch_failed"
FAILURE_NOT_ASSEMBLY = "not_assembly"
FAILURE_PANEL_UNAVAILABLE = "panel_unavailable"
FAILURE_TOLERANCE_NOT_APPLIED = "tolerance_not_applied"
FAILURE_DETECTION_NOT_COMPLETED = "detection_not_completed"
FAILURE_EMPTY_WITHOUT_COMPLETION_PROOF = "empty_without_completion_proof"
FAILURE_RESULT_UNREADABLE = "result_unreadable"
FAILURE_PART_FILTER_EXCLUDED_ALL = "part_filter_excluded_all"
FAILURE_PANEL_RESTORE_FAILED = "panel_restore_failed"

#: Non-blocking failure classes: recorded in ``failures`` but not by themselves a
#: reason to withhold a verdict (the measurement already happened; only the
#: courtesy restore is affected).
NON_BLOCKING_FAILURES = frozenset({FAILURE_PANEL_RESTORE_FAILED})

# ---------------------------------------------------------------------------
# The one DOM layer: a selector map over selectors.py plus provenance
# ---------------------------------------------------------------------------

#: Every raw DOM string this module uses, in one place. The VALUES live in
#: ``onshape_browser_mode/selectors.py`` (the repo's single source of truth); this
#: map is the one layer that says which of them this operation touches. A miss on
#: any of them is reported as an observation, never swallowed.
SELECTORS: dict[str, str] = {
    # -- verified live ------------------------------------------------------
    "analysisButton": selectors.ANALYSIS_BUTTON,
    "analysisPopup": selectors.ANALYSIS_POPUP,
    "assemblyTreeRoot": ".ns-tree-root",
    "assemblyInstanceRow": selectors.ASM_INSTANCE_ROW,
    "assemblyInstanceName": ".assemblyTreeName.os-list-item-name",
    "assemblyInsertButton": selectors.ASM_INSERT_BUTTON,
    "tabBarTab": selectors.TAB_BAR_TAB,
    "tabName": selectors.TAB_NAME,
    # -- UNVERIFIED: the assembly interference panel ------------------------
    "analysisPopupItem": selectors.ANALYSIS_POPUP_ITEM,
    "assemblyToolbarItem": selectors.ASM_TOOLBAR_ITEM,
    "panelRoot": selectors.ASM_INTERFERENCE_PANEL,
    "panelInput": selectors.ASM_INTERFERENCE_INPUT,
    "panelButton": selectors.ASM_INTERFERENCE_BUTTON,
    "panelResultRow": selectors.ASM_INTERFERENCE_ROW,
    "panelClose": selectors.ASM_INTERFERENCE_CLOSE,
    "panelToleranceInput": selectors.ASM_INTERFERENCE_INPUT,
    "progress": selectors.ASM_PROGRESS,
}

#: Provenance for every key above. ``verified-live-<date>`` names the on-disk scan
#: that measured it; ``UNVERIFIED`` means no live observation supports it yet.
SELECTOR_PROVENANCE: dict[str, str] = {
    "analysisButton": "verified-live-2026-08-25 (dev/button-map/scan-app-shell.json, Part Studio)",
    "analysisPopup": "verified-live-2026-08-25 (dev/button-map/scan-app-shell.json, Part Studio)",
    "assemblyTreeRoot": "verified-live-2026-08-21 (dev/button-map/scan-assembly-instances.json)",
    "assemblyInstanceRow": "verified-live-2026-08-21 (dev/button-map/scan-assembly-instances.json)",
    "assemblyInstanceName": "verified-live-2026-08-21 (dev/button-map/scan-assembly-instances.json)",
    "assemblyInsertButton": "verified-live-2026-08-21 (dev/button-map/scan-assembly-instances.json)",
    "tabBarTab": "verified-live-2026-09-20 (onshape_browser_mode/selectors.py)",
    "tabName": "verified-live-2026-09-20 (onshape_browser_mode/selectors.py)",
    "analysisPopupItem": "UNVERIFIED",
    "assemblyToolbarItem": "UNVERIFIED",
    "panelRoot": "UNVERIFIED",
    "panelInput": "UNVERIFIED",
    "panelButton": "UNVERIFIED",
    "panelResultRow": "UNVERIFIED",
    "panelClose": "UNVERIFIED",
    "panelToleranceInput": "UNVERIFIED",
    "progress": "UNVERIFIED",
}

#: Keywords that must appear in the panel's own text for it to be recognised as
#: the interference panel. Verified as MENU ITEM TEXT in the Part Studio analysis
#: popup (2026-08-25); using it as a panel anchor is a design decision.
INTERFERENCE_KEYWORDS: tuple[str, ...] = ("干涉", "interference", "clash", "collision")

#: Texts that identify the interference entry. A bounded ladder; the first verified
#: one is ``干涉检测…`` (2026-08-25 scan).
INTERFERENCE_MENU_TEXTS: tuple[str, ...] = (
    "干涉检测",
    "干涉检测…",
    "Interference detection",
    "Interference detection…",
    "干涉检查",
    "Interference check",
)

#: Texts that identify the panel's compute/run control. UNVERIFIED.
RUN_BUTTON_TEXTS: tuple[str, ...] = (
    "计算",
    "重新计算",
    "检测",
    "运行",
    "Compute",
    "Calculate",
    "Recompute",
    "Run",
    "Check",
)

#: Texts that indicate a run is in progress. UNVERIFIED.
PROGRESS_TEXT_MARKERS: tuple[str, ...] = (
    "计算中",
    "检测中",
    "正在计算",
    "calculating",
    "computing",
    "checking",
)

#: A stated result count is a completion proof: the panel says how many
#: interferences it found, so a run demonstrably finished. UNVERIFIED patterns.
SUMMARY_COUNT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(\d+)\s*(?:处|个|对|条)?\s*(?:干涉|冲突|clash(?:es)?|interference(?:s)?)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:干涉|冲突|clash(?:es)?|interference(?:s)?)\s*[:：]?\s*(\d+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(\d+)\s*(?:interfering|colliding)\s*(?:parts?|instances?|pairs?)",
        re.IGNORECASE,
    ),
)

#: An explicit empty-result statement is also a completion proof. UNVERIFIED.
EMPTY_TEXT_MARKERS: tuple[str, ...] = (
    "未检测到干涉",
    "没有干涉",
    "无干涉",
    "未发现干涉",
    "未检测到冲突",
    "no interference",
    "no interferences",
    "no clash",
    "no clashes",
    "0 处干涉",
    "0处干涉",
    "0 interference",
    "0 clash",
)

#: Markers that a listed pair is a zero-volume contact rather than a volumetric
#: overlap. UNVERIFIED.
ZERO_VOLUME_MARKERS: tuple[str, ...] = (
    "零体积",
    "体积为 0",
    "体积为0",
    "仅接触",
    "只接触",
    "zero volume",
    "zero-volume",
    "touch only",
    "contact only",
)

#: Separators tried, in order, when splitting one pair's raw row text into two
#: entity display names. A bounded ladder because the panel's row format is
#: unverified; an unparseable row keeps its raw text and reports
#: ``namesParsed: false`` rather than inventing names.
PAIR_NAME_SEPARATORS: tuple[str, ...] = (
    "↔",
    "⇔",
    "<->",
    " - ",
    " – ",
    " — ",
    " vs ",
    " 和 ",
    " 与 ",
    ", ",
    "; ",
    "\t",
    " | ",
)

#: Volume units accepted when reading an intersection volume out of a row.
_VOLUME_PATTERN = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)\s*"
    r"(?P<unit>mm\^?3|mm³|cm\^?3|cm³|in\^?3|in³|m\^?3|m³|"
    r"立方毫米|立方厘米|立方英寸|cubic (?:millimeters?|centimeters?|inches?|meters?))",
    re.IGNORECASE,
)

PLAN_OPERATION = "browser-interference-check"

# ---------------------------------------------------------------------------
# Bounded waits
# ---------------------------------------------------------------------------

#: How long the analysis popup, the panel, or the assembly readiness may take to
#: render. Fixed, because these bound a *render*, not a kernel computation -- the
#: same reasoning as PARTSTUDIO_PANEL_READY_TIMEOUT_MS in
#: ``onshape_browser_mode.actions`` (and ``semantic._open_tab``'s own 30 s wait).
PANEL_OPEN_TIMEOUT_MS = 15_000
PANEL_MENU_TIMEOUT_MS = 8_000
PANEL_CLOSE_TIMEOUT_MS = 5_000
TAB_ACTIVATE_TIMEOUT_MS = 20_000

#: Poll interval for the read-driven waits (panel appearing, detection finishing,
#: panel closing). Short enough to notice an instant result, long enough not to
#: hammer the DOM.
PANEL_POLL_MS = 250
DETECTION_POLL_MS = 500

#: The detection wait scales with the assembly's instance count: an interference
#: check costs roughly a fixed part plus a part proportional to the number of
#: instance pairs the kernel must test. Mirrors ``actions.partstudio_wait_budget_ms``
#: -- a fixed budget gets *thinner* as the assembly grows, and the direction it
#: would fail in is a completed detection reported as a timeout. An unreadable
#: instance count is treated as 0, which reproduces the floor exactly rather than
#: silently extending the budget.
DETECTION_WAIT = {"baseMs": 20_000, "perInstanceMs": 250, "maxMs": 180_000}


def detection_wait_budget_ms(profile: dict[str, int], instance_count: Any) -> int:
    """Scale one detection wait budget with the assembly's instance count."""
    try:
        count = int(instance_count)
    except (TypeError, ValueError):
        count = 0
    count = max(0, count)
    budget = int(profile["baseMs"]) + int(profile["perInstanceMs"]) * count
    return min(int(profile["maxMs"]), budget)


def _budgets(instance_count: Any) -> dict[str, Any]:
    """The complete explainable budget picture, recorded in every result."""
    basis = instance_count if isinstance(instance_count, int) else None
    return {
        "panelOpenTimeoutMs": PANEL_OPEN_TIMEOUT_MS,
        "panelMenuTimeoutMs": PANEL_MENU_TIMEOUT_MS,
        "panelCloseTimeoutMs": PANEL_CLOSE_TIMEOUT_MS,
        "tabActivateTimeoutMs": TAB_ACTIVATE_TIMEOUT_MS,
        "panelPollMs": PANEL_POLL_MS,
        "detectionPollMs": DETECTION_POLL_MS,
        "detectionWaitProfile": dict(DETECTION_WAIT),
        "instanceCountBasis": basis,
        "detectionWaitMs": detection_wait_budget_ms(DETECTION_WAIT, instance_count),
        "basis": (
            "panel/menu/close/tab budgets bound a UI render and are fixed; the detection "
            "budget is baseMs + perInstanceMs * assembly instance count, capped at maxMs "
            "(the same scaling contract as actions.partstudio_wait_budget_ms)"
        ),
    }


def unverified_selector_keys() -> list[str]:
    """Selector keys no live observation supports yet. Reported by the plan."""
    return sorted(
        key
        for key, provenance in SELECTOR_PROVENANCE.items()
        if not provenance.startswith("verified-live")
    )


# ---------------------------------------------------------------------------
# The read-only DOM layer
# ---------------------------------------------------------------------------
#
# The probes ONLY read and return page facts. They contain no verdict logic, so
# every judgment in this module is exercised offline by the tests; the probes
# themselves can only be validated on a real page (see the acceptance checklist in
# the final report).

_JS_PROBE = r"""
/* interference:probe */
(payload) => {
  const selectors = (payload && payload.selectors) || {};
  const keywords = (payload && payload.keywords) || [];
  const norm = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const textOf = (el) => {
    if (!el) return '';
    try { return norm(el.innerText || el.textContent); } catch (e) { return ''; }
  };
  const visible = (el) => {
    if (!el) return false;
    try {
      const rect = el.getBoundingClientRect();
      if (!(rect.width > 0 && rect.height > 0)) return false;
      const style = window.getComputedStyle(el);
      return style.visibility !== 'hidden' && style.display !== 'none';
    } catch (e) {
      return false;
    }
  };
  const queryAll = (selector) => {
    if (!selector) return [];
    try { return Array.from(document.querySelectorAll(selector)); } catch (e) { return []; }
  };
  const snippet = (value, limit) => {
    const text = norm(value);
    const cap = limit || 240;
    return text.length > cap ? text.slice(0, cap) + '…' : text;
  };
  const lowered = keywords.map((word) => String(word).toLowerCase());
  const hasKeyword = (value) => {
    const text = String(value || '').toLowerCase();
    return lowered.some((word) => word && text.includes(word));
  };

  const instanceRows = queryAll(selectors.assemblyInstanceRow);
  const analysisButtons = queryAll(selectors.analysisButton);
  const popups = queryAll(selectors.analysisPopup);
  const insertButtons = queryAll(selectors.assemblyInsertButton);

  const keywordNodes = [];
  const allNodes = document.querySelectorAll('body *');
  for (let index = 0; index < allNodes.length && keywordNodes.length < 25; index += 1) {
    const el = allNodes[index];
    if (el.children.length > 6) continue;
    const text = textOf(el);
    if (!text || text.length > 300) continue;
    if (!hasKeyword(text)) continue;
    keywordNodes.push({
      tag: el.tagName.toLowerCase(),
      cls: (typeof el.className === 'string' ? el.className : '').slice(0, 120),
      visible: visible(el),
      text: snippet(text, 300),
    });
  }

  return {
    pageUrl: (typeof location !== 'undefined' && location.href) || '',
    title: (typeof document !== 'undefined' && document.title) || '',
    assembly: {
      treeRootCount: queryAll(selectors.assemblyTreeRoot).length,
      instanceRowCount: instanceRows.length,
      visibleInstanceRowCount: instanceRows.filter(visible).length,
      instanceNames: instanceRows.slice(0, 200).map((el) => {
        const nameEl = el.querySelector(selectors.assemblyInstanceName);
        return textOf(nameEl || el);
      }).filter(Boolean),
      insertButtonCount: insertButtons.length,
      insertButtonVisible: insertButtons.some(visible),
    },
    analysisButton: { count: analysisButtons.length, visible: analysisButtons.some(visible) },
    analysisPopup: { count: popups.length, visible: popups.some(visible) },
    analysisPopupItemTexts: queryAll(selectors.analysisPopupItem)
      .map((el) => textOf(el)).filter(Boolean).slice(0, 40),
    visibleToolbarTexts: queryAll(selectors.assemblyToolbarItem)
      .filter(visible).map((el) => textOf(el)).filter(Boolean).slice(0, 60),
    keywordTexts: keywordNodes,
    containerCandidates: queryAll(selectors.panelRoot).slice(0, 12).map((el) => ({
      tag: el.tagName.toLowerCase(),
      cls: (typeof el.className === 'string' ? el.className : '').slice(0, 120),
      visible: visible(el),
      text: snippet(textOf(el), 400),
    })),
  };
}
"""

_JS_PANEL = r"""
/* interference:panel */
(payload) => {
  const selectors = (payload && payload.selectors) || {};
  const keywords = (payload && payload.keywords) || [];
  const summaryPatterns = (payload && payload.summaryPatterns) || [];
  const emptyMarkers = (payload && payload.emptyMarkers) || [];
  const progressMarkers = (payload && payload.progressMarkers) || [];
  const runTexts = (payload && payload.runTexts) || [];
  const norm = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const textOf = (el) => {
    if (!el) return '';
    try { return norm(el.innerText || el.textContent); } catch (e) { return ''; }
  };
  const visible = (el) => {
    if (!el) return false;
    try {
      const rect = el.getBoundingClientRect();
      if (!(rect.width > 0 && rect.height > 0)) return false;
      const style = window.getComputedStyle(el);
      return style.visibility !== 'hidden' && style.display !== 'none';
    } catch (e) {
      return false;
    }
  };
  const queryAll = (selector) => {
    if (!selector) return [];
    try { return Array.from(document.querySelectorAll(selector)); } catch (e) { return []; }
  };
  const snippet = (value, limit) => {
    const text = norm(value);
    const cap = limit || 240;
    return text.length > cap ? text.slice(0, cap) + '…' : text;
  };
  const lowered = keywords.map((word) => String(word).toLowerCase());
  const hasKeyword = (value) => {
    const text = String(value || '').toLowerCase();
    return lowered.some((word) => word && text.includes(word));
  };
  const within = (root, selector) => {
    try { return Array.from(root.querySelectorAll(selector)); } catch (e) { return []; }
  };

  // The panel root is located by KEYWORD plus an interior control, not by a guessed
  // id: the smallest visible node whose text carries a keyword and which contains
  // an input or a button. A miss reports the candidate containers it did see.
  const candidates = [];
  const allNodes = document.querySelectorAll('body *');
  for (let index = 0; index < allNodes.length; index += 1) {
    const el = allNodes[index];
    if (!visible(el)) continue;
    const text = textOf(el);
    if (!text || !hasKeyword(text)) continue;
    if (!el.querySelector('input, button, [role=button]')) continue;
    candidates.push(el);
  }
  candidates.sort((a, b) => textOf(a).length - textOf(b).length);
  const root = candidates[0] || null;
  if (!root) {
    return {
      found: false,
      rootTag: '',
      rootClass: '',
      rootText: '',
      observedCandidates: queryAll(selectors.panelRoot).slice(0, 8)
        .map((el) => snippet(textOf(el), 300)),
      keywordNodes: [],
    };
  }

  const buttons = within(root, selectors.panelButton);
  const strictRows = within(root, selectors.panelResultRow);
  const rowTexts = strictRows
    .map((el) => textOf(el))
    .filter((text) => text && !emptyMarkers.some((marker) => text.includes(marker)));

  const summaryTexts = [];
  const emptyTexts = [];
  const keywordNodes = [];
  const nodes = within(root, '*');
  for (let index = 0; index < nodes.length && keywordNodes.length < 25; index += 1) {
    const el = nodes[index];
    if (el.children.length > 6) continue;
    const text = textOf(el);
    if (!text || text.length > 300) continue;
    if (keywordNodes.some((item) => item.text === text)) continue;
    keywordNodes.push({ tag: el.tagName.toLowerCase(), visible: visible(el), text: snippet(text, 300) });
    if (summaryPatterns.some((pattern) => {
      try { return new RegExp(pattern, 'i').test(text); } catch (e) { return false; }
    })) {
      summaryTexts.push(snippet(text, 300));
    }
    if (emptyMarkers.some((marker) => text.toLowerCase().includes(String(marker).toLowerCase()))) {
      emptyTexts.push(snippet(text, 300));
    }
  }

  const progressVisible = progressMarkers.some((marker) => {
    if (queryAll(marker).some(visible)) return true;
    return within(root, '*').some((el) => {
      if (el.children.length > 1) return false;
      return textOf(el).toLowerCase().includes(String(marker).toLowerCase());
    });
  });

  return {
    found: true,
    rootTag: root.tagName.toLowerCase(),
    rootClass: (typeof root.className === 'string' ? root.className : '').slice(0, 200),
    rootText: snippet(textOf(root), 600),
    inputs: within(root, selectors.panelInput).slice(0, 10).map((el) => ({
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || '',
      value: String(el.value === undefined ? '' : el.value),
      placeholder: el.getAttribute('placeholder') || '',
      ariaLabel: el.getAttribute('aria-label') || '',
      title: el.getAttribute('title') || '',
      visible: visible(el),
    })),
    buttons: buttons.slice(0, 20).map((el) => ({
      text: snippet(textOf(el), 80),
      disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
      cls: (typeof el.className === 'string' ? el.className : '').slice(0, 120),
      visible: visible(el),
    })),
    runButtonTextsMatched: buttons
      .filter((el) => runTexts.some((text) => textOf(el).includes(text)))
      .map((el) => snippet(textOf(el), 80)),
    rowCount: rowTexts.length,
    rowTexts: rowTexts.slice(0, 100).map((text) => snippet(text, 400)),
    summaryTexts: summaryTexts.slice(0, 10),
    emptyTexts: emptyTexts.slice(0, 10),
    progressVisible: progressVisible,
    keywordNodes: keywordNodes.slice(0, 25),
    closeCandidates: queryAll(selectors.panelClose)
      .map((el) => snippet(textOf(el), 60)).filter(Boolean).slice(0, 10),
  };
}
"""


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


def _string_list(value: Any, label: str) -> list[str]:
    """Validate a caller-supplied list of non-empty strings."""
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError(f"{label} must be a list of non-empty strings")
    return [item.strip() for item in value]


def _positive_number(value: Any, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a positive number")
    if value <= 0:
        raise ValueError(f"{label} must be a positive number")
    return float(value)


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _normalize_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


# ---------------------------------------------------------------------------
# Observation (tabs reused from actions, environment from one read-only probe)
# ---------------------------------------------------------------------------


def _page_url(page: Any) -> str:
    try:
        return str(getattr(page, "url", "") or "")
    except Exception:  # noqa: BLE001 - a dead page has no URL, which is evidence
        return ""


def _read_tabs(page: Any) -> dict[str, Any]:
    """Read the document tab strip through the existing verified action."""
    try:
        listed = actions.list_document_tabs(page)
    except Exception as exc:  # noqa: BLE001 - a failed read is evidence, not a crash
        return {"tabs": [], "tabReadError": f"{type(exc).__name__}: {exc}"}
    if not isinstance(listed, dict):
        return {
            "tabs": [],
            "tabReadError": f"list_document_tabs returned {type(listed).__name__}",
        }
    tabs = listed.get("tabs")
    return {
        "tabs": tabs if isinstance(tabs, list) else [],
        "hasDocumentTabsToolButton": bool(listed.get("hasDocumentTabsToolButton")),
        "tabReadError": "",
    }


def _probe_page(page: Any) -> dict[str, Any]:
    """Read the assembly environment, analysis menu, and interference-ish texts."""
    try:
        observed = page.evaluate(
            _JS_PROBE,
            {
                "selectors": SELECTORS,
                "keywords": list(INTERFERENCE_KEYWORDS),
            },
        )
    except Exception as exc:  # noqa: BLE001 - a probe failure is evidence, not a crash
        return {"probeError": f"{type(exc).__name__}: {exc}"}
    if not isinstance(observed, dict):
        return {"probeError": f"probe returned {type(observed).__name__}, not an object"}
    return observed


def _read_panel(page: Any) -> dict[str, Any]:
    """Read the interference panel (or report that it is not there). Never raises."""
    try:
        observed = page.evaluate(
            _JS_PANEL,
            {
                "selectors": SELECTORS,
                "keywords": list(INTERFERENCE_KEYWORDS),
                "summaryPatterns": [pattern.pattern for pattern in SUMMARY_COUNT_PATTERNS],
                "emptyMarkers": list(EMPTY_TEXT_MARKERS),
                "progressMarkers": list(PROGRESS_TEXT_MARKERS),
                "runTexts": list(RUN_BUTTON_TEXTS),
            },
        )
    except Exception as exc:  # noqa: BLE001 - a probe failure is evidence, not a crash
        return {"found": False, "probeError": f"{type(exc).__name__}: {exc}"}
    if not isinstance(observed, dict):
        return {
            "found": False,
            "probeError": f"panel probe returned {type(observed).__name__}, not an object",
        }
    observed.setdefault("found", False)
    return observed


def _observation(page: Any) -> dict[str, Any]:
    """One observation: the tab strip (via ``actions``) plus one read-only probe."""
    tabs_read = _read_tabs(page)
    probe = _probe_page(page)
    tabs = tabs_read["tabs"]
    active = next((tab for tab in tabs if isinstance(tab, dict) and tab.get("active")), {})
    observation: dict[str, Any] = {
        "pageUrl": _page_url(page),
        "probe": probe,
        "tabs": tabs,
        "hasDocumentTabsToolButton": tabs_read.get("hasDocumentTabsToolButton", False),
        "tabReadError": tabs_read.get("tabReadError", ""),
        "activeTab": str(active.get("name", "")) if isinstance(active, dict) else "",
        "activeTabId": str(active.get("id", "")) if isinstance(active, dict) else "",
        "activeTabElementType": str(active.get("elementType", "")) if isinstance(active, dict) else "",
    }
    if "probeError" in probe:
        observation["probeError"] = probe["probeError"]
    return observation


def _tab_names(observation: dict[str, Any]) -> list[str]:
    return [
        str(tab.get("name", ""))
        for tab in (observation.get("tabs") or [])
        if isinstance(tab, dict)
    ]


def _assembly_environment(observation: dict[str, Any]) -> dict[str, Any]:
    """Judge whether the observed page really carries an assembly environment.

    Records WHICH signal decided it. ``active_tab_name`` and
    ``active_tab_element_type`` are weak evidence (a name is not a proof), so a
    reviewer can discount them; the mounted assembly tree, its instance rows, and
    the assembly insert toolbar (the same readiness signal ``semantic._open_tab``
    waits for) are the strong ones.
    """
    probe = observation.get("probe") if isinstance(observation.get("probe"), dict) else {}
    assembly = probe.get("assembly") if isinstance(probe.get("assembly"), dict) else {}
    tabs_read_error = str(observation.get("tabReadError") or "")
    tree_roots = _int_or_none(assembly.get("treeRootCount"))
    instance_rows = _int_or_none(assembly.get("instanceRowCount"))
    visible_rows = _int_or_none(assembly.get("visibleInstanceRowCount"))
    insert_visible = bool(assembly.get("insertButtonVisible"))
    element_type = str(observation.get("activeTabElementType") or "")
    name = str(observation.get("activeTab") or "")

    signals: list[str] = []
    if tree_roots is not None and tree_roots > 0:
        signals.append("assembly_tree_root")
    if instance_rows is not None and instance_rows > 0:
        signals.append("assembly_instance_rows")
    if insert_visible:
        signals.append("assembly_insert_button_visible")
    if element_type and "assembly" in element_type.lower():
        signals.append("active_tab_element_type")
    if name and ("装配" in name or "assembly" in name.lower()):
        signals.append("active_tab_name")
    return {
        "present": bool(signals),
        "signals": signals,
        "strongSignals": [
            signal
            for signal in signals
            if signal
            in {"assembly_tree_root", "assembly_instance_rows", "assembly_insert_button_visible"}
        ],
        "treeRootCount": tree_roots,
        "instanceRowCount": instance_rows,
        "visibleInstanceRowCount": visible_rows,
        "insertButtonVisible": insert_visible,
        "activeTab": name,
        "activeTabElementType": element_type,
        "tabReadError": tabs_read_error,
        "instanceCountBasis": instance_rows if instance_rows is not None else 0,
    }


def observe_interference_page(page: Any) -> dict[str, Any]:
    """Read-only precondition probe, exported for the plan/diagnostic path.

    Performs no click, opens nothing, and spends 0 API quota. It is the same
    observation the plan reports on and the same facts a failure carries.
    """
    observation = _observation(page)
    return {
        **observation,
        "assemblyEnvironment": _assembly_environment(observation),
        "unverifiedSelectors": unverified_selector_keys(),
        "apiRequests": 0,
    }


# ---------------------------------------------------------------------------
# Pure helpers (all offline-testable)
# ---------------------------------------------------------------------------


def _summary_count(read: dict[str, Any]) -> int | None:
    """The interference count the panel STATES, or None when it states none."""
    texts = read.get("summaryTexts")
    if not isinstance(texts, list):
        return None
    for text in texts:
        for pattern in SUMMARY_COUNT_PATTERNS:
            match = pattern.search(str(text))
            if match:
                try:
                    return int(match.group(1))
                except (TypeError, ValueError):
                    continue
    return None


def _empty_proof(read: dict[str, Any]) -> str:
    """The explicit empty-result statement the panel shows, or ``""``."""
    texts = read.get("emptyTexts")
    if not isinstance(texts, list):
        return ""
    for text in texts:
        lowered = str(text).lower()
        for marker in EMPTY_TEXT_MARKERS:
            if marker.lower() in lowered:
                return str(text)
    return ""


def _parse_volume(raw: str) -> dict[str, Any] | None:
    """Best-effort intersection volume out of one row's raw text."""
    match = _VOLUME_PATTERN.search(str(raw or ""))
    if not match:
        return None
    try:
        value = float(match.group("value"))
    except (TypeError, ValueError):
        return None
    return {
        "value": value,
        "unit": _normalize_text(match.group("unit")),
        "raw": match.group(0).strip(),
    }


def _zero_volume_flag(raw: str, volume: dict[str, Any] | None) -> bool | None:
    """Whether a row is a zero-volume CONTACT.

    ``True`` only on positive evidence (an explicit contact marker, or a parsed
    volume of exactly 0); ``False`` on a parsed positive volume; ``None`` when the
    row does not say. ``None`` rows are never silently dropped by the
    include/exclude switch.
    """
    lowered = str(raw or "").lower()
    if any(marker.lower() in lowered for marker in ZERO_VOLUME_MARKERS):
        return True
    if volume is not None:
        return bool(abs(float(volume.get("value", 0.0))) == 0.0)
    return None


def split_pair_names(raw: str) -> dict[str, Any]:
    """Split one interference row's raw text into two entity display names.

    The panel's row format is unverified, so this tries a bounded ladder of
    separators and reports the one that worked. It NEVER guesses: a row it cannot
    split into exactly two non-empty names keeps ``rawText`` and reports
    ``namesParsed: false``.
    """
    text = _normalize_text(raw)
    if not text:
        return {"names": [], "namesParsed": False, "namesBasis": "empty_row"}
    # Drop a leading ordinal and a trailing volume expression before splitting;
    # both are panel bookkeeping, not entity names.
    cleaned = re.sub(r"^\s*\(?\d+[.)]\s*", "", text)
    cleaned = _VOLUME_PATTERN.sub("", cleaned)
    cleaned = cleaned.strip(" \t\u2022-|,")
    for separator in PAIR_NAME_SEPARATORS:
        parts = re.split(re.escape(separator), cleaned)
        names = [part.strip() for part in parts if part.strip()]
        if len(names) == 2:
            return {"names": names, "namesParsed": True, "namesBasis": f"separator:{separator}"}
    return {"names": [], "namesParsed": False, "namesBasis": "unparsed"}


def _pair_from_row(index: int, raw: str, include_zero_volume: bool) -> dict[str, Any] | None:
    """Turn one raw panel row into a pair record, or drop a proven contact."""
    volume = _parse_volume(raw)
    zero_volume = _zero_volume_flag(raw, volume)
    if zero_volume is True and not include_zero_volume:
        return None
    split = split_pair_names(raw)
    names = list(split["names"])
    return {
        "index": index,
        "entityA": names[0] if len(names) == 2 else None,
        "entityB": names[1] if len(names) == 2 else None,
        "namesParsed": bool(split["namesParsed"]),
        "namesBasis": split["namesBasis"],
        "intersectionVolume": volume,
        "zeroVolumeContact": zero_volume,
        "rawText": _normalize_text(raw),
    }


def build_pairs(
    row_texts: Iterable[str],
    *,
    include_zero_volume: bool = False,
) -> dict[str, Any]:
    """Build pair records from raw panel row texts, applying the contact switch."""
    pairs: list[dict[str, Any]] = []
    excluded = 0
    for index, raw in enumerate(row_texts, start=1):
        pair = _pair_from_row(index, raw, include_zero_volume)
        if pair is None:
            excluded += 1
            continue
        pairs.append(pair)
    return {
        "pairs": pairs,
        "excludedZeroVolumePairs": excluded,
        "includedZeroVolumePairs": sum(1 for pair in pairs if pair["zeroVolumeContact"] is True),
        "unknownZeroVolumePairs": sum(1 for pair in pairs if pair["zeroVolumeContact"] is None),
        "rawTextNote": (
            "rawText is the panel's own row text with whitespace runs folded to single "
            "spaces (the same normalisation the repo's other browser reads use); no other "
            "edit is applied"
        ),
    }


def filter_pairs(pairs: Sequence[dict[str, Any]], part_names: Sequence[str]) -> dict[str, Any]:
    """Keep only pairs one of ``part_names`` participates in.

    Matching is a case-insensitive substring on the parsed entity names, falling
    back to the row's raw text when the names could not be parsed (the row is then
    the only evidence available). ``matchedPartNames``/``unmatchedPartNames`` echo
    the caller's own strings (not the lowered forms), and a name that matched
    nothing is reported rather than silently treated as clean.
    """
    requested = [_normalize_text(name) for name in part_names if _normalize_text(name)]
    wanted = [(original, original.lower()) for original in requested]
    if not wanted:
        return {
            "filterApplied": False,
            "pairs": list(pairs),
            "matchedPartNames": [],
            "unmatchedPartNames": [],
            "filteredOutCount": 0,
            "filterMode": "none",
        }
    kept: list[dict[str, Any]] = []
    matched: set[str] = set()
    for pair in pairs:
        names = [str(pair.get("entityA") or ""), str(pair.get("entityB") or "")]
        haystack = " ".join(name for name in names if name).lower()
        basis = "entity_names"
        if not haystack:
            haystack = str(pair.get("rawText") or "").lower()
            basis = "raw_text"
        hits = [original for original, lowered in wanted if lowered in haystack]
        if hits:
            matched.update(hits)
            kept.append({**pair, "partFilterBasis": basis})
    return {
        "filterApplied": True,
        "pairs": kept,
        "matchedPartNames": sorted(matched),
        "unmatchedPartNames": sorted(set(requested) - matched),
        "filteredOutCount": len(pairs) - len(kept),
        "filterMode": "either_side_substring",
    }


# ---------------------------------------------------------------------------
# Bounded polling
# ---------------------------------------------------------------------------


def _default_pause(page: Any, milliseconds: int) -> None:
    wait = getattr(page, "wait_for_timeout", None)
    if callable(wait):
        wait(milliseconds)
        return
    time.sleep(milliseconds / 1000.0)


def _bounded_poll(
    read_fn: Callable[[], dict[str, Any]],
    is_done: Callable[[dict[str, Any]], bool],
    *,
    budget_ms: int,
    poll_ms: int,
    clock: Callable[[], float],
    pause: Callable[[int], None],
) -> dict[str, Any]:
    """Poll ``read_fn`` until ``is_done`` or the budget runs out.

    The iteration cap is derived from the budget as well as from the clock, so a
    broken or non-advancing clock still terminates instead of looping forever. The
    reads and the budget are returned, because a timeout is evidence.
    """
    started = clock()
    poll_ms = max(1, int(poll_ms))
    max_iterations = max(1, int(budget_ms // poll_ms) + 2)
    reads: list[dict[str, Any]] = []
    last: dict[str, Any] = {}
    done = False
    for _ in range(max_iterations):
        last = read_fn()
        reads.append(last)
        if is_done(last):
            done = True
            break
        if (clock() - started) * 1000.0 >= budget_ms:
            break
        pause(poll_ms)
    return {
        "completed": done,
        "timedOut": not done,
        "attempts": len(reads),
        "maxIterations": max_iterations,
        "elapsedMs": round((clock() - started) * 1000.0),
        "budgetMs": int(budget_ms),
        "pollMs": poll_ms,
        "last": last,
        "reads": reads,
    }


# ---------------------------------------------------------------------------
# Click / fill ladders (the semantic.py shape: record, then a "reason" on miss)
# ---------------------------------------------------------------------------


def _click_text_candidate(
    page: Any,
    *,
    selector: str,
    texts: Sequence[str],
) -> dict[str, Any]:
    """Click the first element matching ``selector`` and one of ``texts``.

    Every attempt is recorded, so a miss reports the candidate texts tried rather
    than a silent no-op -- the same disciplined shape as ``semantic.fix_instances``.
    """
    attempts: list[dict[str, Any]] = []
    for text in texts:
        entry: dict[str, Any] = {"selector": selector, "text": text, "clicked": False}
        try:
            if selector:
                locator = page.locator(selector).filter(has_text=text)
            else:
                locator = page.get_by_text(text, exact=False)
            count = locator.count()
            entry["matchCount"] = count
            if count > 0:
                locator.first.click()
                entry["clicked"] = True
                attempts.append(entry)
                return {"clicked": True, "selector": selector, "text": text, "attempts": attempts}
        except Exception as exc:  # noqa: BLE001 - a failed click is evidence
            entry["error"] = f"{type(exc).__name__}: {exc}"
        attempts.append(entry)
    return {
        "clicked": False,
        "selector": selector,
        "text": "",
        "attempts": attempts,
        "reason": f"none of {len(texts)} candidate text(s) matched under {selector!r}",
    }


def _click_first_present(page: Any, *, selector: str) -> dict[str, Any]:
    """Click the first element matching ``selector``, recording what was found."""
    entry: dict[str, Any] = {"selector": selector, "clicked": False}
    try:
        locator = page.locator(selector)
        count = locator.count()
        entry["matchCount"] = count
        if count > 0:
            locator.first.click()
            entry["clicked"] = True
            return entry
    except Exception as exc:  # noqa: BLE001 - a failed click is evidence
        entry["error"] = f"{type(exc).__name__}: {exc}"
    entry["reason"] = f"no clickable element matched {selector!r}"
    return entry


def _fill_first_present(page: Any, *, selector: str, value: str) -> dict[str, Any]:
    """Fill one input and read its value back. A readback that differs is a miss."""
    entry: dict[str, Any] = {"selector": selector, "filled": False, "requested": value}
    try:
        locator = page.locator(selector)
        count = locator.count()
        entry["matchCount"] = count
        if count == 0:
            entry["reason"] = f"no input matched {selector!r}"
            return entry
        target = locator.first
        target.fill(value)
        entry["filled"] = True
        try:
            readback = target.input_value()
        except Exception:  # noqa: BLE001 - a missing readback method is not a fill failure
            readback = None
        entry["readback"] = readback
        if readback is not None:
            entry["readbackOk"] = _normalize_text(readback) == _normalize_text(value)
    except Exception as exc:  # noqa: BLE001 - a failed fill is evidence
        entry["error"] = f"{type(exc).__name__}: {exc}"
        entry["reason"] = f"{type(exc).__name__}: {exc}"
    return entry


def _press_escape(page: Any) -> dict[str, Any]:
    try:
        keyboard = getattr(page, "keyboard", None)
        if keyboard is None or not hasattr(keyboard, "press"):
            return {"pressed": False, "reason": "page has no keyboard.press"}
        keyboard.press("Escape")
        return {"pressed": True, "key": "Escape"}
    except Exception as exc:  # noqa: BLE001 - a failed key press is evidence
        return {"pressed": False, "reason": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# The plan (pure)
# ---------------------------------------------------------------------------


def plan_interference_check(
    *,
    tab_name: str = "",
    element_id: str = "",
    part_names: Sequence[str] | None = None,
    tolerance_mm: Any = None,
    include_zero_volume: bool = False,
    observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Report what :func:`browser_interference_check` would do, without clicking.

    Pure: it starts no browser session, navigates nowhere, and clicks nothing. Pass
    ``observation`` (from :func:`observe_interference_page`) to have the
    prerequisites judged against the page as it is right now; without it every
    prerequisite is ``None`` (unknown), never optimistically ``True``.
    """
    if not isinstance(tab_name, str):
        raise ValueError("tab_name must be a string")
    if not isinstance(element_id, str):
        raise ValueError("element_id must be a string")
    names = _string_list(part_names, "part_names")
    tolerance = _positive_number(tolerance_mm, "tolerance_mm")

    observed = isinstance(observation, dict)
    probe_ok = observed and "probeError" not in observation
    tab_facts = _plan_tab_facts(observation if probe_ok else None, tab_name=tab_name, element_id=element_id)
    environment = (
        _assembly_environment(observation)
        if probe_ok
        else {"present": None, "signals": [], "strongSignals": [], "instanceCountBasis": 0}
    )
    budgets = _budgets(environment.get("instanceCountBasis"))
    probe = observation.get("probe") if probe_ok else None

    prerequisites = [
        {
            "name": "page_probe_succeeded",
            "met": probe_ok if observed else None,
            "evidence": (observation or {}).get("probeError") if observed else None,
        },
        {
            "name": "target_tab_resolved",
            "met": tab_facts["resolved"] if observed else None,
            "evidence": tab_facts,
        },
        {
            "name": "target_tab_is_assembly",
            "met": environment["present"] if observed else None,
            "evidence": {
                "signals": environment["signals"],
                "strongSignals": environment.get("strongSignals", []),
                "activeTab": environment.get("activeTab"),
                "treeRootCount": environment.get("treeRootCount"),
                "instanceRowCount": environment.get("instanceRowCount"),
            },
        },
        {
            "name": "interference_entry_available",
            "met": _entry_available(probe) if observed else None,
            "evidence": _entry_evidence(probe),
        },
    ]
    preconditions_met = (
        bool(probe_ok and tab_facts["resolved"] and environment["present"]) if observed else None
    )

    return {
        "dryRun": True,
        "operation": PLAN_OPERATION,
        "mutating": False,
        "apiRequests": 0,
        "readOnly": True,
        "targetTab": tab_facts,
        "inputs": {
            "tabName": tab_name,
            "elementId": element_id,
            "partNames": names,
            "toleranceMm": tolerance,
            "includeZeroVolume": bool(include_zero_volume),
        },
        "intent": [
            "read the tab strip through actions.list_document_tabs (never by position)",
            "resolve the target assembly tab strictly (exactly one match, or the active tab)",
            "switch with semantic._open_tab, which waits for the ASM_INSERT_BUTTON assembly toolbar",
            "confirm an assembly environment is mounted (tree root / instance rows / insert toolbar)",
            "open the Interference Detection panel via the analysis menu ladder",
            "apply tolerance_mm when given, reading the field back (never assume it landed)",
            "run the detection and wait inside an explainable budget for a completion proof",
            "read the reported pairs, apply the zero-volume and part_names filters",
            "restore the panel (close it); no mate, constraint, fix, group or save is touched",
        ],
        "budgets": budgets,
        "selectors": dict(SELECTORS),
        "selectorProvenance": dict(SELECTOR_PROVENANCE),
        "unverifiedSelectors": unverified_selector_keys(),
        "vocabularies": {
            "menuTexts": list(INTERFERENCE_MENU_TEXTS),
            "runButtonTexts": list(RUN_BUTTON_TEXTS),
            "emptyTextMarkers": list(EMPTY_TEXT_MARKERS),
            "summaryCountPatterns": [pattern.pattern for pattern in SUMMARY_COUNT_PATTERNS],
            "keywords": list(INTERFERENCE_KEYWORDS),
        },
        "prerequisites": prerequisites,
        "preconditionsMet": preconditions_met,
        "verdictIfRunNow": _plan_verdict(observed, probe_ok, tab_facts, environment, probe),
        "cleanIsOnlyAllowedWhen": (
            "panel_available AND detection_completed AND the read-back pair set is empty; a "
            "missing panel, an unfinished or timed-out detection, an empty read without a "
            "completion proof, or a non-assembly target can never be clean"
        ),
        "note": (
            "The Interference Detection panel's own DOM is UNVERIFIED (see unverifiedSelectors). "
            "Every miss returns the observed page facts; a human must confirm the entry point, "
            "the tolerance field, the compute control, the result rows and the empty state on a "
            "real assembly before this tool's clean verdict is trusted."
        ),
    }


def _plan_tab_facts(
    observation: dict[str, Any] | None,
    *,
    tab_name: str,
    element_id: str,
) -> dict[str, Any]:
    if not isinstance(observation, dict):
        return {
            "resolved": None,
            "requestedName": tab_name,
            "requestedElementId": element_id,
            "matchCount": None,
            "tabs": [],
        }
    tabs = observation.get("tabs") if isinstance(observation.get("tabs"), list) else []
    if element_id:
        matches = [tab for tab in tabs if isinstance(tab, dict) and tab.get("id") == element_id]
    elif tab_name:
        matches = [tab for tab in tabs if isinstance(tab, dict) and tab.get("name") == tab_name]
    else:
        matches = [tab for tab in tabs if isinstance(tab, dict) and tab.get("active")]
    match = matches[0] if len(matches) == 1 else {}
    return {
        "resolved": len(matches) == 1,
        "requestedName": tab_name,
        "requestedElementId": element_id,
        "matchCount": len(matches),
        "targetName": match.get("name", ""),
        "targetId": match.get("id", ""),
        "targetActive": bool(match.get("active")),
        "tabs": tabs,
    }


def _entry_available(probe: dict[str, Any] | None) -> bool | None:
    if not isinstance(probe, dict):
        return None
    popup = probe.get("analysisPopup") if isinstance(probe.get("analysisPopup"), dict) else {}
    items = probe.get("analysisPopupItemTexts")
    toolbar = probe.get("visibleToolbarTexts")
    found_in_popup = isinstance(items, list) and any(
        any(text in str(item) for text in INTERFERENCE_MENU_TEXTS) for item in items
    )
    found_in_toolbar = isinstance(toolbar, list) and any(
        any(text in str(item) for text in INTERFERENCE_MENU_TEXTS) for item in toolbar
    )
    return bool(found_in_popup or found_in_toolbar or popup.get("visible"))


def _entry_evidence(probe: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(probe, dict):
        return {"observed": None}
    return {
        "analysisButton": probe.get("analysisButton"),
        "analysisPopup": probe.get("analysisPopup"),
        "analysisPopupItemTexts": probe.get("analysisPopupItemTexts", []),
        "visibleToolbarTexts": probe.get("visibleToolbarTexts", []),
    }


def _plan_verdict(
    observed: bool,
    probe_ok: bool,
    tab_facts: dict[str, Any],
    environment: dict[str, Any],
    probe: dict[str, Any] | None,
) -> str | None:
    if not observed:
        return None
    if not probe_ok:
        return VERDICT_INDETERMINATE
    if not tab_facts.get("resolved"):
        return VERDICT_UNAVAILABLE
    if not environment.get("present"):
        return VERDICT_UNAVAILABLE
    if _entry_available(probe) is False:
        return VERDICT_INDETERMINATE
    return None


# ---------------------------------------------------------------------------
# The real check
# ---------------------------------------------------------------------------


def browser_interference_check(
    page: Any,
    *,
    tab_name: str = "",
    element_id: str = "",
    part_names: Sequence[str] | None = None,
    tolerance_mm: Any = None,
    include_zero_volume: bool = False,
    clock: Callable[[], float] | None = None,
    pause: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    """Run the zero-quota Interference Detection check on an assembly page.

    Strictly read-only with respect to the model: no mate, no constraint, no
    fix/group, no save. ``clock``/``pause`` exist so the bounded waits are testable
    offline; their defaults are the wall clock and the page's own bounded wait.
    """
    names = _string_list(part_names, "part_names")
    tolerance = _positive_number(tolerance_mm, "tolerance_mm")
    if not isinstance(tab_name, str) or not isinstance(element_id, str):
        raise ValueError("tab_name and element_id must be strings")
    clock = clock or time.monotonic
    pause_fn = pause or (lambda milliseconds: _default_pause(page, milliseconds))

    failures: list[dict[str, Any]] = []
    context: dict[str, Any] = {
        "apiRequests": 0,
        "mutating": False,
        "readOnly": True,
        "savedNothing": True,
        # Every result carries the selector set a human still has to verify, so a
        # failure is diagnosable without a second call.
        "unverifiedSelectors": unverified_selector_keys(),
    }

    def finish(
        verdict: str,
        *,
        failure_class: str,
        failure_stage: str,
        reason: str,
        panel_available: bool = False,
        detection_completed: bool = False,
        pairs: list[dict[str, Any]] | None = None,
        interference_count: int = 0,
        tab_label: str = "",
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        all_failures = list(failures)
        if failure_class:
            all_failures.append(
                {"stage": failure_stage, "class": failure_class, "reason": reason}
            )
        return {
            "verdict": verdict,
            "reason": reason,
            "pairs": pairs or [],
            "interference_count": int(interference_count),
            "panel_available": bool(panel_available),
            "detection_completed": bool(detection_completed),
            "tab_name": tab_label,
            "evidence": {**context, **(evidence or {})},
            "failures": all_failures,
            "failureClass": failure_class,
        }

    # -- stage 1: observe the page -----------------------------------------
    observation = _observation(page)
    budgets = _budgets(
        ((observation.get("probe") or {}).get("assembly") or {}).get("instanceRowCount", 0)
        if isinstance(observation.get("probe"), dict)
        else 0
    )
    if "probeError" in observation:
        return finish(
            VERDICT_INDETERMINATE,
            failure_class=FAILURE_PAGE_PROBE_FAILED,
            failure_stage="observe_page",
            reason=observation["probeError"],
            evidence={"observation": observation, "budgets": budgets},
        )
    context["observation"] = observation

    # -- stage 2: resolve and, when needed, activate the target tab ---------
    tab_facts = _plan_tab_facts(observation, tab_name=tab_name, element_id=element_id)
    if not tab_facts["resolved"]:
        return finish(
            VERDICT_UNAVAILABLE,
            failure_class=FAILURE_TAB_NOT_FOUND,
            failure_stage="resolve_tab",
            reason=(
                f"the requested tab matched {tab_facts['matchCount']} visible tabs"
                if (tab_name or element_id)
                else "no active document tab could be read"
            ),
            tab_label=str(observation.get("activeTab") or ""),
            evidence={
                "observation": observation,
                "targetTab": tab_facts,
                "budgets": budgets,
                "observedTabNames": _tab_names(observation),
            },
        )

    target_name = str(tab_facts.get("targetName") or "")
    activation: dict[str, Any] | None = None
    if not tab_facts.get("targetActive"):
        activation = _switch_to_assembly_tab(
            page,
            element_id=str(tab_facts.get("targetId") or ""),
            name=target_name,
        )
        if not activation.get("switched"):
            return finish(
                VERDICT_INDETERMINATE,
                failure_class=FAILURE_TAB_SWITCH_FAILED,
                failure_stage="activate_tab",
                reason=str(
                    activation.get("reason") or "the target assembly tab was not activated"
                ),
                tab_label=target_name,
                evidence={
                    "observation": observation,
                    "targetTab": tab_facts,
                    "activation": activation,
                    "budgets": budgets,
                    "observedTabNames": _tab_names(observation),
                },
            )
        observation = _observation(page)
        context["observation"] = observation
        context["observationAfterActivation"] = observation
        context["activation"] = activation

    tab_label = str(observation.get("activeTab") or target_name)

    # -- stage 3: is the active tab really an assembly? ---------------------
    environment = _assembly_environment(observation)
    budgets = _budgets(environment.get("instanceCountBasis"))
    if not environment["present"]:
        return finish(
            VERDICT_UNAVAILABLE,
            failure_class=FAILURE_NOT_ASSEMBLY,
            failure_stage="confirm_assembly",
            reason=(
                "the active tab is not an assembly: no assembly tree root, no instance rows, "
                "no assembly insert toolbar, and neither the tab name nor its element type "
                "identifies an assembly"
            ),
            tab_label=tab_label,
            evidence={
                "observation": observation,
                "targetTab": tab_facts,
                "activation": activation,
                "assemblyEnvironment": environment,
                "budgets": budgets,
                "observedTabNames": _tab_names(observation),
            },
        )

    # -- stage 4: open (or find) the interference panel --------------------
    panel_open = _open_panel(page, observation=observation, clock=clock, pause=pause_fn)
    if not panel_open["available"]:
        return finish(
            VERDICT_INDETERMINATE,
            failure_class=FAILURE_PANEL_UNAVAILABLE,
            failure_stage="open_panel",
            reason=(
                "the Interference Detection panel could not be found or opened; the observed "
                "menu/toolbar/keyword texts are returned so the entry point can be corrected"
            ),
            tab_label=tab_label,
            evidence={
                "observation": observation,
                "targetTab": tab_facts,
                "activation": activation,
                "assemblyEnvironment": environment,
                "panelOpen": panel_open,
                "budgets": budgets,
                "observedTabNames": _tab_names(observation),
            },
        )

    panel_read = panel_open["read"]
    context["panelOpen"] = panel_open

    # -- stage 5: tolerance ------------------------------------------------
    if tolerance is not None:
        tolerance_report = _apply_tolerance(page, panel_read, tolerance)
        context["tolerance"] = tolerance_report
        if not tolerance_report["applied"]:
            return finish(
                VERDICT_INDETERMINATE,
                failure_class=FAILURE_TOLERANCE_NOT_APPLIED,
                failure_stage="set_tolerance",
                reason=(
                    "the requested tolerance could not be applied and read back, so a result "
                    "would not be a measurement at the requested tolerance"
                ),
                panel_available=True,
                tab_label=tab_label,
                evidence={
                    "observation": observation,
                    "targetTab": tab_facts,
                    "assemblyEnvironment": environment,
                    "panelOpen": panel_open,
                    "tolerance": tolerance_report,
                    "budgets": budgets,
                },
            )
    else:
        tolerance_report = {
            "requestedMm": None,
            "applied": False,
            "basis": "panel_current_value",
            "panelToleranceCandidates": _tolerance_field_candidates(panel_read),
            "note": (
                "no tolerance_mm was requested, so the panel's own current value is used and "
                "recorded here rather than assumed"
            ),
        }
        context["tolerance"] = tolerance_report

    # -- stage 6: run and wait for a completion proof ----------------------
    detection = _run_detection(
        page,
        initial_read=panel_read,
        tolerance_applied=bool(tolerance_report["applied"]),
        budget_ms=budgets["detectionWaitMs"],
        clock=clock,
        pause=pause_fn,
    )
    context["detection"] = detection
    panel_read = detection["lastRead"]

    restore = _restore_panel(page, clock=clock, pause=pause_fn)
    context["panelClose"] = restore
    if not restore["restored"]:
        failures.append(
            {
                "stage": "restore_panel",
                "class": FAILURE_PANEL_RESTORE_FAILED,
                "reason": "the panel could not be confirmed closed; the document was not saved",
                "panelClose": restore,
            }
        )
    context["panelRestored"] = restore["restored"]

    common_evidence = {
        "observation": observation,
        "targetTab": tab_facts,
        "assemblyEnvironment": environment,
        "panelOpen": panel_open,
        "tolerance": tolerance_report,
        "detection": detection,
        "resultRead": panel_read,
        "budgets": budgets,
        "unverifiedSelectors": unverified_selector_keys(),
    }

    if not detection["completed"]:
        wait = detection.get("wait") or {}
        return finish(
            VERDICT_INDETERMINATE,
            failure_class=FAILURE_DETECTION_NOT_COMPLETED,
            failure_stage="run_detection",
            reason=(
                "the detection did not reach a provable completion inside its budget "
                f"({wait.get('budgetMs')} ms), so nothing can be concluded"
            ),
            panel_available=True,
            detection_completed=False,
            tab_label=tab_label,
            evidence=common_evidence,
        )

    if panel_read.get("probeError"):
        return finish(
            VERDICT_INDETERMINATE,
            failure_class=FAILURE_RESULT_UNREADABLE,
            failure_stage="read_result",
            reason=f"the result read failed: {panel_read['probeError']}",
            panel_available=True,
            detection_completed=True,
            tab_label=tab_label,
            evidence=common_evidence,
        )

    row_texts = [str(text) for text in (panel_read.get("rowTexts") or []) if str(text).strip()]
    built = build_pairs(row_texts, include_zero_volume=include_zero_volume)
    rows = built["pairs"]
    summary_count = _summary_count(panel_read)
    consistency = _result_consistency(summary_count, row_texts, built)
    filtered = filter_pairs(rows, names)
    pairs = filtered["pairs"]
    zero_evidence = _zero_volume_evidence(built)

    evidence = {
        **common_evidence,
        "resultConsistency": consistency,
        "completionProof": detection["proof"],
        "proofBasis": detection["proof"]["basis"],
        "summaryCount": summary_count,
        "rowCount": len(row_texts),
        "unfilteredPairCount": len(rows),
        "returnedPairCount": len(pairs),
        "partFilter": filtered,
        "zeroVolume": zero_evidence,
        "emptyStateText": detection["proof"].get("emptyText", ""),
    }

    if consistency["status"] == "mismatch":
        return finish(
            VERDICT_INDETERMINATE,
            failure_class=FAILURE_RESULT_UNREADABLE,
            failure_stage="read_result",
            reason=consistency["reason"],
            panel_available=True,
            detection_completed=True,
            tab_label=tab_label,
            evidence=evidence,
        )

    if pairs:
        return finish(
            VERDICT_INTERFERENCE,
            failure_class=FAILURE_NONE,
            failure_stage="",
            reason=f"{len(pairs)} interfering pair(s) were reported by the panel",
            panel_available=True,
            detection_completed=True,
            pairs=pairs,
            interference_count=len(pairs),
            tab_label=tab_label,
            evidence=evidence,
        )

    # Zero pairs *after the filters*. Two different reasons are possible and they
    # must not be conflated:
    #   * every reported row was a PROVEN zero-volume contact and the caller asked
    #     for those not to count -- that is a real "no volumetric interference"
    #     answer, so it may be clean, with the excluded count in evidence;
    #   * the part_names filter removed rows -- that is a scoped non-answer about
    #     the requested parts, not a clean assembly, and must never read as one.
    if int(filtered.get("filteredOutCount") or 0) > 0:
        return finish(
            VERDICT_INDETERMINATE,
            failure_class=FAILURE_PART_FILTER_EXCLUDED_ALL,
            failure_stage="apply_filter",
            reason=(
                "the panel reported interference rows, but none of them matched the requested "
                "part_names, so no scoped answer can be stated as clean"
            ),
            panel_available=True,
            detection_completed=True,
            tab_label=tab_label,
            evidence=evidence,
        )

    if not detection["proof"]["basis"]:
        # Defensive: ``detection.completed`` is only ever true with a proof, so this
        # branch is unreachable through _run_detection. It exists so that a future
        # change to the completion rule cannot quietly turn an unproven empty read
        # into ``clean`` -- the invariant this whole tool rests on.
        return finish(
            VERDICT_INDETERMINATE,
            failure_class=FAILURE_EMPTY_WITHOUT_COMPLETION_PROOF,
            failure_stage="read_result",
            reason=(
                "the result read back empty but no completion proof exists, so detection is "
                "not shown to have run"
            ),
            panel_available=True,
            detection_completed=bool(detection["completed"]),
            tab_label=tab_label,
            evidence=evidence,
        )

    excluded_contacts = int(built.get("excludedZeroVolumePairs") or 0)
    return finish(
        VERDICT_CLEAN,
        failure_class=FAILURE_NONE,
        failure_stage="",
        reason=(
            "the panel was present, the detection completed with proof "
            f"({detection['proof']['basis']}), and zero pairs were reported"
            + (
                f" ({excluded_contacts} proven zero-volume contact(s) were excluded because "
                "include_zero_volume=false)"
                if excluded_contacts
                else ""
            )
        ),
        panel_available=True,
        detection_completed=True,
        tab_label=tab_label,
        evidence=evidence,
    )


def _zero_volume_evidence(built: dict[str, Any]) -> dict[str, Any]:
    return {
        "excludedZeroVolumePairs": built["excludedZeroVolumePairs"],
        "includedZeroVolumePairs": built["includedZeroVolumePairs"],
        "unknownZeroVolumePairs": built["unknownZeroVolumePairs"],
        "note": (
            "a row is excluded only when it is PROVEN a zero-volume contact; rows whose volume "
            "the panel does not state are kept with zeroVolumeContact=null rather than dropped"
        ),
    }


def _result_consistency(
    summary_count: int | None,
    row_texts: Sequence[str],
    built: dict[str, Any],
) -> dict[str, Any]:
    """Cross-check the panel's stated count against the rows actually read.

    A disagreement means the read is not trustworthy, and this module refuses to
    pick a side: it makes the verdict ``indeterminate`` instead.
    """
    if summary_count is None:
        return {
            "status": "no_summary",
            "reason": "the panel stated no interference count to cross-check against",
        }
    if summary_count != len(row_texts):
        return {
            "status": "mismatch",
            "summaryCount": summary_count,
            "rowCount": len(row_texts),
            "reason": (
                f"the panel stated {summary_count} interference(s) but {len(row_texts)} "
                "row(s) were read, so the read is not trustworthy"
            ),
        }
    return {
        "status": "consistent",
        "summaryCount": summary_count,
        "rowCount": len(row_texts),
        "excludedZeroVolumePairs": built["excludedZeroVolumePairs"],
    }


def _switch_to_assembly_tab(page: Any, *, element_id: str, name: str) -> dict[str, Any]:
    """Make one assembly tab active, reusing the repo's existing switch paths.

    By name this goes through :func:`onshape_browser_mode.semantic._open_tab`, whose
    success condition is the assembly toolbar (``ASM_INSERT_BUTTON``) becoming
    visible -- so the switch and the assembly readiness are one verified step. If
    that returns false it falls back to the by-``data-id``
    :func:`onshape_browser_mode.actions.activate_tab` and records both, because a
    failed readiness wait must not be confused with a failed switch.
    """
    attempts: list[dict[str, Any]] = []
    switched = False
    readiness = None
    if name:
        try:
            from onshape_browser_mode import semantic

            readiness = bool(semantic._open_tab(page, name))
        except Exception as exc:  # noqa: BLE001 - a failed switch is evidence
            readiness = False
            attempts.append({"step": "semantic._open_tab", "ok": False, "error": f"{type(exc).__name__}: {exc}"})
        else:
            attempts.append({"step": "semantic._open_tab", "ok": readiness})
        if readiness:
            return {
                "switched": True,
                "method": "semantic._open_tab",
                "assemblyReadinessSignal": True,
                "attempts": attempts,
            }
    activation: dict[str, Any] = {}
    if element_id:
        try:
            activation = actions.activate_tab(
                page,
                element_id=element_id,
                content="any",
                timeout_ms=TAB_ACTIVATE_TIMEOUT_MS,
            )
        except Exception as exc:  # noqa: BLE001 - a failed switch is evidence
            activation = {"activated": False, "reason": f"{type(exc).__name__}: {exc}"}
        switched = bool(isinstance(activation, dict) and activation.get("activated"))
        attempts.append({"step": "actions.activate_tab", "ok": switched})
    if not switched and not name:
        return {
            "switched": False,
            "method": "",
            "assemblyReadinessSignal": readiness,
            "attempts": attempts,
            "reason": "no tab name or data-id was available to switch with",
        }
    return {
        "switched": switched,
        "method": "actions.activate_tab" if switched else "",
        "assemblyReadinessSignal": readiness,
        "activation": activation,
        "attempts": attempts,
        "reason": None if switched else "neither the assembly tab switch nor its fallback succeeded",
    }


def _open_panel(
    page: Any,
    *,
    observation: dict[str, Any],
    clock: Callable[[], float],
    pause: Callable[[int], None],
) -> dict[str, Any]:
    """Find or open the interference panel, recording every attempt.

    The ladder is: (1) the panel may already be open; (2) click the analysis button
    and then the interference item inside the popup; (3) click a visible toolbar
    item whose text is the interference entry. A total miss returns the observed
    candidate texts instead of a guess.
    """
    probe = observation.get("probe") if isinstance(observation.get("probe"), dict) else {}
    attempts: list[dict[str, Any]] = []
    initial = _read_panel(page)
    attempts.append({"step": "already_open", "found": bool(initial.get("found"))})
    if initial.get("found"):
        return {
            "available": True,
            "method": "already_open",
            "attempts": attempts,
            "read": initial,
            "wait": {"completed": True, "attempts": 1, "elapsedMs": 0},
        }

    if isinstance(probe.get("analysisButton"), dict) and probe["analysisButton"].get("visible"):
        clicked_analysis = _click_first_present(page, selector=SELECTORS["analysisButton"])
        attempts.append({"step": "click_analysis_button", **clicked_analysis})
        menu_wait = _bounded_poll(
            lambda: {"visible": _popup_visible(page)},
            lambda read: bool(read.get("visible")),
            budget_ms=PANEL_MENU_TIMEOUT_MS,
            poll_ms=PANEL_POLL_MS,
            clock=clock,
            pause=pause,
        )
        attempts.append(
            {
                "step": "wait_analysis_popup",
                "wait": {
                    key: menu_wait[key]
                    for key in ("completed", "timedOut", "attempts", "elapsedMs", "budgetMs")
                },
            }
        )

    popup_click = _click_text_candidate(
        page,
        selector=SELECTORS["analysisPopupItem"],
        texts=INTERFERENCE_MENU_TEXTS,
    )
    attempts.append({"step": "click_popup_item", **popup_click})
    toolbar_click: dict[str, Any] | None = None
    if not popup_click["clicked"]:
        toolbar_click = _click_text_candidate(
            page,
            selector=SELECTORS["assemblyToolbarItem"],
            texts=INTERFERENCE_MENU_TEXTS,
        )
        attempts.append({"step": "click_toolbar_item", **toolbar_click})

    wait = _bounded_poll(
        lambda: _read_panel(page),
        lambda read: bool(read.get("found")),
        budget_ms=PANEL_OPEN_TIMEOUT_MS,
        poll_ms=PANEL_POLL_MS,
        clock=clock,
        pause=pause,
    )
    last = wait["last"]
    if not wait["completed"]:
        return {
            "available": False,
            "method": "",
            "attempts": attempts,
            "wait": {
                key: wait[key]
                for key in ("completed", "timedOut", "attempts", "elapsedMs", "budgetMs", "pollMs")
            },
            "read": last,
            "reason": "the interference panel never appeared inside its open budget",
            "observed": {
                "analysisPopupItemTexts": probe.get("analysisPopupItemTexts", []),
                "visibleToolbarTexts": probe.get("visibleToolbarTexts", []),
                "keywordTexts": probe.get("keywordTexts", []),
                "containerCandidates": probe.get("containerCandidates", []),
                "lastReadObservedCandidates": last.get("observedCandidates", []),
            },
        }
    method = "popup_item" if popup_click["clicked"] else ("toolbar_item" if toolbar_click else "unknown")
    return {
        "available": True,
        "method": method,
        "attempts": attempts,
        "wait": {
            "completed": True,
            "attempts": wait["attempts"],
            "elapsedMs": wait["elapsedMs"],
            "budgetMs": wait["budgetMs"],
            "pollMs": wait["pollMs"],
        },
        "read": last,
    }


def _popup_visible(page: Any) -> bool:
    try:
        return page.locator(SELECTORS["analysisPopup"]).count() > 0
    except Exception:  # noqa: BLE001 - a failed read is simply "not visible yet"
        return False


def _apply_tolerance(page: Any, panel_read: dict[str, Any], tolerance: float) -> dict[str, Any]:
    """Fill the panel's tolerance field and prove the value landed."""
    value = _format_tolerance(tolerance)
    fill = _fill_first_present(
        page,
        selector=SELECTORS["panelToleranceInput"],
        value=value,
    )
    applied = bool(fill.get("filled")) and fill.get("readbackOk") is not False
    return {
        "requestedMm": tolerance,
        "requestedText": value,
        "applied": applied,
        "basis": "field_readback" if applied else "field_not_applied",
        "fill": fill,
        "panelToleranceCandidates": _tolerance_field_candidates(panel_read),
        "note": (
            "a fill whose readback differs is not treated as applied; the check then refuses to "
            "report a verdict at a tolerance it did not set"
        ),
    }


def _format_tolerance(value: float) -> str:
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _tolerance_field_candidates(panel_read: dict[str, Any]) -> list[dict[str, Any]]:
    inputs = panel_read.get("inputs")
    if not isinstance(inputs, list):
        return []
    return [entry for entry in inputs if isinstance(entry, dict)]


def _run_detection(
    page: Any,
    *,
    initial_read: dict[str, Any],
    tolerance_applied: bool,
    budget_ms: int,
    clock: Callable[[], float],
    pause: Callable[[int], None],
) -> dict[str, Any]:
    """Click the compute control and wait for a completion PROOF.

    A completion proof is one of: the panel states an interference count, the panel
    states explicitly that there is none, or a run was observed in progress and the
    panel settled with it gone. A read that merely shows no rows is NOT a proof, and
    is exactly the case that must not become ``clean``.
    """
    pre_proof = _completion_proof(initial_read, progress_seen=False)
    if pre_proof["basis"] and not tolerance_applied:
        return {
            "completed": True,
            "proof": {**pre_proof, "freshness": "pre_existing"},
            "runClicked": False,
            "runClick": None,
            "progressObserved": False,
            "wait": {"completed": True, "attempts": 0, "elapsedMs": 0, "budgetMs": budget_ms},
            "lastRead": initial_read,
        }

    if tolerance_applied:
        # The tolerance changed the inputs, so any previously shown result is stale
        # and a fresh run is mandatory.
        pre_proof = {"basis": "", "reason": "a tolerance was applied, so a fresh run is required"}

    # After a tolerance change the panel can keep DISPLAYING the previous run's
    # result until it recomputes, and that shown result is itself a "completion
    # proof". Accepting it would report a stale measurement at the new tolerance, so
    # a proof only counts once the display has actually moved (or a run was seen in
    # progress and then settled).
    pre_run_signature = _read_signature(initial_read) if tolerance_applied else None
    stale_proof_rejected = False

    run_click = _click_text_candidate(
        page,
        selector=SELECTORS["panelButton"],
        texts=RUN_BUTTON_TEXTS,
    )
    progress_seen = False

    def poll() -> dict[str, Any]:
        nonlocal progress_seen
        read = _read_panel(page)
        if read.get("progressVisible"):
            progress_seen = True
        return read

    def accepted(read: dict[str, Any]) -> bool:
        nonlocal stale_proof_rejected
        if not _completion_proof(read, progress_seen=progress_seen)["basis"]:
            return False
        if (
            pre_run_signature is not None
            and _read_signature(read) == pre_run_signature
            and not progress_seen
        ):
            stale_proof_rejected = True
            return False
        return True

    wait = _bounded_poll(
        poll,
        accepted,
        budget_ms=budget_ms,
        poll_ms=DETECTION_POLL_MS,
        clock=clock,
        pause=pause,
    )
    last = wait["last"]
    proof = _completion_proof(last, progress_seen=progress_seen)
    if stale_proof_rejected and not wait["completed"]:
        proof = {
            "basis": "",
            "reason": (
                "the panel kept showing the pre-run result after the tolerance changed, so no "
                "fresh detection is shown to have finished"
            ),
        }
    return {
        "completed": bool(wait["completed"]),
        "proof": {**proof, "freshness": "after_run_click"},
        "runClicked": bool(run_click.get("clicked")),
        "runClick": run_click,
        "progressObserved": progress_seen,
        "staleResultRejected": stale_proof_rejected,
        "preRunProof": pre_proof,
        "wait": {
            "completed": wait["completed"],
            "timedOut": wait["timedOut"],
            "attempts": wait["attempts"],
            "maxIterations": wait["maxIterations"],
            "elapsedMs": wait["elapsedMs"],
            "budgetMs": wait["budgetMs"],
            "pollMs": wait["pollMs"],
        },
        "lastRead": last,
    }


def _read_signature(read: dict[str, Any]) -> tuple[Any, ...]:
    """A cheap identity for "what the panel is displaying right now"."""
    return (
        tuple(str(text) for text in (read.get("summaryTexts") or [])),
        tuple(str(text) for text in (read.get("rowTexts") or [])),
        tuple(str(text) for text in (read.get("emptyTexts") or [])),
        bool(read.get("progressVisible")),
    )


def _completion_proof(read: dict[str, Any], *, progress_seen: bool) -> dict[str, Any]:
    """The strongest completion proof the current read supports, or an empty one."""
    if not isinstance(read, dict) or not read.get("found"):
        return {"basis": "", "reason": "the panel is not present in the read"}
    summary = _summary_count(read)
    if summary is not None:
        return {"basis": "summary_count", "summaryCount": summary}
    empty_text = _empty_proof(read)
    if empty_text:
        return {"basis": "empty_marker", "emptyText": empty_text}
    if progress_seen and not read.get("progressVisible"):
        return {
            "basis": "progress_completed",
            "note": "a run was observed in progress and the panel settled",
        }
    return {
        "basis": "",
        "reason": (
            "the read shows no count, no explicit empty statement, and no observed run that "
            "finished; an empty row list alone is not proof that detection ran"
        ),
    }


def _restore_panel(
    page: Any,
    *,
    clock: Callable[[], float],
    pause: Callable[[int], None],
) -> dict[str, Any]:
    """Close the panel we opened. Read-only courtesy; never affects the verdict."""
    attempts: list[dict[str, Any]] = []
    close_click = _click_first_present(page, selector=SELECTORS["panelClose"])
    attempts.append({"step": "click_close", **close_click})
    if not close_click.get("clicked"):
        escape = _press_escape(page)
        attempts.append({"step": "press_escape", **escape})

    wait = _bounded_poll(
        lambda: _read_panel(page),
        lambda read: not bool(read.get("found")),
        budget_ms=PANEL_CLOSE_TIMEOUT_MS,
        poll_ms=PANEL_POLL_MS,
        clock=clock,
        pause=pause,
    )
    if not wait["completed"]:
        escape = _press_escape(page)
        attempts.append({"step": "press_escape_retry", **escape})
        wait = _bounded_poll(
            lambda: _read_panel(page),
            lambda read: not bool(read.get("found")),
            budget_ms=PANEL_CLOSE_TIMEOUT_MS,
            poll_ms=PANEL_POLL_MS,
            clock=clock,
            pause=pause,
        )
    return {
        "restored": bool(wait["completed"]),
        "attempts": attempts,
        "elapsedMs": wait["elapsedMs"],
        "lastFound": bool(wait["last"].get("found")),
    }
