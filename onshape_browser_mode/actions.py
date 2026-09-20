"""Zero-quota browser actions for the FeatureScript editor.

These operate on the live Onshape page through Playwright. They never call the
Onshape REST API: reading/writing the Ace editor and clicking the Commit button
all happen in the browser UI, so deploying a FeatureScript script this way
spends 0 API calls.

All functions take a Playwright sync `page` object obtained from
``BrowserSession.start()``.
"""

from __future__ import annotations

import re
import time
from typing import Any

from onshape_browser_mode import diagnostics, interaction
from onshape_browser_mode.selectors import (
    ACE_EDITOR,
    CONTEXT_MENU_LAYER,
    CUSTOM_FEATURE_MENU_ITEM,
    CUSTOM_FEATURE_MENU_LABEL,
    FEATURE_DIALOG_OK,
    FS_COMMIT_BUTTON,
    FS_MODULE_OUTLINE,
    FS_MODULE_OUTLINE_DROPDOWN,
    FS_MODULE_OUTLINE_ICON,
    FS_MODULE_OUTLINE_ITEM,
    FS_MODULE_OUTLINE_LIST,
    FS_MODULE_OUTLINE_NAME,
    FS_NOTICE_COLUMN,
    FS_NOTICE_CONTENT,
    FS_NOTICE_LINE,
    FS_NOTICE_MESSAGE,
    FS_NOTICE_TABLE,
    FS_NOTICE_TOGGLE,
    PARTSTUDIO_FEATURE_ITEM,
    PS_DEFAULT_FEATURE,
    PS_FEATURES_HEADER,
    PS_WORKSPACE_CUSTOM_FEATURE_BTN,
    TIMEOUT_RECONNECT_LINK,
)

_ACE_GET_EDITOR_JS = """
() => {
  const el = document.querySelector('%s');
  if (!el) return null;
  const ed = (el.env && el.env.editor) || (window.ace && window.ace.edit(el));
  return ed || null;
}
""" % ACE_EDITOR

#: Bounded waits for the Part Studio custom-feature apply path. Each is at least
#: as long as the fixed sleep it replaced, so a slow workbench cannot regress,
#: while a fast one no longer pays the full delay. See onshape_docs/experience/
#: browser-automation.md for the recorded UI sequence.
CUSTOM_FEATURE_MENU_TIMEOUT_MS = 8_000
FEATURE_DIALOG_TIMEOUT_MS = 15_000

#: Floor of both post-insert wait budgets, and the whole budget when the custom
#: feature count cannot be read. A reload discards the workbench, so the
#: post-reload read happens only after the feature rows are back; a short default
#: would race the document load and report a committed feature as missing
#: (measured live 2026-09-20: the panel title was already visible with an empty
#: list, and the rows arrived ~1 s later).
PARTSTUDIO_RELOAD_TIMEOUT_MS = 30_000

#: Post-insert wait budgets scale with the number of custom features in the
#: element, because a post-insert recompute costs roughly a fixed part plus a part
#: proportional to how many features must be re-evaluated. Measured live
#: 2026-09-20 on a Part Studio with 5 spiral features and 5 solid parts: the
#: in-place regeneration returned after 202 ms, but the survival wait after the
#: commit-verify reload needed 18 431 ms of its 30 000 ms budget. A fixed budget
#: therefore gets *thinner* as the document grows, and the direction it fails in
#: is a committed feature reported as missing. Both profiles keep today's fixed
#: value as their floor (a feature count of 0 is exactly the old behaviour), add
#: a per-feature allowance, and stay capped so a tool call still returns.
PARTSTUDIO_REGENERATE_WAIT = {"baseMs": 30_000, "perFeatureMs": 2_000, "maxMs": 300_000}
PARTSTUDIO_RELOAD_WAIT = {"baseMs": 30_000, "perFeatureMs": 8_000, "maxMs": 900_000}

#: Readiness waits used only after this module switches to another Part Studio tab.
#: A switched-to workbench renders in stages (title, then rows, then toolbar), and
#: both the baseline read and the toolbar click are wrong if they run too early:
#: measured live 2026-09-20, a switch from a Feature Studio gave
#: "workspace-custom-features button not found" and a baseline of 0 rows on a Part
#: Studio holding 8 custom features. Fixed, because they bound a *render*, not a
#: model recompute.
PARTSTUDIO_PANEL_READY_TIMEOUT_MS = 30_000
PARTSTUDIO_TOOLBAR_TIMEOUT_MS = 30_000

#: In-page readiness predicate: at least ``minimum`` Feature List rows exist.
_PANEL_ROW_COUNT_PREDICATE = """
({selector, minimum}) => document.querySelectorAll(selector).length >= minimum
"""

#: In-page predicate for both insert waits: visible user-feature rows whose text
#: contains the feature name, with the same matching rule as ``feature_state``
#: (the ``ns-user-feature`` class plus a substring name match). It waits for a
#: COUNT rather than for one named row, because a name-only wait cannot tell the
#: row this call creates from a same-named row that was already in the Part
#: Studio: measured live 2026-09-20, a Part Studio already holding two
#: ``Spiral ridge`` rows satisfied the old name-only regeneration wait in 12 ms.
#: ``minimum`` is therefore the pre-insert baseline plus one.
_ROW_COUNT_PREDICATE = """
({selector, text, minimum}) => {
  const wanted = (text || '').trim().toLowerCase();
  const matched = Array.from(document.querySelectorAll(selector)).filter(el => {
    const cls = String(el.className || '');
    if (!cls.includes('ns-user-feature')) return false;
    if (!wanted) return true;
    return (el.innerText || el.textContent || '').toLowerCase().includes(wanted);
  });
  return matched.length >= minimum;
}
"""

#: How long a deleted document tab may take to leave the tab strip. A removed tab
#: is marked ``hidden`` first (Onshape's ``ng-class`` reads
#: ``tab.getIsRemoved()``) and detached later, so the wait accepts either state.
#: The wait is on the tab's ``data-id``, never on a position: a tab strip is an
#: ``ng-repeat`` list, so removing a tab re-numbers it and ``locator.nth(i)``
#: re-resolves to the tab that moved into the freed slot — which is attached, so
#: ``wait_for(state="detached")`` can never be satisfied. Measured live
#: 2026-09-20: that wait timed out after 30 s on a tab that had in fact been
#: deleted, and the exception became ``deleted: false``.
TAB_DELETE_TIMEOUT_MS = 30_000

#: Bounded wait for a tab this call just clicked to carry Onshape's own ``active``
#: class. The verdict is that class, read for the exact ``data-id``, never a
#: duration and never a position.
TAB_ACTIVATE_TIMEOUT_MS = 15_000

_TAB_ACTIVE_PREDICATE = """
({selector, id}) => {
  const nodes = Array.from(document.querySelectorAll(selector)).filter(
    el => el.getAttribute('data-id') === id
  );
  return nodes.length > 0 && nodes.every(
    el => String(el.className || '').split(/\\s+/).includes('active')
  );
}
"""

#: In-page predicate: the tab carrying this ``data-id`` is gone, or every node
#: carrying it is marked removed (``hidden``).
_TAB_REMOVED_PREDICATE = """
({selector, id}) => {
  const nodes = Array.from(document.querySelectorAll(selector)).filter(
    el => el.getAttribute('data-id') === id
  );
  return nodes.length === 0 || nodes.every(
    el => String(el.className || '').split(/\\s+/).includes('hidden')
  );
}
"""

#: In-page enumeration of custom-feature rows: the names AND the count of the SAME
#: node list. That identity is the point — a read that filters and a locator that
#: counts are different sets and must never be compared. Measured live 2026-09-20,
#: ``read_partstudio_features`` ends its collector with ``.filter(f => f.name)``,
#: so a node whose ``innerText`` and ``textContent`` are both empty was dropped
#: there while ``page.locator('.os-list-item.ns-user-feature')`` counted it: on two
#: elements holding 1 and 11 named rows the counts were ``2`` and ``12``, a
#: constant +1 that made the dialog edit path refuse on every element.
#: ``querySelectorAll`` is document order, which is the order the row locator
#: resolves in, so a click index taken from this list addresses the row the name
#: came from.
_USER_FEATURE_ROWS_JS = """
({selector}) => {
  const rows = Array.from(document.querySelectorAll(selector)).filter(
    el => String(el.className || '').includes('ns-user-feature')
  );
  return {
    count: rows.length,
    names: rows.map(el =>
      (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 100)
    ),
  };
}
"""

#: Notice-pane collector. One notice table can carry several message paragraphs;
#: all of them are returned in ``messages`` (``text`` keeps the first one for
#: callers that predate the list). Notices are returned for EVERY document
#: element the pane lists, each flagged ``isActiveTab`` and ``outOfDate``: a
#: feature that fails to regenerate in a Part Studio is reported in this pane
#: under that Part Studio's own container while a Feature Studio is the active
#: tab, and dropping that container (or skipping a container whose header carries
#: ``notices-out-of-date``) hid the failure behind an empty notice list. When a
#: listed element yields no readable notice at all, bounded structural evidence
#: (``unstructuredContainers``/``paneClassNames``) is returned instead of
#: nothing, because the pane's real structure is otherwise unobservable. Kept as
#: a module constant so the offline stub-DOM test in dev/tests exercises the
#: exact string sent to Playwright.
FS_NOTICE_SNAPSHOT_JS = """
(selectors) => {
  const visible = (el) => {
    if (!el) return false;
    const style = window.getComputedStyle(el);
    const rect = el.getBoundingClientRect();
    return style.display !== 'none' && style.visibility !== 'hidden' &&
      rect.width > 0 && rect.height > 0;
  };
  const text = (el) => (el ? (el.innerText || el.textContent || '').trim() : '');
  const integer = (el) => {
    const value = Number.parseInt(text(el), 10);
    return Number.isInteger(value) ? value : null;
  };
  const toggle = document.querySelector(selectors.toggle);
  const content = document.querySelector(selectors.content);
  const activeTab = Array.from(document.querySelectorAll('.os-tab-bar-tab'))
    .find((tab) => (tab.className || '').includes('active'));
  const activeTabName = text(activeTab && activeTab.querySelector('.os-tab-name'));
  const containers = content
    ? Array.from(content.querySelectorAll('.element-notice-set-container'))
    : [];
  // Bounded structural evidence for the shape "the pane listed a document
  // element but this collector read no notice from it": a regeneration failure
  // is recorded in the element's log region rather than as a notice row, so an
  // empty notice list alone cannot tell "nothing to report" apart from
  // "reported somewhere this collector does not read yet". Class names are
  // keyword-filtered and unique, so the payload stays small and the pane's real
  // structure is observable without a browser eval tool.
  const structureClasses = (root, limit) => {
    const seen = [];
    for (const el of root.querySelectorAll('[class]')) {
      const cls = String(el.className || '').trim().replace(/\\s+/g, ' ');
      if (!cls || !/notice|log|console|error|warn/i.test(cls)) continue;
      if (seen.includes(cls)) continue;
      seen.push(cls);
      if (seen.length >= limit) break;
    }
    return seen;
  };
  const notices = [];
  const silentContainers = [];
  for (const container of containers) {
    // ``notices-out-of-date`` on the element header is NOT "these rows are
    // invalid". Measured live 2026-09-20: the container for a Part Studio whose
    // custom feature failed to regenerate carried that class AND the complete,
    // current error with its call stack in a normal notice table. Skipping such
    // a container hid the failure behind an empty notice list, so the rows are
    // read and flagged ``outOfDate`` instead; callers that must not let a stale
    // row fail a fresh compile filter on that flag.
    const outOfDate = !!container.querySelector('.notices-out-of-date');
    const tabName = text(container.querySelector('.element-notice-title'));
    // A container with no title cannot be attributed, so it counts as the
    // active tab (the pre-existing behaviour) instead of being dropped.
    const isActiveTab = !activeTabName || !tabName || tabName === activeTabName;
    let produced = 0;
    for (const table of container.querySelectorAll(selectors.table)) {
      const messages = Array.from(table.querySelectorAll(selectors.message))
        .map(text).filter(Boolean);
      if (!messages.length) continue;
      const line = integer(table.querySelector(selectors.line));
      const column = integer(table.querySelector(selectors.column));
      // Severity from the table's OWN class vocabulary, by precedence: one row
      // of a console-style table can carry an info-styled gutter icon AND an
      // error text cell (`.error-text-td`/`.error-list-error-text`), so asking
      // for `fs-notice-info` first labelled a real regeneration error as info
      // and hid it from every blocking verdict. An error marker anywhere in the
      // table therefore wins, then warning, then info.
      const classBlob = [
        String(table.className || ''),
        ...Array.from(table.querySelectorAll('[class]')).map((el) => String(el.className || '')),
      ].join(' ').toLowerCase();
      let severity = 'warning';
      if (classBlob.includes('error')) severity = 'error';
      else if (classBlob.includes('warn')) severity = 'warning';
      else if (classBlob.includes('info')) severity = 'info';
      notices.push({
        severity,
        text: messages[0],
        messages,
        line,
        column,
        row: line === null ? 0 : Math.max(0, line - 1),
        col: column === null ? 0 : Math.max(0, column - 1),
        tabName,
        isActiveTab,
        outOfDate,
      });
      produced += 1;
    }
    if (!produced) silentContainers.push({ container, tabName, outOfDate });
  }
  const activeTabNotices = notices.filter((notice) => notice.isActiveTab);
  const structure = silentContainers.length ? {
    unstructuredContainers: silentContainers.slice(0, 3).map((entry) => ({
      tabName: entry.tabName,
      outOfDate: entry.outOfDate,
      classes: String(entry.container.className || '').trim().replace(/\\s+/g, ' ').slice(0, 160),
      text: text(entry.container).slice(0, 400),
    })),
    paneClassNames: structureClasses(document, 48),
  } : {};
  return {
    found: !!toggle || !!content,
    indicatorPresent: visible(toggle),
    paneOpen: !!(toggle && toggle.querySelector('.flyout-toggle-button.os-expanded')),
    activeTabName,
    // Bounded structural evidence: which document elements the pane listed at
    // all, which distinguishes "the pane said nothing" from "the pane listed an
    // element that produced no readable notice", which an empty notice list
    // alone cannot tell apart.
    containerCount: containers.length,
    containerTitles: containers
      .map((container) => text(container.querySelector('.element-notice-title')))
      .filter(Boolean)
      .slice(0, 20),
    noticeCount: notices.length,
    activeTabNoticeCount: activeTabNotices.length,
    otherElementNoticeCount: notices.length - activeTabNotices.length,
    notices,
    ...structure,
  };
}
"""


def read_featurescript_editor(page: Any) -> str | None:
    """Return the full FeatureScript source, or None if no Ace editor is open."""
    return page.evaluate(
        """
        () => {
          const el = document.querySelector('.ace_editor');
          if (!el) return null;
          const ed = (el.env && el.env.editor) || (window.ace && window.ace.edit(el));
          return ed ? ed.getValue() : null;
        }
        """
    )


def _read_featurescript_ace_annotations(page: Any) -> dict[str, Any]:
    """Read and normalize the active Ace session's annotations."""
    return page.evaluate(
        """
        () => {
          const el = document.querySelector('%s');
          if (!el) {
            return {
              found: false,
              annotationCount: 0,
              errors: [],
              reason: 'FeatureScript editor not found',
            };
          }
          const ed = (el.env && el.env.editor) || (window.ace && window.ace.edit(el));
          if (!ed || !ed.session || typeof ed.session.getAnnotations !== 'function') {
            return {
              found: false,
              annotationCount: 0,
              errors: [],
              reason: 'Ace annotation API unavailable',
            };
          }
          const annotations = ed.session.getAnnotations() || [];
          return {
            found: true,
            annotationCount: annotations.length,
            errors: annotations.map((item) => ({
              row: Number.isInteger(item.row) ? item.row : 0,
              col: Number.isInteger(item.column)
                ? item.column
                : (Number.isInteger(item.col) ? item.col : 0),
              text: String(item.text || ''),
              type: String(item.type || 'error'),
              source: 'aceAnnotation',
            })),
          };
        }
        """ % ACE_EDITOR
    )


def _read_featurescript_notice_snapshot(page: Any) -> dict[str, Any]:
    return page.evaluate(
        FS_NOTICE_SNAPSHOT_JS,
        {
            "toggle": FS_NOTICE_TOGGLE,
            "content": FS_NOTICE_CONTENT,
            "table": FS_NOTICE_TABLE,
            "message": FS_NOTICE_MESSAGE,
            "line": FS_NOTICE_LINE,
            "column": FS_NOTICE_COLUMN,
        },
    )


def read_featurescript_notices(page: Any) -> dict[str, Any]:
    """Read every notice the pane lists and restore the notice pane state.

    Rows are NOT filtered by tab: the pane attributes each row to a document
    element, and a Part Studio regeneration failure is exactly such a row while
    a Feature Studio is the active tab. Callers that need the active editor's
    verdict split on ``isActiveTab`` instead of relying on a silent drop.
    """
    try:
        snapshot = _read_featurescript_notice_snapshot(page)
    except Exception as exc:  # noqa: BLE001 - fail closed with structured evidence
        return {
            "found": False,
            "complete": False,
            "indicatorPresent": False,
            "noticeCount": 0,
            "notices": [],
            "openedForRead": False,
            "restored": True,
            "reason": f"FeatureScript notice snapshot failed: {type(exc).__name__}: {exc}",
        }
    if not isinstance(snapshot, dict):
        return {
            "found": False,
            "complete": False,
            "noticeCount": 0,
            "notices": [],
            "reason": "FeatureScript notice snapshot was not an object",
        }

    opened_for_read = False
    restored = True
    reason = ""
    if (
        snapshot.get("indicatorPresent")
        and not snapshot.get("paneOpen")
        and not snapshot.get("notices")
    ):
        toggle = page.locator(FS_NOTICE_TOGGLE).first
        try:
            if toggle.count() != 1:
                raise RuntimeError("FeatureScript notice toggle was not found uniquely")
            toggle.click()
            opened_for_read = True
            page.locator(FS_NOTICE_CONTENT).first.wait_for(
                state="visible", timeout=5_000
            )
            refreshed = _read_featurescript_notice_snapshot(page)
            if isinstance(refreshed, dict):
                snapshot = refreshed
            else:
                reason = "FeatureScript notice snapshot was not an object after opening"
        except Exception as exc:  # noqa: BLE001 - return bounded browser evidence
            reason = f"FeatureScript notice pane unavailable: {type(exc).__name__}: {exc}"
        finally:
            if opened_for_read:
                try:
                    toggle.click()
                except Exception as exc:  # noqa: BLE001 - status evidence remains usable
                    restored = False
                    if not reason:
                        reason = f"FeatureScript notice pane could not be restored: {type(exc).__name__}: {exc}"

    complete = bool(
        not snapshot.get("indicatorPresent")
        or snapshot.get("paneOpen")
        or snapshot.get("notices")
    ) and not (reason and not snapshot.get("notices"))
    return {
        **snapshot,
        "complete": complete,
        "openedForRead": opened_for_read,
        "restored": restored,
        **({"reason": reason} if reason else {}),
    }


def _enrich_compile_errors(
    errors: list[dict[str, Any]],
    index: diagnostics.ErrorStringEnumIndex | None = None,
) -> list[dict[str, Any]]:
    """Add the normalized code and every message paragraph to each diagnostic.

    The raw notice text is the browser's unfiltered observation; this derived
    view is what a consumer groups on. ``codeBasis``/``codeStable`` state whether
    the code is server-defined or one of our compiler-message families, so a
    caller never has to guess how much to trust it.
    """
    enriched = []
    for item in errors:
        normalized = diagnostics.normalize_diagnostic(str(item.get("text", "")), index)
        messages = item.get("messages")
        enriched.append({
            **item,
            "messages": list(messages) if isinstance(messages, list) and messages
            else ([str(item.get("text"))] if str(item.get("text", "")).strip() else []),
            **normalized,
        })
    return enriched


def _notice_error_row(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one raw notice row into the compile-status diagnostic shape."""
    return {
        "row": int(item.get("row", 0)),
        "col": int(item.get("col", 0)),
        "line": item.get("line"),
        "column": item.get("column"),
        "text": str(item.get("text", "")),
        "messages": [
            str(message) for message in item.get("messages", []) if str(message).strip()
        ],
        "type": str(item.get("severity", "warning")),
        "source": "featureScriptNotice",
        "tabName": str(item.get("tabName", "")),
        "isActiveTab": bool(item.get("isActiveTab", True)),
        "outOfDate": bool(item.get("outOfDate", False)),
    }


def _split_notices(
    notices: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Split pane notices into fresh-active-tab, stale-active-tab, and other.

    A custom feature that fails to regenerate in a Part Studio is reported in
    the Feature Studio notice pane under that Part Studio's own container — often
    with that container's header carrying ``notices-out-of-date`` — so the split
    is what lets a caller keep the editor's verdict separate from the document's,
    and a fresh commit separate from a stale row.
    """
    fresh_active: list[dict[str, Any]] = []
    stale_active: list[dict[str, Any]] = []
    others: list[dict[str, Any]] = []
    for item in notices:
        if not bool(item.get("isActiveTab", True)):
            others.append(item)
        elif bool(item.get("outOfDate", False)):
            stale_active.append(item)
        else:
            fresh_active.append(item)
    return fresh_active, stale_active, others


def _blocking_notices(notices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Notices at warning-or-worse severity; ``info`` never blocks."""
    return [
        item for item in notices if str(item.get("severity", "warning")).lower() != "info"
    ]


def read_featurescript_compile_status(page: Any) -> dict[str, Any]:
    """Combine Ace annotations with the FeatureScript notice pane.

    Every returned diagnostic carries ``messages`` (all paragraphs of one notice
    table) and a self-labeled ``code``. ``diagnosticSummary`` appears only when
    there is something to summarize, so a clean compile stays small.

    ``errors``/``compiled`` stay the ACTIVE EDITOR's fresh verdict: they are what
    deployment acceptance reads, so a Part Studio that is broken elsewhere — or a
    row the pane marks ``notices-out-of-date`` — must never turn a clean
    FeatureScript commit into a failed one. The same pane observation is still
    reported in full: ``elementErrors`` covers other document elements and
    ``staleErrors`` covers out-of-date rows on the active tab, so the real
    regeneration error text is returned instead of hidden, and ``documentClean``
    states whether anything at all is failing.
    """
    index = diagnostics.error_string_enum_index()
    try:
        ace = _read_featurescript_ace_annotations(page)
    except Exception as exc:  # noqa: BLE001 - deployment must retain failure evidence
        return {
            "found": False,
            "compiled": False,
            "annotationCount": 0,
            "noticeCount": 0,
            "activeTabNoticeCount": 0,
            "elementNoticeCount": 0,
            "elementNotices": [],
            "elementErrorCount": 0,
            "elementErrors": [],
            "staleNoticeCount": 0,
            "staleNotices": [],
            "staleErrorCount": 0,
            "staleErrors": [],
            "documentClean": False,
            "errors": _enrich_compile_errors([{
                "row": 0,
                "col": 0,
                "text": f"Ace annotation read failed: {type(exc).__name__}: {exc}",
                "type": "error",
                "source": "compileObservation",
            }], index),
            "notices": [],
            "noticeReadComplete": False,
            "reason": f"Ace annotation read failed: {type(exc).__name__}: {exc}",
        }
    if not isinstance(ace, dict) or not ace.get("found"):
        ace_errors = [item for item in (ace or {}).get("errors", []) if isinstance(item, dict)]
        return {
            "found": False,
            "compiled": False,
            "annotationCount": int((ace or {}).get("annotationCount", 0)),
            "noticeCount": 0,
            "activeTabNoticeCount": 0,
            "elementNoticeCount": 0,
            "elementNotices": [],
            "elementErrorCount": 0,
            "elementErrors": [],
            "staleNoticeCount": 0,
            "staleNotices": [],
            "staleErrorCount": 0,
            "staleErrors": [],
            "documentClean": False,
            "errors": _enrich_compile_errors(ace_errors, index),
            "notices": [],
            "noticeReadComplete": False,
            "reason": (ace or {}).get("reason", "FeatureScript annotations unavailable"),
        }

    notice_status = read_featurescript_notices(page)
    notices = [item for item in notice_status.get("notices", []) if isinstance(item, dict)]
    fresh_active, stale_active, element_notices = _split_notices(notices)
    notice_errors = [_notice_error_row(item) for item in _blocking_notices(fresh_active)]
    stale_errors = _enrich_compile_errors(
        [_notice_error_row(item) for item in _blocking_notices(stale_active)], index
    )
    element_errors = _enrich_compile_errors(
        [_notice_error_row(item) for item in _blocking_notices(element_notices)], index
    )
    ace_errors = [item for item in ace.get("errors", []) if isinstance(item, dict)]
    notice_complete = bool(notice_status.get("complete"))
    errors = _enrich_compile_errors([*ace_errors, *notice_errors], index)
    document_clean = bool(
        not errors and not element_errors and not stale_errors and notice_complete
    )
    result = {
        "found": True,
        "compiled": not errors and notice_complete,
        "annotationCount": int(ace.get("annotationCount", len(ace_errors))),
        "noticeCount": len(notices),
        "activeTabName": str(notice_status.get("activeTabName", "")),
        "activeTabNoticeCount": len(fresh_active),
        "elementNoticeCount": len(element_notices),
        "elementNotices": element_notices,
        "elementErrorCount": len(element_errors),
        "elementErrors": element_errors,
        "staleNoticeCount": len(stale_active),
        "staleNotices": stale_active,
        "staleErrorCount": len(stale_errors),
        "staleErrors": stale_errors,
        "documentClean": document_clean,
        "errorCount": sum(1 for item in errors if str(item.get("type", "")).lower() == "error"),
        "warningCount": sum(1 for item in errors if str(item.get("type", "")).lower() == "warning"),
        "errors": errors,
        "notices": notices,
        "noticeReadComplete": notice_complete,
        "noticePaneOpenedForRead": bool(notice_status.get("openedForRead")),
        "noticePaneRestored": bool(notice_status.get("restored", True)),
    }
    container_titles = notice_status.get("containerTitles")
    if isinstance(container_titles, list):
        result["noticeContainerTitles"] = [
            str(title) for title in container_titles if str(title).strip()
        ][:20]
    pane_structure = {
        key: notice_status[key]
        for key in ("unstructuredContainers", "paneClassNames")
        if notice_status.get(key)
    }
    if pane_structure:
        result["noticePaneStructure"] = pane_structure
    if element_errors:
        result["elementDiagnosticSummary"] = diagnostics.inline_diagnostic_summary(
            diagnostics.summarize_diagnostics({"errors": element_errors}, index=index)
        )
    if stale_errors:
        result["staleDiagnosticSummary"] = diagnostics.inline_diagnostic_summary(
            diagnostics.summarize_diagnostics({"errors": stale_errors}, index=index)
        )
    if errors:
        result["diagnosticSummary"] = diagnostics.inline_diagnostic_summary(
            diagnostics.summarize_diagnostics({"errors": errors}, index=index)
        )
    if not notice_complete:
        result["reason"] = str(
            notice_status.get("reason", "FeatureScript notice indicator present but notices were not readable")
        )
    return result


def _featurescript_symbol_kind(icon: str) -> str:
    """Map the Module-outline glyph to a stable public symbol kind."""
    if icon == "C":
        return "const"
    if icon == "Φ":
        return "feature"
    return "function"


def read_featurescript_symbols(page: Any) -> dict[str, Any]:
    """Open Module outline and return its normalized top-level symbols."""
    dropdown = page.locator(FS_MODULE_OUTLINE_DROPDOWN).first
    try:
        visible = dropdown.count() > 0 and dropdown.is_visible()
        if not visible:
            button = page.locator(FS_MODULE_OUTLINE).first
            if button.count() == 0:
                return {
                    "found": False,
                    "symbolCount": 0,
                    "symbols": [],
                    "reason": "Module outline button not found",
                }
            button.click()
            page.locator(FS_MODULE_OUTLINE_LIST).first.wait_for(
                state="visible", timeout=10_000
            )
    except Exception as exc:  # noqa: BLE001 - structured browser failure
        return {
            "found": False,
            "symbolCount": 0,
            "symbols": [],
            "reason": f"Module outline unavailable: {type(exc).__name__}: {exc}",
        }

    raw = page.evaluate(
        """
        (selectors) => ({
          found: true,
          items: Array.from(document.querySelectorAll(selectors.item)).map((item) => ({
            rawIcon: (item.querySelector(selectors.icon)?.textContent || '').trim(),
            displayName: (item.querySelector(selectors.name)?.textContent || '').trim(),
          })),
        })
        """,
        {
            "item": FS_MODULE_OUTLINE_ITEM,
            "icon": FS_MODULE_OUTLINE_ICON,
            "name": FS_MODULE_OUTLINE_NAME,
        },
    )
    if not isinstance(raw, dict) or not raw.get("found"):
        return {
            "found": False,
            "symbolCount": 0,
            "symbols": [],
            "reason": "Module outline symbols could not be read",
        }
    symbols = []
    for item in raw.get("items", []):
        if not isinstance(item, dict):
            continue
        display_name = str(item.get("displayName", "")).strip()
        name = display_name.split("(", 1)[0].strip()
        if not name:
            continue
        raw_icon = str(item.get("rawIcon", "")).strip()
        symbols.append({
            "kind": _featurescript_symbol_kind(raw_icon),
            "name": name,
            "displayName": display_name,
            "rawIcon": raw_icon,
        })
    return {
        "found": True,
        "symbolCount": len(symbols),
        "symbols": symbols,
    }


def write_featurescript_editor(page: Any, text: str) -> dict[str, Any]:
    """Replace the FeatureScript editor content in place.

    Uses the Ace API (not DOM textarea) so Onshape's change detection sees the
    edit and enables the Commit button.
    """
    return page.evaluate(
        """
        (text) => {
          const el = document.querySelector('.ace_editor');
          if (!el) return {ok: false, error: 'no .ace_editor on page'};
          const ed = (el.env && el.env.editor) || (window.ace && window.ace.edit(el));
          if (!ed) return {ok: false, error: 'ace editor API unavailable'};
          ed.setValue(text);
          ed.clearSelection();
          ed.moveCursorTo(0, 0);
          return {ok: true, length: text.length, lineCount: text.split('\\n').length};
        }
        """,
        text,
    )


def commit_button_state(page: Any) -> dict[str, Any]:
    """Report whether the FeatureScript Commit button exists and is enabled."""
    return page.evaluate(
        """
        () => {
          const btn = Array.from(document.querySelectorAll('.tool.is-activatable.is-button'))
            .find(b => (b.innerText || '').trim() === '提交');
          if (!btn) return {found: false};
          return {
            found: true,
            disabled: btn.className.includes('disabled'),
            cls: (typeof btn.className === 'string' ? btn.className : '').slice(0, 120),
          };
        }
        """
    )


def click_commit(page: Any) -> dict[str, Any]:
    """Click the FeatureScript Commit button and report the new button state."""
    before = commit_button_state(page)
    if not before.get("found"):
        return {"clicked": False, "before": before, "error": "commit button not found"}
    try:
        page.locator(FS_COMMIT_BUTTON).first.click()
        page.wait_for_timeout(3000)
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {"clicked": False, "before": before, "error": f"{type(exc).__name__}: {exc}"}
    after = commit_button_state(page)
    return {"clicked": True, "before": before, "after": after}


_DOCUMENT_URL_RE = re.compile(r"/documents/([^/]+)(?:/w/([^/]+))?(?:/e/([^/]+))?")


def parse_document_url(url: str) -> dict[str, str | None]:
    """Extract documentId/workspaceId/elementId from an Onshape URL.

    Handles both the documents-list form (``/documents/<did>``) and the opened
    tab form (``/documents/<did>/w/<wid>/e/<eid>``). Unknown shapes return all
    None values, never raise.
    """
    match = _DOCUMENT_URL_RE.search(url or "")
    if not match:
        return {"documentId": None, "workspaceId": None, "elementId": None}
    return {
        "documentId": match.group(1) or None,
        "workspaceId": match.group(2) or None,
        "elementId": match.group(3) or None,
    }


def create_document(page: Any, name: str = "") -> dict[str, Any]:
    """Create a new Onshape document from the documents page (0 API quota).

    Goes to the documents list, opens the Create menu, clicks "文档…", fills the
    document-name input (default "无标题文档" when empty), and clicks "创建".
    Returns the new document URL and parsed document/workspace ids.
    """
    try:
        page.goto(
            "https://cad.onshape.com/documents",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        page.wait_for_timeout(4000)
        page.locator("#create-new-type").first.click()
        page.wait_for_timeout(1000)
        page.locator(".create-new-document").first.click()
        page.wait_for_timeout(2000)
        if name:
            page.locator("#document-name-input").first.fill(name)
            page.wait_for_timeout(500)
        page.locator(".new-document-dialog .btn-primary").first.click()
        page.wait_for_timeout(8000)
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {"created": False, "error": f"{type(exc).__name__}: {exc}", "pageUrl": page.url}

    url = page.url
    return {"created": True, "pageUrl": url, **parse_document_url(url)}


def create_document_tab(page: Any, tab_type: str = "Feature Studio") -> dict[str, Any]:
    """Create a new document tab (Feature Studio / Part Studio / Assembly /
    Drawing) via the tabs menu.

    The dropdown items are present but hidden until the menu opens; a plain
    Playwright click on a hidden item fails, so the item is clicked in page
    JavaScript. Adding a tab creates an Onshape document element (a cloud
    mutation) but spends zero REST API quota.
    """
    try:
        before_state = list_document_tabs(page)
        before_names = {tab.get("name", "") for tab in before_state.get("tabs", [])}
        before_tabs_readable = True
    except Exception:  # noqa: BLE001 - creation can still be attempted
        before_names = set()
        before_tabs_readable = False

    create_item_text = {
        "Feature Studio": "创建 Feature Studio",
        "Part Studio": "创建 Part Studio",
        "Assembly": "创建装配体",
        "Drawing": "创建工程图",
    }
    needle = create_item_text.get(tab_type, "创建 " + tab_type)

    clicked_item = page.evaluate(
        """
        (needle) => {
          const items = Array.from(document.querySelectorAll('a.dropdown-item, .dropdown-item, li.dropdown-item'));
          const item = items.find(el => ((el.textContent || '').replace(/\\s+/g, ' ')).includes(needle.replace(/\\s+/g, ' ')));
          if (!item) {
            return {clicked: false, reason: 'dropdown item not found',
                    items: items.map(el => (el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80))};
          }
          item.click();
          return {clicked: true, text: (item.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 80)};
        }
        """,
        needle,
    )
    if not clicked_item.get("clicked"):
        return {
            **clicked_item,
            "triggered": False,
            "created": False,
            "tabType": tab_type,
            "pageUrl": page.url,
        }
    page.wait_for_timeout(8000)

    try:
        tab_state = list_document_tabs(page)
        after_tabs = tab_state.get("tabs", [])
        new_tabs = [tab for tab in after_tabs if tab.get("name", "") not in before_names]
        tab_read_error = None
    except Exception as exc:  # noqa: BLE001 - return a structured partial result
        tab_state = {"tabs": [], "hasDocumentTabsToolButton": None}
        new_tabs = []
        tab_read_error = f"{type(exc).__name__}: {exc}"

    created = before_tabs_readable and bool(new_tabs)
    result = {
        "triggered": True,
        "created": created,
        "beforeTabsReadable": before_tabs_readable,
        "tabType": tab_type,
        "clickedItem": clicked_item.get("text", ""),
        "newTabs": new_tabs,
        **tab_state,
        "pageUrl": page.url,
    }
    if tab_read_error:
        result["tabReadError"] = tab_read_error
    if not before_tabs_readable:
        result["reason"] = "creation flow triggered but the previous tab state was unreadable; creation is unverified"
    elif not created:
        result["reason"] = "creation flow triggered but no new tab is visible; complete any open dialog"
    return result


def rename_tab(page: Any, name: str, new_name: str) -> dict[str, Any]:
    """Rename a document tab (Feature Studio / Part Studio) by its visible name.

    Right-clicks the tab, picks 重命名 from the context menu, fills the rename
    input with the new name and commits with Enter. Uses real Playwright input
    (trusted events) so Angular processes the rename. Zero Onshape API quota.
    """
    from onshape_browser_mode.selectors import (
        TAB_BAR_TAB,
        TAB_CONTEXT_MENU_ITEM,
        TAB_RENAME_INPUT,
    )

    new_name = (new_name or "").strip()
    if not new_name:
        return {"renamed": False, "reason": "new_name must be non-empty", "pageUrl": page.url}

    # 1. Right-click the tab and pick 重命名.
    try:
        tab = page.locator(TAB_BAR_TAB).filter(has_text=name)
        if tab.count() == 0:
            return {"renamed": False, "reason": f"tab {name!r} not found", "pageUrl": page.url}
        dismiss_stale_context_menu(page)
        tab.first.click(button="right")
        page.wait_for_timeout(2000)
        item = page.locator(TAB_CONTEXT_MENU_ITEM).filter(has_text="重命名")
        if item.count() == 0:
            return {"renamed": False, "reason": "重命名 menu item not found", "pageUrl": page.url}
        item.first.click()
        page.wait_for_timeout(1500)
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {"renamed": False, "reason": f"rename-menu click failed: {exc}", "pageUrl": page.url}

    # 2. Fill the rename input and commit with Enter (trusted Playwright input).
    try:
        input_locator = page.locator(TAB_RENAME_INPUT)
        if input_locator.count() == 0:
            return {"renamed": False, "reason": "rename input not found", "pageUrl": page.url}
        input_locator.first.click()
        input_locator.first.fill(new_name)
        input_locator.first.press("Enter")
        page.wait_for_timeout(3000)
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {"renamed": False, "reason": f"rename input failed: {exc}", "pageUrl": page.url}

    tabs = list_document_tabs(page)
    renamed = any(t.get("name") == new_name for t in tabs.get("tabs", []))
    return {"renamed": renamed, **tabs, "pageUrl": page.url}


def _tab_locators_by_id(page: Any, element_id: str) -> list[Any]:
    """Return exact data-id matches without interpolating caller text into CSS."""
    from onshape_browser_mode.selectors import TAB_BAR_TAB

    rows = page.locator(TAB_BAR_TAB)
    matches = []
    for index in range(rows.count()):
        row = rows.nth(index)
        try:
            if row.get_attribute("data-id") == element_id:
                matches.append(row)
        except Exception:
            continue
    return matches


def delete_element_by_id(page: Any, element_id: str) -> dict[str, Any]:
    """Delete exactly one visible tab by observed data-id and verify REMOVAL.

    The verdict is the element id leaving the visible tab strip, not the node
    detaching: a removed tab is marked ``hidden`` first and detached later, and
    the previous positional ``state="detached"`` wait could never be satisfied
    (see :func:`wait_for_tab_removed`).
    """
    from onshape_browser_mode.selectors import DIALOG_ACCEPT, TAB_CONTEXT_MENU_ITEM

    matches = _tab_locators_by_id(page, element_id)
    if len(matches) != 1:
        return {
            "deleted": False,
            "elementId": element_id,
            "matchCount": len(matches),
            "reason": "element data-id must match exactly one visible tab",
            "pageUrl": page.url,
        }
    tab = matches[0]
    try:
        dismiss_stale_context_menu(page)
        tab.click(button="right")
        candidates = page.locator(TAB_CONTEXT_MENU_ITEM)
        exact_visible = []
        for index in range(candidates.count()):
            candidate = candidates.nth(index)
            try:
                if candidate.is_visible() and candidate.inner_text().strip() == "删除":
                    exact_visible.append(candidate)
            except Exception:
                continue
        if len(exact_visible) != 1:
            return {
                "deleted": False,
                "elementId": element_id,
                "reason": "exact unique visible 删除 menu item not found",
                "pageUrl": page.url,
            }
        exact_visible[0].click()
        confirm = page.locator(DIALOG_ACCEPT)
        if confirm.count() > 0:
            confirm.first.click()
    except Exception as exc:  # noqa: BLE001
        return {"deleted": False, "elementId": element_id, "reason": str(exc), "pageUrl": page.url}
    removal = wait_for_tab_removed(page, element_id)
    tabs = list_document_tabs(page)
    # `list_document_tabs` does not filter removed nodes, so a ``hidden`` tab can
    # still be listed while the document no longer has it. ``removal`` (the
    # data-id wait) is the verdict; the raw read is returned for diagnosis.
    still_listed = [
        tab.get("id") for tab in tabs.get("tabs", []) if tab.get("id") == element_id
    ]
    deleted = bool(removal.get("waited"))
    result = {
        "deleted": deleted,
        "elementId": element_id,
        "removal": removal,
        "stillListedIds": still_listed,
        **tabs,
        "pageUrl": page.url,
    }
    if not deleted:
        result["reason"] = (
            f"the tab {element_id!r} is still a visible document tab after "
            f"{removal.get('elapsedMs')} ms"
        )
    return result


def wait_for_tab_removed(
    page: Any,
    element_id: str,
    timeout_ms: int = TAB_DELETE_TIMEOUT_MS,
) -> dict[str, Any]:
    """Wait until a tab carrying ``element_id`` is gone, or marked removed.

    The wait is on the ``data-id``, never on a position. Measured live 2026-09-20:
    the previous check was ``locator.nth(i).wait_for(state="detached")``, and a tab
    strip is an ``ng-repeat`` list — removing a tab re-numbers it, so ``nth(i)``
    re-resolved to the tab that moved into the freed slot, which is attached. The
    wait could therefore never be satisfied: it timed out after 30 s on a tab that
    had in fact been deleted, the exception became ``deleted: false``, and
    ``browser_get_page_tabs`` immediately afterwards no longer listed the tab.

    Timeout is returned as data, never raised: the caller reports the verdict.
    """
    from onshape_browser_mode.selectors import TAB_BAR_TAB

    started = time.monotonic()
    try:
        page.wait_for_function(
            _TAB_REMOVED_PREDICATE,
            arg={"selector": TAB_BAR_TAB, "id": element_id},
            timeout=timeout_ms,
        )
        waited, error = True, ""
    except Exception as exc:  # noqa: BLE001 - a timeout is evidence, not a crash
        waited, error = False, f"{type(exc).__name__}: {exc}"
    return {
        "waited": waited,
        "condition": "tab_removed_or_hidden",
        "elementId": element_id,
        "timeoutMs": timeout_ms,
        "elapsedMs": round((time.monotonic() - started) * 1000),
        **({"error": error} if error else {}),
    }


def activate_tab(
    page: Any,
    *,
    element_id: str = "",
    name: str = "",
    content: str = "any",
    timeout_ms: int = TAB_ACTIVATE_TIMEOUT_MS,
) -> dict[str, Any]:
    """Make one EXISTING document tab the active tab, by ``data-id`` or exact name.

    Read tools and the dialog-edit transaction act on whatever tab happens to be
    active, and until now nothing could select one. Measured live 2026-09-20:
    ``browser_rename_tab`` double-clicks a tab NAME but leaves the previously active
    tab active, and the only tab switches in the codebase were a byproduct of
    ``insert_custom_feature(part_studio_tab=...)``. That is why a small-element
    end-to-end run could not be substituted for an 11-feature element.

    Selection goes through ``data-id`` whenever one is known — and the tab listing
    itself supplies it — never through a position: the tab strip is an ``ng-repeat``
    list, so removing or adding a tab renumbers it (the same property that made the
    old positional delete wait unsatisfiable). ``name`` resolution requires exactly
    one exact match, so an ambiguous name is a refusal and not a guess.

    The verdict is the tab's own ``active`` class for that ``data-id``, read in the
    page; ``content="partstudio"`` additionally waits for the feature-list header and
    whose rows, because a switched-to Part Studio renders in stages and a read taken
    immediately after the switch sees zero rows.
    """
    from onshape_browser_mode.selectors import TAB_BAR_TAB

    if not element_id and not name:
        raise ValueError("either element_id or name is required")
    if content not in {"any", "partstudio"}:
        raise ValueError("content must be any or partstudio")
    before = list_document_tabs(page)
    tabs = before.get("tabs", [])
    active_before = next((tab.get("id", "") for tab in tabs if tab.get("active")), "")
    matches = (
        [tab for tab in tabs if tab.get("id") == element_id]
        if element_id
        else [tab for tab in tabs if tab.get("name") == name]
    )
    if len(matches) != 1:
        return {
            "activated": False,
            "elementId": element_id,
            "name": name,
            "matchCount": len(matches),
            "activeBefore": active_before,
            "activeAfter": active_before,
            "reason": (
                "element_id must match exactly one visible tab"
                if element_id
                else f"tab name {name!r} must match exactly one visible tab"
            ),
            "tabs": tabs,
        }
    target_id = matches[0].get("id", "")
    if not target_id:
        return {
            "activated": False,
            "name": matches[0].get("name", ""),
            "activeBefore": active_before,
            "activeAfter": active_before,
            "reason": "the matched tab carries no data-id",
            "tabs": tabs,
        }

    already_active = active_before == target_id
    started = time.monotonic()
    clicked = False
    if not already_active:
        try:
            dismiss_stale_context_menu(page)
            page.locator(f'{TAB_BAR_TAB}[data-id="{target_id}"]').first.click()
            clicked = True
        except Exception as exc:  # noqa: BLE001 - a failed click is evidence
            return {
                "activated": False,
                "elementId": target_id,
                "name": matches[0].get("name", ""),
                "clicked": False,
                "activeBefore": active_before,
                "activeAfter": active_before,
                "reason": f"the tab {target_id!r} could not be clicked: {type(exc).__name__}: {exc}",
                "tabs": list_document_tabs(page).get("tabs", []),
            }

    try:
        page.wait_for_function(
            _TAB_ACTIVE_PREDICATE,
            arg={"selector": TAB_BAR_TAB, "id": target_id},
            timeout=timeout_ms,
        )
        waited, wait_error = True, ""
    except Exception as exc:  # noqa: BLE001 - a timeout is evidence, not a crash
        waited, wait_error = False, f"{type(exc).__name__}: {exc}"

    content_ready: dict[str, Any] = {}
    if waited and content == "partstudio":
        try:
            page.locator(PS_FEATURES_HEADER).first.wait_for(
                state="visible", timeout=PARTSTUDIO_PANEL_READY_TIMEOUT_MS
            )
            header_visible = True
        except Exception:  # noqa: BLE001
            header_visible = False
        content_ready = {
            "headerVisible": header_visible,
            "rows": wait_for_panel_rows(page, PARTSTUDIO_PANEL_READY_TIMEOUT_MS),
        }

    after = list_document_tabs(page)
    active_after = next(
        (tab.get("id", "") for tab in after.get("tabs", []) if tab.get("active")), ""
    )
    activated = waited and active_after == target_id
    result = {
        "activated": activated,
        "elementId": target_id,
        "name": matches[0].get("name", ""),
        "alreadyActive": already_active,
        "clicked": clicked,
        "activeBefore": active_before,
        "activeAfter": active_after,
        "wait": {
            "condition": "tab_active_class",
            "waited": waited,
            "timeoutMs": timeout_ms,
            "elapsedMs": round((time.monotonic() - started) * 1000),
            **({"error": wait_error} if wait_error else {}),
        },
        "content": content,
        "tabs": after.get("tabs", []),
    }
    if content_ready:
        result["contentReady"] = content_ready
    if not activated:
        result["reason"] = (
            f"the tab {target_id!r} is not the active tab after {timeout_ms} ms"
        )
    return result


def delete_tab(page: Any, name: str) -> dict[str, Any]:
    """Compatibility wrapper: resolve one exact visible name, then delete by ID."""
    tabs = list_document_tabs(page)
    exact = [tab for tab in tabs.get("tabs", []) if tab.get("name") == name]
    if len(exact) != 1:
        return {
            "deleted": False,
            "name": name,
            "matchCount": len(exact),
            "reason": "tab name must match exactly one visible tab; prefer browser_delete_element",
            **tabs,
            "pageUrl": page.url,
        }
    element_id = exact[0].get("id")
    if not isinstance(element_id, str) or not element_id:
        return {
            "deleted": False,
            "name": name,
            "reason": "exact tab has no observable data-id; use browser_delete_element when ID is available",
            **tabs,
            "pageUrl": page.url,
        }
    return {**delete_element_by_id(page, element_id), "resolvedName": name, "compatibilityWrapper": True}


def open_document_by_name(
    page: Any,
    document_name: str,
    entry_url: str | None = None,
) -> dict[str, Any]:
    """Open a document from the documents list by its visible name.

    This is read-only navigation (no Onshape data is created or changed): go to
    the documents list, click the matching document link, and wait for the SPA
    to settle. Returns the resulting URL and parsed ids.
    """
    from onshape_browser_mode.session import _is_onshape_app_url

    try:
        current = page.url
    except Exception:
        current = None

    if not _is_onshape_app_url(current) or read_featurescript_editor(page) is not None:
        pass  # keep going through the list entry to reach the named document

    try:
        page.goto(
            entry_url or "https://cad.onshape.com/documents",
            wait_until="domcontentloaded",
            timeout=60_000,
        )
        page.wait_for_timeout(4000)
    except Exception as exc:
        return {"opened": False, "error": f"navigate to documents failed: {exc}", "pageUrl": page.url}

    try:
        locator = page.get_by_text(document_name, exact=False)
        count = locator.count()
        if count == 0:
            return {"opened": False, "error": f"document not found: {document_name!r}", "pageUrl": page.url}
        locator.first.click()
        page.wait_for_timeout(5000)
    except Exception as exc:
        return {"opened": False, "error": f"click document failed: {exc}", "pageUrl": page.url}

    url = page.url
    return {
        "opened": True,
        "pageUrl": url,
        **parse_document_url(url),
    }


def read_partstudio_features(page: Any) -> dict[str, Any]:
    """Read the Part Studio feature tree and part list (read-only, 0 quota).

    Returns the feature-list header, each feature item with its user/default
    classification, and the part-list text (e.g. "零件数 (132) base ...").
    A custom feature present in the list means its FeatureScript compiled and
    was instantiated successfully.
    """
    return page.evaluate(
        """
        () => {
          const features = Array.from(document.querySelectorAll('.os-list-item')).map(el => {
            const icon = el.querySelector('.os-list-item-icon');
            const cls = el.className || '';
            return {
              name: (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 100),
              isUserFeature: cls.includes('ns-user-feature'),
              isDefault: cls.includes('ns-default-feature'),
              className: String(cls).slice(0, 180),
              hasError: /error|not-computed|未计算|错误/i.test(cls + ' ' + (el.innerText || el.textContent || '')),
              iconCls: icon ? (typeof icon.className === 'string' ? icon.className : '').slice(0, 90) : '',
            };
          }).filter(f => f.name);
          const header = document.querySelector('.features-title');
          const partsEl = document.querySelector('.part-list-container');
          return {
            headerText: header ? (header.innerText || header.textContent || '').trim() : '',
            features,
            partsText: partsEl ? (partsEl.innerText || partsEl.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 400) : '',
            // Part-name rows as ELEMENTS, in DOM order. `partsText` is whitespace
            // folded and must never be split into names (measured live
            // 2026-09-20: the `count == 1` branch swallowed the next section
            // header into the name, `曲线数 (1)`, and `count > 1` produced no
            // names at all). The folded text stays as the count's source and as
            // the evidence for what the panel actually rendered.
            partItems: Array.from(document.querySelectorAll('.os-list-item')).filter(el => {
              const icon = el.querySelector('.os-list-item-icon');
              return String((icon && icon.className) || '').includes('os-part-list-icon');
            }).map(el => (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 100)),
          };
        }
        """
    )


def match_user_feature_row_indices(names: Any, feature_name: Any) -> list[int]:
    """Positions of the rows whose name contains ``feature_name``, case-insensitive.

    The ONE matching rule for custom-feature rows. Presence (``feature_state``)
    and the dialog edit path's row choice both call it, so a presence check and a
    click cannot drift apart. An empty row name never matches, and an empty
    ``feature_name`` matches nothing rather than everything.
    """
    wanted = str(feature_name or "").strip().lower()
    if not wanted or not isinstance(names, (list, tuple)):
        return []
    return [index for index, name in enumerate(names) if wanted in str(name).lower()]


def enumerate_user_feature_rows(page: Any, selector: str) -> dict[str, Any]:
    """Enumerate the custom-feature rows ONCE: their names and their count.

    Identity and position must come from one enumeration. Measured live
    2026-09-20: ``read_partstudio_features`` drops any row whose ``innerText`` and
    ``textContent`` are both empty (its collector ends with ``.filter(f => f.name)``),
    while ``page.locator('.os-list-item.ns-user-feature')`` counts it; comparing
    the two therefore reported a constant +1 on every Part Studio — 1 named row
    against 2, and 11 against 12 — so the dialog edit path refused on both. Both
    ``querySelectorAll`` and ``page.locator`` are document order, so an index taken
    from this list addresses the row the name came from.

    A malformed answer is returned as an empty enumeration instead of raised: the
    caller has to report "0 rows" as evidence rather than crash on it.
    """
    result = page.evaluate(_USER_FEATURE_ROWS_JS, {"selector": selector})
    if not isinstance(result, dict):
        return {"count": 0, "names": []}
    raw_names = result.get("names")
    names = [str(name) for name in raw_names] if isinstance(raw_names, list) else []
    try:
        count = max(0, int(result.get("count", len(names))))
    except (TypeError, ValueError):
        count = len(names)
    return {"count": count, "names": names}


def feature_state(features: Any, feature_name: str) -> dict[str, Any]:
    """Presence AND computedness of a named user feature in a read feature list.

    Presence and computedness are different facts. The recorded experience is
    explicit that a `not-computed` row still appears in the Feature List, and
    that a picker entry, a bare `feature-id`, or a row without computed geometry
    is not proof of success. Presence alone would therefore accept a feature that
    never computed, so both signals are returned from one matching rule.

    ``errored`` is a UI signal, not a domain verdict: an error class can be
    visible while the workbench is still regenerating, which is why callers
    report it instead of retrying anything.
    """
    empty = {"listed": False, "errored": False, "names": [], "rows": []}
    if not isinstance(features, dict) or not isinstance(feature_name, str):
        return empty
    items = features.get("features")
    if not isinstance(items, list):
        return empty
    candidates = [
        {
            "name": str(item.get("name", "")),
            "hasError": bool(item.get("hasError")),
        }
        for item in items
        if isinstance(item, dict) and item.get("isUserFeature")
    ]
    names = [row["name"] for row in candidates]
    rows = [candidates[index] for index in match_user_feature_row_indices(names, feature_name)]
    return {
        "listed": bool(rows),
        "errored": any(row["hasError"] for row in rows),
        "names": [row["name"] for row in rows],
        "rows": rows,
    }


def feature_listed(features: Any, feature_name: str) -> bool:
    """Whether a read Part Studio feature list contains the named user feature.

    This is the single presence rule used by both the apply path and
    ``semantic.build_part``; an empty name is never a match. Callers that need to
    know whether the row actually computed use :func:`feature_state`.
    """
    return feature_state(features, feature_name)["listed"]


def list_document_tabs(page: Any) -> dict[str, Any]:
    """List the document tabs (e.g. Feature Studio / Part Studio) on screen.

    Read-only and 0 quota. Returns each tab's name and whether it is the active
    tab, plus the page URL. Used to find the Part Studio tab to insert into or
    the Feature Studio tab to deploy to.
    """
    return page.evaluate(
        """
        () => {
          const tabs = Array.from(document.querySelectorAll('.os-tab-bar-tab')).map(el => {
            const nameEl = el.querySelector('.os-tab-name');
            const name = (nameEl ? (nameEl.innerText || nameEl.textContent || '') : (el.innerText || el.textContent || '')).trim().replace(/\\s+/g, ' ');
            const cls = el.className || '';
            const elementType = el.getAttribute('data-element-type') || el.getAttribute('data-type') || '';
            return {
              id: el.getAttribute('data-id') || '',
              name,
              elementType,
              active: cls.includes('active'),
            };
          });
          const documentTabsToolButton = document.querySelector('.document-tabs-button');
          return { tabs, hasDocumentTabsToolButton: !!documentTabsToolButton };
        }
        """
    )


def dismiss_stale_context_menu(page: Any) -> dict[str, Any]:
    """Dismiss a pointer-blocking context-menu layer before a tab click."""
    expression = """
        (selector) => {
          const layer = document.querySelector(selector);
          if (!layer) return {present: false, blocking: false};
          const rect = layer.getBoundingClientRect();
          const style = window.getComputedStyle(layer);
          return {
            present: true,
            blocking: style.pointerEvents !== 'none' && rect.width > 0 && rect.height > 0,
            childCount: layer.childElementCount,
          };
        }
    """
    before = page.evaluate(expression, CONTEXT_MENU_LAYER)
    if not isinstance(before, dict) or not before.get("blocking"):
        return {"attempted": False, "dismissed": False, "before": before}
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        after = page.evaluate(expression, CONTEXT_MENU_LAYER)
    except Exception as exc:  # noqa: BLE001 - structured browser failure
        return {
            "attempted": True,
            "dismissed": False,
            "before": before,
            "reason": f"{type(exc).__name__}: {exc}",
        }
    return {
        "attempted": True,
        "dismissed": isinstance(after, dict) and not after.get("blocking", False),
        "before": before,
        "after": after,
    }


def reload_page(page: Any) -> dict[str, Any]:
    """Reload the current page with bounded waits and best-effort state."""
    warnings = []
    reloaded = True
    try:
        page.reload(wait_until="commit", timeout=15000)
    except Exception as exc:  # noqa: BLE001 - navigation may still have started
        reloaded = False
        warnings.append(f"reload: {type(exc).__name__}: {exc}")

    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception as exc:  # noqa: BLE001 - report partial recovery state
        warnings.append(f"domcontentloaded: {type(exc).__name__}: {exc}")

    try:
        current_url = page.url
    except Exception as exc:  # noqa: BLE001 - best effort after reload
        current_url = None
        warnings.append(f"url: {type(exc).__name__}: {exc}")

    try:
        tab_state = {"tabsReadable": True, **list_document_tabs(page)}
    except Exception as exc:  # noqa: BLE001 - execution context may be rebuilding
        tab_state = {"tabs": [], "hasDocumentTabsToolButton": None, "tabsReadable": False}
        warnings.append(f"tabs: {type(exc).__name__}: {exc}")

    return {
        "reloadAttempted": True,
        "reloaded": reloaded,
        "warnings": warnings,
        "pageUrl": current_url,
        **tab_state,
    }


def open_insert_custom_feature_dialog(page: Any) -> dict[str, Any]:
    """Click the Part Studio toolbar's "添加自定义特征" button to open the dialog.

    The toolbar label span is hidden (``.tool-label.hide-in-toolbar``), so the
    click targets the visible ``.tool.is-button`` inside the toolbar item whose
    textContent contains 添加自定义特征.
    """
    clicked = page.evaluate(
        """
        () => {
          const items = Array.from(document.querySelectorAll('.toolbar-item'));
          const item = items.find(el => (el.textContent || '').includes('添加自定义特征'));
          if (!item) return {clicked: false, reason: 'toolbar item not found'};
          const btn = item.querySelector('.tool.is-button');
          if (!btn) return {clicked: false, reason: 'toolbar button not found'};
          btn.click();
          return {clicked: true};
        }
        """
    )
    page.wait_for_timeout(2500)
    dialog = page.evaluate(
        """
        () => {
          const dlg = document.querySelector('.feature-studio-insert-dialog');
          return { present: !!dlg, text: dlg ? (dlg.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 200) : '' };
        }
        """
    )
    return {**clicked, "dialog": dialog}


def read_insert_dialog(page: Any) -> dict[str, Any]:
    """Read the insert-custom-feature dialog state (read-only)."""
    return page.evaluate(
        """
        () => {
          const dlg = document.querySelector('.feature-studio-insert-dialog');
          if (!dlg) return { present: false };
          const tabs = Array.from(dlg.querySelectorAll('.os-dialog-tab')).map(
            el => ({ text: (el.innerText || el.textContent || '').trim(), active: (el.className || '').includes('active') })
          );
          const docNameEl = dlg.querySelector('.select-item-dialog-document-name');
          const warning = dlg.querySelector('.select-item-warning');
          const prompt = dlg.querySelector('.select-item-prompt-save-version');
          return {
            present: true,
            tabs,
            docName: docNameEl ? (docNameEl.innerText || docNameEl.textContent || '').trim() : '',
            warning: warning ? (warning.innerText || warning.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 200) : '',
            promptSaveVersion: !!prompt,
          };
        }
        """
    )


def feature_label(item: Any) -> str:
    """The feature NAME of one workspace custom-feature dropdown row.

    A row renders as
    ``<div class="tool-icon"><div class="tool-initials-icon">Bf</div></div>``
    ``<span class="tool-label">Bounded fillet</span>``, so the row's own text is
    ``"Bf\\nBounded fillet"``. The name is the ``.tool-label`` element; a row
    with no label element falls back to its last non-empty text line so that an
    older row shape still resolves instead of silently matching nothing.
    """
    try:
        label = item.locator(CUSTOM_FEATURE_MENU_LABEL)
        if label.count():
            text = label.first.inner_text().strip()
            if text:
                return text
    except Exception:  # noqa: BLE001 - the text fallback is the designed path
        pass
    lines = [line.strip() for line in str(item.inner_text()).splitlines() if line.strip()]
    return lines[-1] if lines else ""


def partstudio_wait_budget_ms(profile: dict[str, int], feature_count: Any) -> int:
    """Scale one post-insert wait budget with the element's custom-feature count.

    ``baseMs + perFeatureMs * count``, clamped to ``maxMs``. A missing or
    unreadable count (the read can land while the panel is mid-render) is treated
    as 0, which reproduces the previous fixed budget exactly rather than silently
    shortening it.
    """
    try:
        count = max(0, int(feature_count))
    except (TypeError, ValueError):
        count = 0
    budget = int(profile["baseMs"]) + int(profile["perFeatureMs"]) * count
    return min(int(profile["maxMs"]), budget)


def count_custom_features(features: Any) -> int:
    """Custom features in a read Feature List — the reload's recompute load.

    The post-insert cost is dominated by re-evaluating the element's user
    features, so that is what the adaptive budgets scale on, not the number of
    rows matching one feature name.
    """
    if not isinstance(features, dict):
        return 0
    items = features.get("features")
    if not isinstance(items, list):
        return 0
    return sum(
        1
        for item in items
        if isinstance(item, dict) and item.get("isUserFeature")
    )


def wait_for_panel_rows(
    page: Any,
    timeout_ms: int,
    *,
    minimum: int = 1,
) -> dict[str, Any]:
    """Wait until the Feature List has rendered at least ``minimum`` rows.

    Used after a tab switch, where the panel title is visible before its rows.
    Failure is reported, never raised: the caller still has to attempt its click
    and can decide with the evidence in hand.
    """
    started = time.monotonic()
    try:
        page.wait_for_function(
            _PANEL_ROW_COUNT_PREDICATE,
            arg={"selector": PARTSTUDIO_FEATURE_ITEM, "minimum": minimum},
            timeout=timeout_ms,
        )
        waited, error = True, ""
    except Exception as exc:  # noqa: BLE001 - a timeout is evidence, not a crash
        waited, error = False, f"{type(exc).__name__}: {exc}"
    return {
        "waited": waited,
        "condition": "partstudio_row_count",
        "minimum": minimum,
        "timeoutMs": timeout_ms,
        "elapsedMs": round((time.monotonic() - started) * 1000),
        **({"error": error} if error else {}),
    }


def wait_for_feature_list(
    page: Any,
    timeout_ms: int,
    *,
    selector: str = PS_DEFAULT_FEATURE,
    minimum: int = 1,
) -> dict[str, Any]:
    """Wait until the FEATURE LIST has rendered, not merely any list item.

    :func:`wait_for_panel_rows` counts ``PARTSTUDIO_FEATURE_ITEM`` (``.os-list-item``),
    which the part list, the tab strip and a loading skeleton also match. Measured live
    2026-09-20, immediately after the recovery page reload that wait reported
    ``waited: True`` after 2736 ms while the row enumeration still found 0 custom
    features, 0 readable tabs and no document-tabs button — a satisfied wait that
    proved nothing about the list the caller was about to enumerate.

    ``selector`` defaults to ``PS_DEFAULT_FEATURE`` (the default-geometry group row and
    the Origin/plane rows), which only the Feature List renders. A caller that is about
    to read CUSTOM-feature rows should pass ``PS_USER_FEATURE`` instead: the condition
    that matters is the one the very next read depends on, and waiting for the default
    rows alone can still precede the custom rows on a page that renders in stages.

    This is deliberately a SEPARATE function rather than a change to
    :func:`wait_for_panel_rows`, whose broader condition the tab-switch callers rely on.
    ``minimum`` is a COUNT, not a name match, so the single row-matching rule
    (:func:`match_user_feature_row_indices`) stays the only one. Failure is reported,
    never raised: the caller still has to read the rows and can report 0 as evidence.
    """
    started = time.monotonic()
    try:
        page.wait_for_function(
            _PANEL_ROW_COUNT_PREDICATE,
            arg={"selector": selector, "minimum": minimum},
            timeout=timeout_ms,
        )
        waited, error = True, ""
    except Exception as exc:  # noqa: BLE001 - a timeout is evidence, not a crash
        waited, error = False, f"{type(exc).__name__}: {exc}"
    return {
        "waited": waited,
        "condition": "feature_list_rendered",
        "selector": selector,
        "minimum": minimum,
        "timeoutMs": timeout_ms,
        "elapsedMs": round((time.monotonic() - started) * 1000),
        **({"error": error} if error else {}),
    }


def wait_for_toolbar_button(
    page: Any,
    selector: str,
    timeout_ms: int,
) -> dict[str, Any]:
    """Wait until one toolbar button matching ``selector`` is visible."""
    started = time.monotonic()
    try:
        page.locator(selector).first.wait_for(state="visible", timeout=timeout_ms)
        waited, error = True, ""
    except Exception as exc:  # noqa: BLE001 - a timeout is evidence, not a crash
        waited, error = False, f"{type(exc).__name__}: {exc}"
    return {
        "waited": waited,
        "condition": "toolbar_button_visible",
        "selector": selector,
        "timeoutMs": timeout_ms,
        "elapsedMs": round((time.monotonic() - started) * 1000),
        **({"error": error} if error else {}),
    }


def wait_for_feature_rows(
    page: Any,
    feature_name: str,
    minimum: int,
    timeout_ms: int,
) -> dict[str, Any]:
    """Wait (bounded, inside the page) until ``minimum`` matching rows exist.

    The predicate counts user-feature rows, so the wait is immune to the two
    false signals a name-only wait produces: a same-named row that was already
    there (it satisfies a "row with this name is visible" wait immediately) and a
    workbench that renders its title before its rows (a read straight after a
    reload can see an empty list). Both were measured live on 2026-09-20.
    """
    started = time.monotonic()
    try:
        page.wait_for_function(
            _ROW_COUNT_PREDICATE,
            arg={
                "selector": PARTSTUDIO_FEATURE_ITEM,
                "text": feature_name,
                "minimum": minimum,
            },
            timeout=timeout_ms,
        )
        waited, error = True, ""
    except Exception as exc:  # noqa: BLE001 - a timeout is evidence, not a crash
        waited, error = False, f"{type(exc).__name__}: {exc}"
    return {
        "waited": waited,
        "condition": "user_feature_row_count",
        "minimum": minimum,
        "timeoutMs": timeout_ms,
        "elapsedMs": round((time.monotonic() - started) * 1000),
        **({"error": error} if error else {}),
    }


def verify_insert_committed(
    page: Any,
    feature_name: str,
    *,
    minimum: int = 1,
    appeared: bool = False,
    timeout_ms: int = PARTSTUDIO_RELOAD_TIMEOUT_MS,
) -> dict[str, Any]:
    """Reload the workbench and require the new feature row to survive it.

    A visible Feature List row is NOT proof that the workspace owns the feature.
    Measured live 2026-09-20 (see
    ``onshape_docs/verification/browser-rest-handoff-2026-09-20.json``): a
    browser-inserted custom feature reported its row, its part and a clean
    regeneration, yet the REST feature list of the same element still returned
    no features minutes later; only a page reload made the row appear there. A
    REST-added feature was visible immediately, which rules out a read-side
    cache: the browser insert is simply not committed to the workspace until the
    page is reloaded.

    One bounded reload is therefore the cheapest reliable commit check, and it
    spends 0 API quota. ``minimum`` is the pre-insert matching-row count plus one,
    so the check asks "is the row this call created there", not "is a row with
    this name visible". ``verified`` says the reload ran; ``committed`` says the
    row survived it. An insert that never appeared, or a reload that failed, is
    reported ``verified: False`` and never as inserted — the recorded defect was
    exactly a false positive in this direction. ``timeout_ms`` is the caller's
    budget, normally the adaptive one from ``partstudio_wait_budget_ms``.
    """
    if not appeared:
        return {
            "verified": False,
            "committed": False,
            "reload": None,
            "survived": None,
            "features": None,
            "listed": False,
            "errored": False,
            "featureRows": [],
            "reason": (
                f"the custom feature {feature_name!r} never appeared in the "
                "Feature List, so there was nothing to confirm"
            ),
        }
    reload_result = reload_page(page)
    survived = None
    if reload_result.get("reloaded"):
        survived = wait_for_feature_rows(
            page, feature_name, minimum, timeout_ms
        )
    verified = bool(reload_result.get("reloaded"))
    # A best-effort read even when the row never came back: the returned lists are
    # evidence for the caller, while the wait above stays the gate.
    features = read_partstudio_features(page)
    state = feature_state(features, feature_name)
    committed = verified and bool((survived or {}).get("waited")) and state["listed"]
    if committed:
        reason = ""
    elif not verified:
        reason = (
            "the page reload needed to confirm the insert did not complete, so "
            "the workspace state is unverified and the insert is not reported "
            "as applied"
        )
    else:
        reason = (
            f"the feature {feature_name!r} did not survive the confirming page "
            "reload: the workspace did not keep it, so the insert was not "
            "committed"
        )
    return {
        "verified": verified,
        "committed": committed,
        "reload": reload_result,
        "survived": survived,
        "features": features,
        "listed": state["listed"],
        "errored": state["errored"],
        "featureRows": state["rows"],
        "reason": reason,
    }


def insert_custom_feature(
    page: Any,
    feature_name: str,
    part_studio_tab: str | None = None,
) -> dict[str, Any]:
    """Apply a custom FeatureScript feature into a Part Studio (0 API quota).

    The Part Studio must MANUALLY apply the feature: clicking the toolbar button
    whose tooltip is 此工作区中的自定义特征 opens a dropdown of the workspace's
    custom features; clicking the feature applies it and opens its parameter
    dialog; clicking the checkmark (button-ok) accepts and computes the model.
    The 添加自定义特征 picker alone only inserts a not-computed row.

    ``inserted`` means the workspace kept the feature, not that a click landed:
    the pre-click matching-row count is read first, both waits require that count
    to grow, and after the row and the part appear the page is reloaded once and
    the count must survive that reload (see ``verify_insert_committed`` for the
    measured reason).
    """
    if part_studio_tab:
        # Same switch the tool ``browser_activate_tab`` exposes, so both paths share
        # one implementation. The hard gate stays what it always was: the
        # Feature-List title has to become visible, and the row wait is recorded as
        # evidence. A switched-to Part Studio renders in stages: the title appears
        # before its rows, and the toolbar later still. Measured live 2026-09-20,
        # switching from a Feature Studio produced both a "workspace-custom-features
        # button not found" click and a baseline read of 0 rows on a Part Studio
        # holding 8 custom features — the second one silently degrades ``minimum`` to
        # 1 and re-opens the false-positive the count check exists to close. Wait for
        # the rows and the toolbar button before either is used.
        activation = activate_tab(page, name=part_studio_tab, content="partstudio")
        content_ready = activation.get("contentReady", {})
        panel_ready = content_ready.get("rows")
        if not activation.get("activated") or not content_ready.get("headerVisible"):
            reason = (
                f"part studio tab {part_studio_tab!r} not found"
                if activation.get("matchCount") == 0
                else f"part studio tab did not become ready: {activation.get('reason', '')}"
            )
            return {
                "inserted": False,
                "reason": reason,
                "panelReady": panel_ready,
                "activation": activation,
            }
        toolbar_ready = wait_for_toolbar_button(
            page, PS_WORKSPACE_CUSTOM_FEATURE_BTN, PARTSTUDIO_TOOLBAR_TIMEOUT_MS
        )
    else:
        panel_ready = None
        toolbar_ready = None

    # 1. Click the toolbar button titled 此工作区中的自定义特征.
    #    Baseline BEFORE any click: a same-named row that is already in the Part
    #    Studio must not be mistaken for the one this call creates, so both waits
    #    below require the matching row count to grow past this number (measured
    #    live 2026-09-20: two `Spiral ridge` rows already existed and satisfied a
    #    name-only regeneration wait in 12 ms).
    baseline_read = read_partstudio_features(page)
    baseline = len(feature_state(baseline_read, feature_name)["rows"])
    minimum = baseline + 1
    # Both waits scale with the element's recompute load: a fixed budget gets
    # thinner as the document grows, and it fails by calling a committed feature
    # missing (measured live 2026-09-20, see PARTSTUDIO_RELOAD_WAIT).
    custom_features = count_custom_features(baseline_read)
    regenerate_budget = partstudio_wait_budget_ms(
        PARTSTUDIO_REGENERATE_WAIT, custom_features
    )
    survival_budget = partstudio_wait_budget_ms(PARTSTUDIO_RELOAD_WAIT, custom_features)
    clicked = page.evaluate(
        """
        () => {
          const btn = Array.from(document.querySelectorAll('.tool')).find(
            el => (el.getAttribute('title') || el.getAttribute('data-bs-original-title') || '') === '此工作区中的自定义特征'
          );
          if (!btn) return {clicked: false, reason: 'workspace-custom-features button not found'};
          btn.click();
          return {clicked: true};
        }
        """
    )
    if not clicked.get("clicked"):
        return {**clicked, "inserted": False}
    opened = interaction.wait_for_condition(
        page,
        condition="visible",
        selector=CUSTOM_FEATURE_MENU_ITEM,
        timeout_ms=CUSTOM_FEATURE_MENU_TIMEOUT_MS,
    )
    if not opened.get("waited"):
        return {
            "inserted": False,
            "reason": "custom-feature dropdown did not open",
            "menu": opened,
        }

    # 2. Click the specific feature ITEM inside the dropdown (the dropdown may
    #    hold several workspace features; clicking the container hits whichever
    #    item sits at its centre, so scope the text match to the item rows).
    #    Match the row's NAME element, not its innerText: a workspace row also
    #    renders a two-letter Feature Studio badge, so the row text is
    #    "Bf\nBounded fillet" and exact text equality never holds. Measured live
    #    2026-09-19; see onshape_docs/verification/capability-live-run-2026-09-19.md.
    try:
        items = page.locator(CUSTOM_FEATURE_MENU_ITEM)
        rows = []
        available = []
        for index in range(items.count()):
            item = items.nth(index)
            if not item.is_visible():
                continue
            label = feature_label(item)
            available.append(label)
            if label == feature_name:
                rows.append(item)
        if len(rows) != 1:
            return {
                "inserted": False,
                "reason": (
                    f"feature {feature_name!r} must match exactly one workspace "
                    "dropdown item"
                ),
                "available": available,
            }
        rows[0].click()
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {"inserted": False, "reason": f"feature dropdown click failed: {exc}"}
    dialog = interaction.wait_for_condition(
        page,
        condition="visible",
        selector=FEATURE_DIALOG_OK,
        timeout_ms=FEATURE_DIALOG_TIMEOUT_MS,
    )

    # 3. Accept the parameter dialog (checkmark) to finalize and compute.
    accepted = page.evaluate(
        """
        () => {
          const ok = document.querySelector('%s');
          if (!ok) return {clicked: false, reason: 'accept button not found'};
          ok.click();
          return {clicked: true};
        }
        """ % FEATURE_DIALOG_OK
    )
    # Regeneration is asynchronous: wait for the row COUNT to pass the baseline
    # instead of sleeping a fixed 15s, and instead of waiting for one row whose
    # name may already be on screen.
    regenerated = wait_for_feature_rows(
        page, feature_name, minimum, regenerate_budget
    )

    features = read_partstudio_features(page)
    state = feature_state(features, feature_name)
    accepted_ok = bool(accepted.get("clicked"))

    # A row in the workbench is not a workspace commit (verify_insert_committed):
    # reload once and require the row to survive, then report that read.
    commit = verify_insert_committed(
        page,
        feature_name,
        minimum=minimum,
        appeared=accepted_ok and state["listed"],
        timeout_ms=survival_budget,
    )
    if isinstance(commit.get("features"), dict):
        features = commit["features"]
        state = feature_state(features, feature_name)

    result = {
        "inserted": accepted_ok and bool(commit["committed"]),
        "accepted": accepted,
        "listed": state["listed"],
        "errored": state["errored"],
        "featureRows": state["rows"],
        "baselineRows": baseline,
        "commit": {key: value for key, value in commit.items() if key != "features"},
        "waits": {
            "menu": opened,
            "dialog": dialog,
            "regeneration": regenerated,
            "commitSurvival": commit.get("survived"),
        },
        "panelReady": panel_ready,
        "toolbarReady": toolbar_ready,
        "budgets": {
            "customFeaturesRead": custom_features,
            "regenerationMs": regenerate_budget,
            "commitSurvivalMs": survival_budget,
        },
        "features": features,
        "pageUrl": page.url,
    }
    if state["errored"]:
        # Reported, never retried: an error row may still be regenerating, and a
        # second accept click would add a second feature instead of fixing this
        # one. semantic.build_part turns this into an explicit non-acceptance.
        result["reason"] = (
            "the Feature List row for the feature reports an unresolved error "
            "(not computed); re-read the Part Studio before assuming failure"
        )
    elif not accepted_ok:
        result["reason"] = (
            "the parameter dialog's accept click did not land, so no feature "
            "was created"
        )
    elif not commit["committed"]:
        result["reason"] = str(commit.get("reason") or "")
    return result


def create_document_version(page: Any, name: str = "") -> dict[str, Any]:
    """Create a document version so custom features become insertable.

    The Feature Studio must be committed and the insert dialog shows a
    "创建一个版本" prompt until a version exists. This clicks that prompt,
    unchecks the publish-custom-features checkbox (publishing has extra
    requirements we do not need for in-document insertion), optionally fills
    the version name, and clicks 创建. Returns the new version label.
    """
    info = read_insert_dialog(page)
    if info.get("present") and not info.get("promptSaveVersion"):
        return {"created": False, "reason": "no version prompt; a version may already exist", "dialog": info}

    # Click the version-create prompt (opens .version-or-workspace-dialog).
    clicked = page.evaluate(
        """
        () => {
          const prompt = document.querySelector('.select-item-prompt-save-version');
          if (!prompt) return {clicked: false, reason: 'no version prompt'};
          (prompt.querySelector('a') || prompt).click();
          return {clicked: true};
        }
        """
    )
    if not clicked.get("clicked"):
        return {**clicked, "created": False}

    page.wait_for_timeout(4000)

    # Uncheck publish (extra requirements) and fill the optional name.
    page.evaluate(
        """
        (name) => {
          const modal = document.querySelector('.version-or-workspace-dialog');
          if (!modal) return {ok: false};
          const cb = modal.querySelector('.publish-custom-features-checkbox');
          if (cb && cb.checked) cb.click();
          if (name) {
            const input = modal.querySelector('input.form-control');
            if (input) {
              const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
              setter.call(input, name);
              input.dispatchEvent(new Event('input', {bubbles: true}));
            }
          }
          return {ok: true};
        }
        """,
        name,
    )
    page.wait_for_timeout(1000)

    # Click the plain 创建 button (its label is 创建 and发布 when publish is checked).
    clicked_create = page.evaluate(
        """
        () => {
          const modal = document.querySelector('.version-or-workspace-dialog');
          if (!modal) return {clicked: false, reason: 'no version modal'};
          const btns = Array.from(modal.querySelectorAll('button'));
          const btn = btns.find(b => (b.textContent || '').trim() === '创建');
          if (!btn) return {clicked: false, reason: 'no 创建 button', buttons: btns.map(b => (b.textContent || '').trim())};
          btn.click();
          return {clicked: true};
        }
        """
    )
    if not clicked_create.get("clicked"):
        return {**clicked_create, "created": False}

    page.wait_for_timeout(15000)

    version_label = page.evaluate(
        """
        () => {
          const el = document.querySelector('.select-item-dialog-document-version-name');
          const modal = document.querySelector('.version-or-workspace-dialog');
          return { version: el ? (el.innerText || el.textContent || '').trim() : '', modalOpen: !!modal };
        }
        """
    )
    return {"created": not version_label.get("modalOpen"), **version_label}


def timeout_dialog_state(page: Any) -> dict[str, Any]:
    """Report whether the Onshape session-timeout dialog is present."""
    return page.evaluate(
        """
        () => {
          const link = document.querySelector('.alert-link.osx-message-bubble-link');
          const dialog = document.querySelector('.osx-message');
          return {
            present: !!link,
            linkText: link ? (link.innerText || link.textContent || '').trim() : '',
            message: dialog ? (dialog.innerText || dialog.textContent || '').trim().slice(0, 200) : '',
          };
        }
        """
    )


def reconnect_if_needed(page: Any) -> dict[str, Any]:
    """Click the '重新连接' link if the Onshape timeout dialog is showing.

    Reconnecting is a session-level navigation (no cloud data is created or
    changed). Returns before/after dialog state plus the resulting URL.
    """
    before = timeout_dialog_state(page)
    if not before.get("present"):
        return {"reconnected": False, "reason": "no timeout dialog", "state": before, "pageUrl": page.url}
    try:
        page.locator(TIMEOUT_RECONNECT_LINK).first.click()
        page.wait_for_timeout(5000)
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {
            "reconnected": False,
            "error": f"{type(exc).__name__}: {exc}",
            "state": before,
            "pageUrl": page.url,
        }
    after = timeout_dialog_state(page)
    return {
        "reconnected": not after.get("present"),
        "state": before,
        "after": after,
        "pageUrl": page.url,
    }
