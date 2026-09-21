"""Zero-quota browser actions for the FeatureScript editor.

These operate on the live Onshape page through Playwright. They never call the
Onshape REST API: reading/writing the Ace editor and clicking the Commit button
all happen in the browser UI, so deploying a FeatureScript script this way
spends 0 API calls.

All functions take a Playwright sync `page` object obtained from
``BrowserSession.start()``.
"""

from __future__ import annotations

import collections
import re
import time
from typing import Any

from onshape_browser_mode import diagnostics, interaction
from onshape_browser_mode.selectors import (
    ACE_EDITOR,
    CONTEXT_MENU_LAYER,
    CUSTOM_FEATURE_MENU_ITEM,
    CUSTOM_FEATURE_MENU_LABEL,
    DOCUMENT_TABS_BUTTON,
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
    PS_FEATURE_DIALOG,
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

#: Context-menu and delete bounds for the Part Studio feature list. The menu is the
#: shared jQuery context menu the tab strips already use, so it opens as fast as a
#: tab menu; the removal wait is generous because deleting a row regenerates the
#: whole feature list.
CONTEXT_MENU_TIMEOUT_MS = 5_000
FEATURE_DELETE_TIMEOUT_MS = 30_000
FEATURE_DELETE_POLL_MS = 500

#: Bounded ladder of the context-menu labels a USER feature row can show for
#: deletion. The item is clicked only when exactly one visible label matches, and
#: every visible label is returned either way, so a differently-worded menu is
#: diagnosed from evidence instead of from a guessed click.
PS_FEATURE_DELETE_MENU_TEXTS = ("删除", "删除特征", "删除…", "Delete", "Delete feature")

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

#: How long the document shell itself may take to render after a reload. A reload
#: is the only zero-quota proof that a browser-inserted feature reached the
#: workspace, but the page it lands on is not instantly usable: the tab strip and
#: the Feature List arrive after the app boots. Measured live 2026-09-21, a reload
#: fired straight after a parameter accept left BOTH unrendered for more than 30 s
#: -- the survival wait then counted zero user rows for its whole budget and
#: reported a committed feature as not inserted -- while an idle reload of the same
#: page rendered its tab strip within ~3 s. A boot is not a model recompute, so it
#: gets its own gate instead of eating the row budget; the fast path pays nothing,
#: because the predicate is already true on a rendered page.
DOCUMENT_READY_TIMEOUT_MS = 45_000

#: In-page readiness predicate for the document shell: the tab-strip tools button
#: is absent while the document is still loading and present once it has rendered
#: (measured live 2026-09-21, in both directions).
_DOCUMENT_READY_PREDICATE = """
({selector}) => !!document.querySelector(selector)
"""

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
#: ``minimum`` is therefore the pre-insert baseline plus one. An EMPTY ``text``
#: drops the name filter and counts every user row; the post-reload commit wait
#: uses that mode, because a feature with a ``"Feature Name Template"`` displays
#: its template instead of its Feature Type Name and so can never satisfy a name
#: filter (measured live 2026-09-21: a ``Thin Variable`` row read
#: ``TV #gf_probe = 42 mm``).
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
#:
#: The Feature List is a VIRTUALISED scroller, so one pass sees only the rows the
#: pane currently renders. Measured live 2026-09-21 on a 25-row thin chain: the
#: list header read ``特征 (29)`` while ``querySelectorAll`` returned exactly the
#: first 18 rows, and because ``browser_read_feature_parameters``,
#: ``browser_delete_feature`` and the insert commit gate all resolve rows through
#: THIS enumeration, a row near the bottom of the tree could be neither read nor
#: deleted -- and a reload that re-rendered the top looked like rows disappearing.
#: The collector therefore also walks the row list's own scroll container in
#: bounded steps and unions what it sees, restoring the original scroll position
#: afterwards. A pass that already saw everything (the common case, and what every
#: stub-DOM test exercises) returns byte-for-byte the old answer: the node count
#: plus the names in document order. Only a pass that DISCOVERED more rows switches
#: to the union, where ``count`` is the number of distinct rows seen and
#: ``scrolled`` is reported so a caller can say which read it got.
_USER_FEATURE_ROWS_JS = """
async ({selector}) => {
  const text = (el) => (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 100);
  const nodes = () => Array.from(document.querySelectorAll(selector)).filter(
    el => String(el.className || '').includes('ns-user-feature')
  );
  const first = nodes();
  const firstNames = first.map(text);
  let container = null;
  let walk = first.length ? first[0].parentElement : null;
  while (walk) {
    if (walk.scrollHeight - walk.clientHeight > 8) { container = walk; break; }
    walk = walk.parentElement;
  }
  if (!container) return { count: first.length, names: firstNames, scrolled: false };
  const step = Math.max(40, Math.floor(container.clientHeight * 0.8));
  const limit = container.scrollHeight + step;
  const origin = container.scrollTop;
  const order = firstNames.slice();
  const seen = new Set(order);
  let discovered = 0;
  try {
    container.scrollTop = 0;
    await new Promise(resolve => setTimeout(resolve, 120));
    for (let top = 0; top <= limit; top += step) {
      container.scrollTop = top;
      await new Promise(resolve => setTimeout(resolve, 120));
      for (const name of nodes().map(text)) {
        if (!seen.has(name)) { seen.add(name); order.push(name); discovered += 1; }
      }
      if (top > 0 && container.scrollTop + container.clientHeight >= container.scrollHeight - 1) break;
    }
  } finally {
    container.scrollTop = origin;
  }
  if (discovered === 0) return { count: first.length, names: firstNames, scrolled: true };
  return { count: order.length, names: order, scrolled: true };
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

    # 1. Right-click the tab and pick 重命名. The tab is resolved by exact name
    # through the tab strip, so a name that only PREFIXES another tab's name is a
    # refusal rather than a rename of the wrong tab (see resolve_exact_tab).
    try:
        resolved = resolve_exact_tab(page, name)
        if resolved["matchCount"] != 1:
            return {
                "renamed": False,
                "reason": (
                    f"tab {name!r} must match exactly one visible tab name (exact): "
                    f"matchCount={resolved['matchCount']}, "
                    f"containingName={resolved['contains']}, tabs={resolved['names']}"
                ),
                "pageUrl": page.url,
            }
        if not resolved["id"]:
            return {
                "renamed": False,
                "reason": f"the matched tab {name!r} carries no data-id",
                "pageUrl": page.url,
            }
        tab = page.locator(f'{TAB_BAR_TAB}[data-id="{resolved["id"]}"]')
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


def resolve_exact_tab(page: Any, name: str) -> dict[str, Any]:
    """Resolve one visible tab by EXACT name; never by a substring.

    A substring filter plus ``.first`` can never report ambiguity: ``.first``
    narrows the locator to at most one element, so a following ``count() != 1``
    check can only ever see 0 or 1 and a colliding name is silently accepted.
    Measured live 2026-09-21: a STEP export asked for ``GF Thin Plate`` while
    ``GF Thin Plate (old, 14 rows)`` also existed; the substring click hit the
    other tab and the run failed later with an unrelated URL-mismatch error. The
    tab-strip listing is the authority and the caller clicks the returned id.

    Returns the single match's id (empty when the name is absent or ambiguous),
    the exact match count, every visible name, and the substring candidates so a
    refusal can name what it saw.
    """
    tabs = list_document_tabs(page).get("tabs", [])
    names = [tab.get("name", "") for tab in tabs]
    matches = [tab for tab in tabs if tab.get("name") == name]
    return {
        "id": matches[0].get("id", "") if len(matches) == 1 else "",
        "name": matches[0].get("name", "") if len(matches) == 1 else "",
        "matchCount": len(matches),
        "names": names,
        "contains": [candidate for candidate in names if name and name in candidate],
    }


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


def wait_for_feature_row_removed(
    page: Any,
    feature_name: str,
    timeout_ms: int = FEATURE_DELETE_TIMEOUT_MS,
    selector: str = "",
    name_count_below: int | None = None,
) -> dict[str, Any]:
    """Wait until the named USER feature row leaves the visible feature list.

    The verdict is the NAME, not a position: deleting a row re-numbers every row
    below it, which is the same ``ng-repeat`` hazard the tab-strip removal wait
    documents. Timeout is returned as data, never raised.

    ``name_count_below`` switches the verdict from "the name is gone" to "fewer than
    this many rows carry the name". That is the only correct verdict when the name is
    SHARED: two identical rows are a real state (an interrupted run and its resume can
    both land the same insert, measured live 2026-09-21 with two identical
    ``TV #gf_lock = ...`` rows), and deleting one of them cannot make the name
    disappear. Waiting for absence there would burn the whole timeout and then report a
    correct delete as a failure.
    """
    from onshape_browser_mode.selectors import PS_USER_FEATURE

    wanted = str(feature_name or "")
    counted = name_count_below is not None
    condition = "user_feature_row_count_below" if counted else "user_feature_row_absent"
    started = time.monotonic()
    last: list[str] = []
    while True:
        enumerated = enumerate_user_feature_rows(page, selector or PS_USER_FEATURE)
        last = [str(name) for name in enumerated.get("names", [])]
        matches = sum(1 for name in last if name == wanted)
        done = bool(wanted) and (
            matches < int(name_count_below) if counted else wanted not in last
        )
        if done:
            return {
                "waited": True,
                "condition": condition,
                "featureName": wanted,
                "elapsedMs": int((time.monotonic() - started) * 1000),
                "rowCount": enumerated.get("count"),
                "nameCount": matches,
            }
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if elapsed_ms >= timeout_ms:
            return {
                "waited": False,
                "condition": condition,
                "featureName": wanted,
                "elapsedMs": elapsed_ms,
                "rowCount": enumerated.get("count"),
                "nameCount": matches,
                "nameCountBelow": name_count_below,
                "rows": last,
                "reason": (
                    f"{matches} row(s) named {wanted!r} are still listed after "
                    f"{timeout_ms} ms"
                    + (f" (the wait required fewer than {name_count_below})" if counted else "")
                ),
            }
        page.wait_for_timeout(FEATURE_DELETE_POLL_MS)


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


#: The Feature List header that carries the count for the WHOLE list, not the
#: rendered window: `特征 (27)` in the Chinese UI, `Features (27)` in the English
#: one. The list is VIRTUALISED (measured live 2026-09-21: one read of a 23-row
#: element saw only 18 rows, and two consecutive reads of the same page differed
#: in membership), so this header count is the cheapest full-list answer. An
#: unrecognised shape must yield ``None`` rather than a guess: a different
#: section's header (``零件数 (3)``) is not a feature count.
_PS_HEADER_COUNT = re.compile(r"^\s*(?:特征|Features?)\s*\(\s*(\d+)\s*\)\s*$")

#: The header count includes the four default planes (``PS_DEFAULT_FEATURE``:
#: Origin/Top/Front/Right) in addition to the user features. Measured live
#: 2026-09-21: ``特征 (27)`` on an element holding 23 user features, and
#: ``特征 (15)`` on one whose read listed 11 named rows -- 11 + 4. The row items
#: this reader returns are the named user-feature rows, so a COMPLETE read has
#: exactly this many fewer rows than the header.
DEFAULT_FEATURE_COUNT = 4


def parse_feature_header_count(header_text: Any) -> int | None:
    """The whole-list count in a Feature List header, or ``None`` if unreadable.

    ``None`` is the honest answer for a shape this reader does not recognise: the
    caller has to be able to tell "no count was readable" from "the count is
    zero", so a foreign header never has a number invented for it.
    """
    if not isinstance(header_text, str):
        return None
    match = _PS_HEADER_COUNT.match(header_text)
    return int(match.group(1)) if match else None


def read_partstudio_features(page: Any) -> dict[str, Any]:
    """Read the Part Studio feature tree and part list (read-only, 0 quota).

    Returns the feature-list header, each feature item with its user/default
    classification, and the part-list text (e.g. "零件数 (132) base ...").
    A custom feature present in the list means its FeatureScript compiled and
    was instantiated successfully.

    The Feature List is VIRTUALISED, so one pass reads only the rendered window;
    the answer therefore also carries the readiness this read previously lacked:
    ``headerCount`` (the whole-list count parsed from ``headerText``, or ``None``),
    ``rowsComplete`` (``True`` only when the rows read account for that count
    minus the four default planes, else ``None`` when there is no count to prove
    it against) and ``ready`` (the document shell has rendered). ``ready`` is
    read, never waited for: this is a read tool, so it must not spend the
    caller's budget on a boot.
    """
    raw = page.evaluate(
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
            // The document shell is only readable once its tab-strip tools button
            // exists (measured live 2026-09-21, in both directions: absent while
            // booting, present when rendered). Reading it in THIS pass is the
            // zero-wait answer to "has the page rendered at all" -- a read tool
            // must never start waiting for it.
            documentTabsButtonPresent: !!(document.querySelector('%s')),
          };
        }
        """ % DOCUMENT_TABS_BUTTON,
    )
    if not isinstance(raw, dict):
        # A malformed answer stays the caller's evidence rather than crashing the
        # read; a non-dict cannot carry the readiness keys at all.
        return raw
    features = raw.get("features")
    features = features if isinstance(features, list) else []
    header_count = parse_feature_header_count(raw.get("headerText"))
    # Mutate the evaluated answer IN PLACE rather than rebuilding it: the read's
    # fields are the caller's evidence, and ``insert_custom_feature`` reports the
    # very object the page returned (an existing test pins that identity).
    raw["headerCount"] = header_count
    # The header counts the user-feature rows PLUS the four default planes, while
    # ``features`` holds the named user-feature rows, so equality against
    # ``headerCount - 4`` is what proves this pass saw the whole virtualised list.
    # With no readable header there is nothing to prove completeness against, and
    # a guess would be worse than ``None``.
    raw["rowsComplete"] = (
        len(features) == header_count - DEFAULT_FEATURE_COUNT
        if header_count is not None
        else None
    )
    raw["ready"] = bool(raw.get("documentTabsButtonPresent"))
    # The shell flag is an implementation detail of this read: the public answer
    # keeps every existing field and gains only the three documented keys.
    raw.pop("documentTabsButtonPresent", None)
    return raw


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

    The in-page collector (see :data:`_USER_FEATURE_ROWS_JS`) walks the Feature
    List's own scroll container when one pass sees fewer rows than the list holds,
    because that list is virtualised: on a 25-row chain only the first 18 rows were
    in the DOM, and every name-addressed tool -- this function feeds
    ``browser_read_feature_parameters``, ``browser_delete_feature`` and the insert
    commit gate -- was blind to the rest. ``scrolled`` is added to the answer only
    when the collector actually had to scroll, so the ordinary small-list answer
    keeps exactly its old shape.
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
    answer: dict[str, Any] = {"count": count, "names": names}
    if result.get("scrolled"):
        answer["scrolled"] = True
    return answer


#: Bounded scroll-and-match for a VIRTUALISED Feature List. The click layer addresses
#: a row by its index in the RENDERED node list, so a row that is not rendered cannot
#: be clicked at all: measured live 2026-09-21, the page enumeration saw 26 rows while
#: `page.locator('.os-list-item.ns-user-feature')` counted 18, and the staleness check
#: (correctly) refused rather than click the wrong row. This walks the row list's own
#: scroll container until ``occurrence`` rendered rows carry the wanted name and
#: returns the LAST of them -- the index the caller clicks -- so a row the pane has not
#: rendered is still addressable. A name that two rows share is real: an interrupted
#: run and its resume can both land the same insert, and then only the caller knows
#: which occurrence it means (measured live 2026-09-21, two identical
#: `TV #gf_lock = ...` rows). The default ``occurrence`` of 1 therefore keeps the old
#: exact-one-match behaviour for every other caller. The scroll position is left where
#: the row was found (restoring it there would un-render the row again) and is put back
#: only when no such occurrence was found.
_SCROLL_TO_USER_FEATURE_ROW_JS = """
async ({selector, wanted, occurrence}) => {
  const want = Math.max(1, Number(occurrence) || 1);
  const text = (el) => (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' ').slice(0, 100);
  const nodes = () => Array.from(document.querySelectorAll(selector)).filter(
    el => String(el.className || '').includes('ns-user-feature')
  );
  const rendered = () => nodes().map(text);
  const needle = String(wanted || '').trim().toLowerCase();
  const hits = () => rendered().map((name, index) => [name, index]).filter(
    pair => pair[0].toLowerCase().includes(needle)
  );
  const start = nodes();
  let container = null;
  let walk = start.length ? start[0].parentElement : null;
  while (walk) {
    if (walk.scrollHeight - walk.clientHeight > 8) { container = walk; break; }
    walk = walk.parentElement;
  }
  const now = hits();
  if (now.length >= want) {
    const hit = now[want - 1];
    return { found: true, index: hit[1], name: hit[0], matches: now.length, rendered: rendered(), scrolled: false, steps: 0 };
  }
  if (!container) {
    return { found: false, rendered: rendered(), scrolled: false, steps: 0, reason: 'the row list has no scroll container' };
  }
  const step = Math.max(40, Math.floor(container.clientHeight * 0.8));
  const limit = container.scrollHeight + step;
  const origin = container.scrollTop;
  container.scrollTop = 0;
  await new Promise(resolve => setTimeout(resolve, 120));
  let steps = 0;
  let most = now.length;
  for (let top = 0; top <= limit; top += step) {
    container.scrollTop = top;
    await new Promise(resolve => setTimeout(resolve, 120));
    steps += 1;
    const found = hits();
    most = Math.max(most, found.length);
    if (found.length >= want) {
      const hit = found[want - 1];
      return { found: true, index: hit[1], name: hit[0], matches: found.length, rendered: rendered(), scrolled: true, steps: steps };
    }
    if (top > 0 && container.scrollTop + container.clientHeight >= container.scrollHeight - 1) break;
  }
  container.scrollTop = origin;
  return { found: false, rendered: rendered(), scrolled: true, steps: steps, matches: most, reason: 'no scroll position rendered occurrence ' + want + ' of that name (at most ' + most + ' match(es))' };
}
"""


def scroll_to_user_feature_row(
    page: Any, selector: str, feature_name: str, occurrence: int = 1
) -> dict[str, Any]:
    """Scroll the Feature List until ``occurrence`` rendered rows match ``feature_name``.

    Returns the LAST matching row's index in the CURRENT rendered node list (the index
    the click layer uses), plus the rendered names it was chosen from, how many matches
    that scroll position rendered, and whether scrolling was needed. ``occurrence`` is
    1-based, so the default requires exactly one match, which is the behaviour every
    existing caller relies on. A malformed answer is returned as ``found: False``: an
    unreadable page is evidence, not an exception.
    """
    result = page.evaluate(
        _SCROLL_TO_USER_FEATURE_ROW_JS,
        {"selector": selector, "wanted": feature_name, "occurrence": occurrence},
    )
    if not isinstance(result, dict):
        return {"found": False, "rendered": [], "reason": "the row-list scroll probe returned no map"}
    names = result.get("rendered")
    return {
        "found": bool(result.get("found")),
        "index": result.get("index"),
        "name": result.get("name"),
        "matches": result.get("matches"),
        "occurrence": occurrence,
        "rendered": [str(name) for name in names] if isinstance(names, list) else [],
        "scrolled": bool(result.get("scrolled")),
        "steps": result.get("steps"),
        "reason": result.get("reason", ""),
    }


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
    # The SAME user-row rule the count-based commit gate uses: one rule for "a
    # user-feature row", so the name-matched verdict and the count can never
    # disagree about which rows exist.
    candidates = user_feature_rows(features)
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


def wait_for_document_ready(
    page: Any, timeout_ms: int = DOCUMENT_READY_TIMEOUT_MS
) -> dict[str, Any]:
    """Wait (bounded, inside the page) until the document shell has rendered.

    A reload is the cheapest zero-quota proof that a browser-inserted feature is
    committed, but the reloaded page is not instantly readable: the tab-strip tools
    button (and with it the Feature List) appears only once the app has booted, and
    a read taken before that sees an empty document. Measured live 2026-09-21 on a
    document carrying a live Feature Studio: a reload fired immediately after an
    accept left the shell unrendered for more than 30 s, so the survival wait that
    followed counted 0 rows and reported the insert as not applied, although the
    same page reloaded from idle rendered in ~3 s. Waiting here first is what keeps
    a slow boot out of the row verdict. Never raises: a timeout is evidence.
    """
    started = time.monotonic()
    try:
        page.wait_for_function(
            _DOCUMENT_READY_PREDICATE,
            arg={"selector": DOCUMENT_TABS_BUTTON},
            timeout=timeout_ms,
        )
        waited, error = True, ""
    except Exception as exc:  # noqa: BLE001 - a timeout is evidence, not a crash
        waited, error = False, f"{type(exc).__name__}: {exc}"
    return {
        "waited": waited,
        "condition": "document_tabs_button",
        "selector": DOCUMENT_TABS_BUTTON,
        "timeoutMs": timeout_ms,
        "elapsedMs": round((time.monotonic() - started) * 1000),
        **({"error": error} if error else {}),
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


def user_feature_rows(features: Any) -> list[dict[str, Any]]:
    """Every user-feature row of a read Feature List, whatever it is CALLED.

    A custom feature may declare a ``"Feature Name Template"``, and then its row
    does not display its Feature Type Name at all. Measured live 2026-09-21 on
    the thin ``Thin Variable`` feature, whose template is the native Variable
    feature's own ``###name = #value``: the row read ``TV #gf_probe = 42 mm``, so
    a search for "Thin Variable" can never find the row it is meant to confirm.
    Callers therefore identify the row a call created by the MULTISET difference
    against the pre-insert row names (``created_user_feature_rows``) and gate on a
    row COUNT.
    """
    if not isinstance(features, dict):
        return []
    items = features.get("features")
    if not isinstance(items, list):
        return []
    return [
        {"name": str(item.get("name", "")), "hasError": bool(item.get("hasError"))}
        for item in items
        if isinstance(item, dict) and item.get("isUserFeature")
    ]


def created_user_feature_rows(
    rows: Any, baseline_names: Any
) -> list[dict[str, Any]]:
    """The rows of ``rows`` that EXCEED the pre-click name MULTISET.

    A name-set difference is not enough, and it fails in the one case this check
    exists for. The row a custom feature writes is not unique: two ``Thin Variable``
    rows that define the same variable with the same value render the identical
    text, and a run that was interrupted and resumed can leave exactly that. Measured
    live 2026-09-21: a resume raced a still-running first run, the element held two
    identical ``TV #gf_lock = 37.7 mm 锁定面方孔边长`` rows, and the set difference
    then reported the NEW third row as "not created" because its name was already in
    the baseline -- which made the runner fail that step forever, however often it was
    retried. Counting per name fixes it: the excess over the baseline is the row this
    call created, whether or not a same-named row was there before.

    Rows with no baseline counterpart are always created. The answer keeps the read's
    order so a caller can report the row text.
    """
    # A ``Counter`` is copied WITH its counts; anything else is counted here. Iterating a
    # Counter yields its distinct keys, so treating one as a plain name list would drop
    # every duplicate -- exactly the row this helper exists to find.
    if isinstance(baseline_names, collections.Counter):
        remaining: dict[str, int] = collections.Counter(baseline_names)
    else:
        remaining = collections.Counter(
            str(name) for name in (baseline_names or ())
        )
    created: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        key = str(row.get("name", ""))
        if remaining.get(key, 0) > 0:
            remaining[key] -= 1
            continue
        created.append(row)
    return created


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
    *,
    match_name: bool = True,
) -> dict[str, Any]:
    """Wait (bounded, inside the page) until ``minimum`` matching rows exist.

    The predicate counts user-feature rows, so the wait is immune to the two
    false signals a name-only wait produces: a same-named row that was already
    there (it satisfies a "row with this name is visible" wait immediately) and a
    workbench that renders its title before its rows (a read straight after a
    reload can see an empty list). Both were measured live on 2026-09-20.

    ``match_name=False`` drops the name filter and counts user-feature rows only.
    That is what the post-reload commit check needs, because a feature with a
    ``"Feature Name Template"`` does not display its Feature Type Name at all
    (measured live 2026-09-21: a ``Thin Variable`` row read
    ``TV #gf_probe = 42 mm``), so a name filter can never be satisfied by the very
    row the check exists to confirm. The name filter stays for the pre-accept
    regeneration wait, where the row is the open dialog's own row.
    """
    started = time.monotonic()
    try:
        page.wait_for_function(
            _ROW_COUNT_PREDICATE,
            arg={
                "selector": PARTSTUDIO_FEATURE_ITEM,
                "text": feature_name if match_name else "",
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
        "matchName": match_name,
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
    survival_minimum: int | None = None,
    baseline_names: Any = (),
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

    The post-reload gate counts ROWS, not name matches, and identifies the created
    row as the one whose name was not in ``baseline_names``. A feature carrying a
    ``"Feature Name Template"`` does not display its Feature Type Name, so a
    name-matching gate times out on a row that is really there: measured live
    2026-09-21, a ``Thin Variable`` insert (row ``TV #gf_probe = 42 mm``, no
    error, variable really created) was reported ``inserted: False`` after the
    full 30 s survival budget because the filter looked for "Thin Variable".
    ``survival_minimum`` is the pre-insert USER-ROW count plus one and is what the
    wait and the verdict use; ``minimum`` keeps its name-matched meaning for the
    pre-accept wait the caller runs.

    No row is counted until the reloaded document shell has rendered: a reload
    fired straight after an accept can land on a page whose Feature List has not
    appeared yet (measured live 2026-09-21: >30 s on a document carrying a live
    Feature Studio, while an idle reload of the same page rendered in ~3 s). A
    shell that never renders is reported ``bootReady: False`` with no row verdict,
    so a caller can tell "the row is missing" from "the row could not be counted".
    """
    if not appeared:
        return {
            "verified": False,
            "committed": False,
            "bootReady": None,
            "documentReady": None,
            "reload": None,
            "survived": None,
            "features": None,
            "listed": False,
            "errored": False,
            "createdRows": [],
            "userRows": [],
            "featureRows": [],
            "reason": (
                f"the custom feature {feature_name!r} never appeared in the "
                "Feature List, so there was nothing to confirm"
            ),
        }
    target = minimum if survival_minimum is None else survival_minimum
    baseline = collections.Counter(str(name) for name in baseline_names)
    reload_result = reload_page(page)
    document_ready = None
    survived = None
    if reload_result.get("reloaded"):
        # Wait for the shell before counting rows: a reload fired right after an
        # accept can land on a document that has not rendered yet (see
        # DOCUMENT_READY_TIMEOUT_MS), and a row count taken then reads 0 for a
        # reason that has nothing to do with this feature.
        document_ready = wait_for_document_ready(page)
        if document_ready.get("waited"):
            survived = wait_for_feature_rows(
                page, feature_name, target, timeout_ms, match_name=False
            )
    verified = bool(reload_result.get("reloaded"))
    booted = document_ready is None or bool(document_ready.get("waited"))
    # A best-effort read even when the row never came back: the returned lists are
    # evidence for the caller, while the wait above stays the gate.
    features = read_partstudio_features(page)
    state = feature_state(features, feature_name)
    rows = user_feature_rows(features)
    created = created_user_feature_rows(rows, baseline)
    waited = bool((survived or {}).get("waited"))
    counted = verified and waited and len(rows) >= target
    committed = counted and bool(created)
    if committed:
        reason = ""
    elif not verified:
        reason = (
            "the page reload needed to confirm the insert did not complete, so "
            "the workspace state is unverified and the insert is not reported "
            "as applied"
        )
    elif not booted:
        reason = (
            "the reload needed to confirm the insert landed on a document whose UI "
            f"had not rendered within {document_ready['timeoutMs']} ms, so the "
            "Feature List could never be counted: the row may or may not be "
            "committed, and this call reports neither -- re-read the Part Studio "
            "before retrying"
        )
    elif not waited:
        reason = (
            f"the survival wait for {feature_name!r} never settled within its "
            "budget, so the workspace state is unverified and the insert is not "
            "reported as applied"
        )
    elif len(rows) < target:
        reason = (
            f"the post-reload read found {len(rows)} user row(s) where the survival "
            f"wait required {target}: the Feature List is virtualised and a read taken "
            "right after a reload can see only a partial window, so this call reports "
            "neither success nor failure -- re-read the list before retrying"
        )
    else:
        reason = (
            f"the reloaded Feature List shows {len(rows)} user row(s) and none of them "
            f"is beyond the pre-click baseline of {sum(baseline.values())} row(s), so "
            "this call cannot point at a row it created"
        )
    return {
        "verified": verified,
        "committed": committed,
        "bootReady": booted,
        "documentReady": document_ready,
        # ``listed``/``errored`` describe the row this call created, so a
        # template-named row is reported as listed even though no name matched.
        "listed": bool(created) or state["listed"],
        "errored": state["errored"] or any(row["hasError"] for row in created),
        "createdRows": created,
        "userRows": rows,
        "reload": reload_result,
        "survived": survived,
        "features": features,
        "featureRows": state["rows"],
        "reason": reason,
    }


def dialog_values(page: Any) -> dict[str, str]:
    """Read every named field of the open parameter dialog.

    A parameter's own id is the key: the control carries ``name``/``id``, or the
    wrapping ``[data-parameter-id]`` owner does. Checkboxes read as
    ``String(checked)`` so a boolean round-trips through the same text comparison
    as a number.
    """
    result = page.evaluate(
        """
        () => {
          const dialog = document.querySelector('.feature-dialog');
          if (!dialog) return {};
          const result = {};
          for (const input of dialog.querySelectorAll('input, textarea, select')) {
            const owner = input.closest('[data-parameter-id], [parameter-id]');
            const key = input.getAttribute('name') || input.id ||
              owner?.getAttribute('data-parameter-id') || owner?.getAttribute('parameter-id') ||
              input.getAttribute('aria-label') || '';
            if (key) result[key] = input.type === 'checkbox' ? String(input.checked) : String(input.value || '');
          }
          return result;
        }
        """
    )
    return result if isinstance(result, dict) else {}


#: A parameter id is not an id attribute: Onshape renders the control inside a
#: ``[data-parameter-id]`` owner, so each candidate selector is tried in order and
#: the visible label is the last resort.
_DIALOG_FIELD_SELECTOR = (
    '[data-parameter-id="{key}"] input, [parameter-id="{key}"] input, '
    'input[name="{key}"], textarea[name="{key}"], select[name="{key}"], #{key}'
)

#: Onshape paints a styled checkbox and leaves the real control invisible: the
#: ``<input type="checkbox" class="os-param-checkbox-input">`` that carries the
#: parameter id resolves but is measured NOT VISIBLE, so clicking it waits for
#: visibility and times out (measured live 2026-09-20: 30 s on ``subtract`` of a
#: Thin Extrude dialog, the log showing the input resolved and "element is not
#: visible" on every retry). The visible click target is therefore an ancestor, and
#: which ancestor owns the click behaviour is not fixed across control types, so
#: each candidate is tried until the state actually changes.
_BOOLEAN_CLICK_TARGETS = (
    "xpath=..",
    "xpath=../..",
    "xpath=ancestor::label[1]",
    "xpath=ancestor::*[contains(@class, 'checkbox')][1]",
)

#: Per-candidate budget. A wrong ancestor is a cheap no-op, but four candidates at
#: Playwright's 30 s default would cost two minutes before a refusal could be
#: reported, and a refusal is a normal outcome for a parameter this mechanism
#: cannot set.
_BOOLEAN_CLICK_TIMEOUT_MS = 2500

#: Bounded wait for an Onshape quantity widget to RESOLVE the expressions it was
#: just filled with, and the interval it re-reads the dialog on. A widget resolves
#: ``#variable`` asynchronously, and the accept click races that resolution:
#: measured live 2026-09-21, accepting straight after the fill committed the field's
#: OLD value (the row read ``TV #gf_plate_size = 0 mm``) although the same dialog's
#: live preview showed ``84 mm``. Once it has resolved, the widget echoes the typed
#: expression VERBATIM -- the same build read ``#gf_plate_size = 84 mm`` in the row
#: and ``#gf_pitch * 2`` in the dialog -- so a satisfied wait means the text the
#: accept will commit is exactly the text that was asked for.
EXPRESSION_RESOLVE_WAIT_MS = 20_000
EXPRESSION_RESOLVE_POLL_MS = 1_000


def _boolean_state(locator: Any) -> bool | None:
    """Read a checkbox's state; visibility is not required to read it."""
    try:
        return bool(locator.first.is_checked())
    except Exception:
        return None


def _click_boolean(locator: Any, desired: bool) -> bool:
    """Click until the checkbox holds ``desired``; report whether it got there.

    Every candidate is judged by its RESULT, never by the click returning: a click
    that lands on an ancestor with no click handler raises nothing and changes
    nothing, so the state read back afterwards is the only evidence that a click
    was the right one.
    """
    if _boolean_state(locator) == desired:
        return True
    for selector in (None, *_BOOLEAN_CLICK_TARGETS):
        candidate = locator if selector is None else locator.locator(selector)
        try:
            if candidate.count() == 0 or not candidate.first.is_visible():
                continue
            candidate.first.click(timeout=_BOOLEAN_CLICK_TIMEOUT_MS)
        except Exception:
            continue
        if _boolean_state(locator) == desired:
            return True
    return _boolean_state(locator) == desired


def _commit_field(target: Any) -> bool:
    """Fire the ``change`` event a freshly filled field needs to reach the model.

    ``Locator.fill`` focuses the field, sets the text, and fires ``input``; the
    browser fires ``change`` only when the element loses focus. Onshape's parameter
    directive commits on ``change``, so the LAST field filled in a dialog never
    reached the model. Measured live 2026-09-21 on a 14-row build: every field filled
    before another one was persisted, while the final fill of each dialog was not --
    ``corner_radius`` and ``draft_angle`` read back correctly in the dialog (4 mm and
    45 deg) and were stored as their zero defaults, producing a plate with sharp
    corners and a socket whose 45 deg ramps had no taper at all. Blurring each field
    as it is filled closes the gap instead of relying on whatever field happens to be
    filled next.

    A field cleared with an empty string needs this too, for the same reason.
    """
    try:
        target.blur()
        return True
    except Exception:
        return False


_QUANTITY_RE = re.compile(r"^([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(.*)$")


def quantities_match(actual: Any, expected: Any) -> bool:
    """Whether a dialog readback is the value that was asked for.

    Two shapes have to match, and they are not the same comparison:

    * a literal field reads back exactly the text that was typed;
    * a QUANTITY widget that has evaluated an expression reads back the resolved
      NUMBER, not the expression. Measured live 2026-09-21 on the same dialog: the
      read taken 4 ms after the fill still held the typed `#gf_socket`, while the
      same field read `36.3 mm` 20 s later. Both are the expression having taken
      effect; only the second one is settled.

    Text is compared case-insensitively with whitespace collapsed, and two numbers
    compare equal within a relative 1e-9 so a caller may write `36.30 mm` for a
    widget that renders `36.3 mm`. The unit must match: ignoring it would accept
    `36.3 in` for `36.3 mm`.
    """
    left = " ".join(str(actual).split()).lower()
    right = " ".join(str(expected).split()).lower()
    if left == right:
        return True
    found = _QUANTITY_RE.match(left)
    wanted = _QUANTITY_RE.match(right)
    if not found or not wanted or found.group(2) != wanted.group(2):
        return False
    try:
        a = float(found.group(1))
        b = float(wanted.group(1))
    except (TypeError, ValueError):  # pragma: no cover - the regex already guards this
        return False
    return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))


def wait_for_dialog_fields(
    page: Any,
    desired: dict[str, Any],
    keys: list[str],
    timeout_ms: int = EXPRESSION_RESOLVE_WAIT_MS,
    poll_ms: int = EXPRESSION_RESOLVE_POLL_MS,
    resolved: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wait, bounded, until the dialog reads ``desired`` back for ``keys``.

    This is the accept gate for an expression value. The quantity widget resolves a
    ``#variable`` reference asynchronously, so the read taken straight after a fill
    still shows the field's OLD text and the accept click would then commit that old
    value -- silently, as a wrong number (see ``EXPRESSION_RESOLVE_WAIT_MS`` for the
    measurement). Waiting on the DIALOG's own readback is what makes the wait usable
    for every thin row: a row whose feature has no ``Feature Name Template``
    displays no numbers at all, so the row text cannot serve as the signal, while the
    dialog always can.

    A stated ``resolved`` value is the ONLY accepted signal for that key, and it has to
    be stated for EVERY expression key. The widget shows the typed expression for a
    moment before it parses it, so "the field reads the text I typed" is not evidence
    that the value was taken -- measured live 2026-09-21, the accept that followed such
    a read committed the field's PREVIOUS value, silently. Two live instances of that
    defect: a variable-driven ``Thin Sketch Rectangle`` came out 100 mm x 100 mm with a
    0 mm corner radius (its dialog defaults) while its literal-valued sibling in the
    same document stored 84 mm / 4 mm, and a ``Thin Variable`` row landed as
    ``#gf_plate_size = 0 mm``. Both were accepted by the typed-text rule. Hence an
    expression key the caller states a value for is satisfied ONLY by the value the
    expression must EVALUATE to (``quantities_match``) -- a settled widget renders the
    number, not the text (a correctly stored ``#gf_pitch * 2`` reads back ``84 mm``) --
    and an expression key the caller states NOTHING for can never be confirmed, so the
    wait refuses immediately with ``condition: "unstated_expression"`` instead of
    spending its budget and instead of accepting the text. A literal key keeps the
    exact-text rule. ``resolved`` is keyed by parameter id and is only consulted for the
    given ``keys``.

    Failure is reported, never raised, and the caller decides what an unresolved
    field means: the returned ``after``/``mismatched`` are the same read the fill
    verdict is taken from.
    """
    expectations: dict[str, list[Any]] = {}
    strict_keys: list[str] = []
    unstated: list[str] = []
    for key in keys:
        name = str(key)
        if resolved and key in resolved:
            expectations[name] = [resolved[key]]
            strict_keys.append(name)
        elif "#" in str(desired.get(key, "")):
            # An expression is NEVER confirmed by the text that was typed into it. A
            # variable's Value field settles to the EVALUATED number too: measured live
            # 2026-09-21, a correctly stored `#gf_pitch * 2` reads back `84 mm`, and the
            # insert that accepted while the field still showed the text committed the
            # field's previous value and produced the row `TV #gf_plate_size = 0 mm`.
            # So a caller that states nothing for an expression key cannot confirm it,
            # and this waits for nothing: it refuses immediately and says so.
            expectations[name] = []
            strict_keys.append(name)
            unstated.append(name)
        else:
            expectations[name] = [desired.get(key, "")]
    if unstated:
        return {
            "waited": False,
            "condition": "unstated_expression",
            "keys": [str(key) for key in keys],
            "strictKeys": strict_keys,
            "unstatedExpressionKeys": unstated,
            "resolvedValues": {
                key: resolved[key] for key in expectations if resolved and key in resolved
            },
            "timeoutMs": timeout_ms,
            "pollMs": poll_ms,
            "elapsedMs": 0,
            "after": dialog_values(page),
            "mismatched": unstated,
        }
    started = time.monotonic()
    read: dict[str, Any] = {}
    mismatched: list[str] = []
    while True:
        read = dialog_values(page)
        mismatched = [
            key
            for key, options in expectations.items()
            if not any(quantities_match(read.get(key, ""), option) for option in options)
        ]
        elapsed = round((time.monotonic() - started) * 1000)
        if not mismatched or elapsed >= timeout_ms:
            break
        page.wait_for_timeout(poll_ms)
    return {
        "waited": not mismatched,
        "condition": "dialog_fields_readback",
        "keys": [str(key) for key in keys],
        "strictKeys": strict_keys,
        "unstatedExpressionKeys": [],
        "resolvedValues": {
            key: resolved[key] for key in expectations if resolved and key in resolved
        },
        "timeoutMs": timeout_ms,
        "pollMs": poll_ms,
        "elapsedMs": elapsed,
        "after": read,
        "mismatched": mismatched,
    }


def fill_dialog_fields(
    page: Any,
    parameters: dict[str, Any],
    expect_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fill the open parameter dialog's named fields and read the values back.

    One implementation for both callers, because "which control carries this
    parameter id" must not drift between them:
    ``browser_edit_feature_parameters`` opens this dialog on an existing row, and
    ``browser_insert_custom_feature`` opens it on a row it just added, which is
    what lets a thin feature — a row whose whole content is a few numbers — be
    created correctly in ONE browser transaction instead of insert-then-edit.

    Nothing is accepted here: the caller decides, and ``readbackOk`` plus
    ``missing`` are the evidence it decides on. ``before`` is read before any
    fill so a caller can report what the row held.

    A field holding an Onshape EXPRESSION (``#gf_socket``) is WAITED for before the
    verdict is taken, because the quantity widget shows the typed text for a moment
    before it parses it: the read straight after the fill is stale, and accepting on it
    commits the field's PREVIOUS value as a silently wrong number (measured live
    2026-09-21 -- a variable-driven sketch came out at its 100 mm defaults while its
    literal-valued sibling stored 84 mm). ``expect_values`` maps a parameter id to the
    value the expression must EVALUATE to, which is what a settled widget renders, and
    for a key it states it is the ONLY accepted signal; a key with no stated value is
    satisfied by the typed text, which is the settled state of a field whose stored
    value IS the expression (a variable's Value field). Both the wait and its verdict
    are returned (``expressionWait``, ``resolved``).

    ``mismatched`` names the fields whose ``after`` read does not match the request,
    by the one comparison both callers share (``quantities_match``): exact text for a
    literal, and for an expression the stated ``expect_values`` value (or the typed
    text when none is stated). It is reported rather than judged, because the caller
    decides what a refusal means.
    """
    before = dialog_values(page)
    dialog = page.locator(PS_FEATURE_DIALOG).first
    updated: list[str] = []
    missing: list[str] = []
    committed: list[str] = []
    uncommitted: list[str] = []
    for key, value in parameters.items():
        locator = dialog.locator(_DIALOG_FIELD_SELECTOR.format(key=key))
        if locator.count() == 0:
            container = dialog.locator(".parameter-item, .feature-parameter").filter(
                has_text=str(key)
            )
            locator = container.locator("input, textarea, select") if container.count() else locator
        if locator.count() == 0:
            missing.append(str(key))
            continue
        target = locator.first
        if isinstance(value, bool):
            # A boolean goes through the styled checkbox, which is not the element
            # that carries the parameter id; see _BOOLEAN_CLICK_TARGETS. A click
            # commits by itself, so it needs no blur.
            if not _click_boolean(locator, value):
                missing.append(str(key))
                continue
        else:
            target.fill(str(value))
            if _commit_field(target):
                committed.append(str(key))
            else:
                uncommitted.append(str(key))
        updated.append(str(key))
    after = dialog_values(page)
    desired = {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in parameters.items()
    }
    expression_fields = [
        str(key)
        for key, value in parameters.items()
        if not isinstance(value, bool) and "#" in str(value)
    ]
    resolved_values = {
        str(key): value
        for key, value in (expect_values or {}).items()
        if str(key) in expression_fields
    }
    mismatched = [
        key
        for key, value in desired.items()
        if not quantities_match(after.get(key, ""), value)
    ]
    # 2c. Let the widget RESOLVE what was just filled before anything is judged. The
    #     read above was taken immediately, so for an expression it is the stale one.
    expression_wait = None
    if expression_fields:
        expression_wait = wait_for_dialog_fields(
            page, desired, expression_fields, resolved=resolved_values
        )
        after = expression_wait["after"]
        unsettled = set(expression_wait["mismatched"])
        mismatched = [
            key
            for key in desired
            if key in unsettled or (key not in expression_fields and key in mismatched)
        ]
    return {
        "updated": updated,
        "missing": missing,
        "committed": committed,
        "uncommitted": uncommitted,
        "mismatched": mismatched,
        "before": before,
        "after": after,
        "desired": desired,
        "readbackOk": not mismatched,
        "expressionFields": expression_fields,
        "expressionWait": expression_wait,
        "expectValues": resolved_values,
        "resolved": None if expression_wait is None else not expression_wait["mismatched"],
    }


def insert_custom_feature(
    page: Any,
    feature_name: str,
    part_studio_tab: str | None = None,
    parameters: dict[str, Any] | None = None,
    expect_row: str = "",
    expect_values: dict[str, Any] | None = None,
    verify_commit: bool = True,
) -> dict[str, Any]:
    """Apply a custom FeatureScript feature into a Part Studio (0 API quota).

    The Part Studio must MANUALLY apply the feature: clicking the toolbar button
    whose tooltip is 此工作区中的自定义特征 opens a dropdown of the workspace's
    custom features; clicking the feature applies it and opens its parameter
    dialog; clicking the checkmark (button-ok) accepts and computes the model.
    The 添加自定义特征 picker alone only inserts a not-computed row.

    ``inserted`` means the workspace kept the feature, not that a click landed:
    the pre-click USER-ROW count and names are read first, both waits require that
    count to grow, and after the row and the part appear the page is reloaded once
    and the new row must survive that reload (see ``verify_insert_committed`` for
    the measured reason and for why the check counts rows instead of matching the
    feature's name). The read taken immediately after the accept is reported as
    ``workbenchAppeared`` but deliberately does NOT gate that reload: it can be
    empty mid-re-render even when the insert really landed.

    ``parameters`` fills the dialog's named fields before it is accepted, so the
    row is created with its numbers instead of with the dialog's defaults. A
    feature whose whole content is a few numbers (a thin, native-shaped row) would
    otherwise need two browser transactions per row -- insert, then edit -- and the
    default it was briefly created with would be an extra state to reason about. A
    fill that cannot find every field, whose field cannot be committed, or whose
    readback does not match, is reported as ``inserted: False`` with the fill
    evidence and the dialog is NOT accepted.

    A value containing ``#`` is an Onshape EXPRESSION, and it RESOLVES
    ASYNCHRONOUSLY: the read taken straight after the fill still shows the field's
    old text, and accepting then commits that old value as a silently wrong number.
    Measured live 2026-09-21 on ``#gf_pitch * 2``: the accept landed and the model
    stored ``0 mm`` after the dialog's own preview had shown ``84 mm``. So an
    expression field is waited for (see ``wait_for_dialog_fields``), and the wait is
    satisfied by the typed text or, when the caller states it, by the value the
    expression must EVALUATE to: a settled widget renders the resolved number, so
    ``expect_values`` (parameter id -> value) is what lets a dimension-driven step be
    confirmed at all -- measured live 2026-09-21, the same field read the typed
    ``#gf_socket`` 4 ms after the fill and ``36.3 mm`` 20 s later. A field that never
    reaches either readback is a refusal, unless ``expect_row`` covers it: that is the
    ROW text the model writes, produced by the feature's ``Feature Name Template``
    from the computed parameter, which is the strongest evidence for a feature whose
    row states numbers.

    Careful with what a refusal means, because it was measured (2026-09-21): the
    dropdown click has ALREADY added the row, and a row with an unaccepted dialog
    keeps its dialog DEFAULTS and survives a reload. So a refusal leaves a real,
    default-valued row in the tree that satisfies ``inserted`` on a later call and
    contributes geometry; it must be deleted, not ignored.

    ``verify_commit=False`` skips that confirming reload. It exists because the
    two-wait confirmation (regeneration, then a reload plus its survival wait) can
    exceed the ~60-70 s transport budget of one MCP call on a step whose geometry is
    expensive to recompute: measured live 2026-09-21, a 45-degree-draft subtract
    extrude of 2.15 mm at z 5.0 timed out twice at a clean tree and created NO row,
    while four thinner instances of the same feature in the same element completed.
    A timed-out call returns no verdict at all, so the caller is left unable to tell
    an unsent step from a landed one. With the reload skipped the call returns as
    soon as the accept landed, ``inserted`` is ``None`` (unknown, never a false
    success) and ``applyState`` is ``pending_verification``; the caller then proves
    the row with ``browser_read_feature_parameters`` or a feature-list read before
    the next step. Use it only for a step whose confirmation is known to outlive the
    transport, never to avoid a refusal.

    The SHORT path also skips the post-accept regeneration wait, and it has to: that
    wait's budget scales with the element (30 s plus 2 s per custom feature, see
    ``partstudio_wait_budget_ms``), so on an element of ~20 rows it is already longer
    than one call's transport budget -- measured live 2026-09-21, three short-path
    attempts at one heavy cut on a 20-row tree returned NO verdict at all, because the
    call never got as far as returning from the accept it had already clicked. What
    the short path guarantees is therefore "the accept click was made", not "the model
    finished recomputing", and the caller's own row read is what decides.
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
                "applyState": "not_inserted",
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
    #
    #    The waits gate on the WHOLE user-row count, not on a name match, because a
    #    feature with a "Feature Name Template" does not display its Feature Type
    #    Name: a `Thin Variable` row reads `TV #gf_probe = 42 mm`, so a wait for
    #    "Thin Variable" could never be satisfied by the row it was waiting for
    #    (measured live 2026-09-21; see verify_insert_committed). Counting rows and
    #    subtracting the pre-insert names is the same check without that blind spot.
    baseline_read = read_partstudio_features(page)
    baseline_rows = user_feature_rows(baseline_read)
    baseline_names = [row["name"] for row in baseline_rows]
    baseline = len(feature_state(baseline_read, feature_name)["rows"])
    minimum = baseline + 1
    survival_minimum = len(baseline_rows) + 1
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
            "applyState": "not_inserted",
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
                "applyState": "not_inserted",
                "reason": (
                    f"feature {feature_name!r} must match exactly one workspace "
                    "dropdown item"
                ),
                "available": available,
            }
        rows[0].click()
    except Exception as exc:  # noqa: BLE001 - surface as structured result
        return {
            "inserted": False,
            "applyState": "not_inserted",
            "reason": f"feature dropdown click failed: {exc}",
        }
    dialog = interaction.wait_for_condition(
        page,
        condition="visible",
        selector=FEATURE_DIALOG_OK,
        timeout_ms=FEATURE_DIALOG_TIMEOUT_MS,
    )

    # 2b. Fill the dialog BEFORE accepting it, when the caller named values. The
    #     dialog is already visible, so the fill runs against the row this call
    #     just created. A fill that did not land exactly is a refusal, not a
    #     silent default-valued row.
    filled = None
    expression_fields: list[str] = []
    expression_wait = None
    if parameters:
        # The fill WAITS for every expression field before the verdict is taken: the
        # read straight after the fill is the stale one that used to be accepted and
        # committed as a wrong number. Both the wait and its verdict live in the one
        # shared implementation, so the edit path gets the same gate.
        filled = fill_dialog_fields(page, parameters, expect_values=expect_values)
        expression_fields = filled["expressionFields"]
        expression_wait = filled["expressionWait"]
        unresolved = [
            key for key in filled["mismatched"] if key not in expression_fields
        ]
        unconfirmed = [
            key for key in filled["mismatched"] if key in expression_fields
        ]
        if filled["missing"] or filled["uncommitted"] or unresolved or (
            unconfirmed and not expect_row
        ):
            if unconfirmed and not expect_row:
                reason = (
                    f"parameter(s) {', '.join(unconfirmed)} hold an Onshape "
                    "expression whose resolved value the dialog never showed, so the "
                    "value could not be confirmed before the accept; pass "
                    "expect_values with the value each expression must EVALUATE to "
                    "(the settled widget renders the number, not the expression), or "
                    "expect_row with the row text the model should write"
                )
            else:
                reason = (
                    "the parameter dialog was not filled exactly; the dialog was left "
                    "unaccepted"
                )
            return {
                "inserted": False,
                "applyState": "not_inserted",
                "reason": reason,
                "parameters": filled,
                "expressionFields": expression_fields,
                "available": available,
                "dialog": dialog,
                "wait": expression_wait,
                "panelReady": panel_ready,
                "toolbarReady": toolbar_ready,
            }

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
    #
    # On the SHORT path this wait is SKIPPED, because it is what breaks the short
    # path's own promise. The budget scales with the element (30 s plus 2 s per
    # custom feature), so on an element with ~20 rows it is already ~70 s -- longer
    # than the ~60-70 s a single MCP call gets, which is exactly the case the caller
    # asked to avoid (measured live 2026-09-21: three `verify_commit=False` attempts
    # at one heavy cut on a 20-row element returned no verdict at all, and the call
    # never reached the accept-click it was supposed to return from). The caller of
    # the short path has explicitly taken over confirmation, so the wait is not a
    # gate it needs; the accept click is the last mandatory step, and everything
    # reported below is evidence the caller is told not to trust as a verdict.
    if verify_commit:
        regenerated = wait_for_feature_rows(
            page, feature_name, survival_minimum, regenerate_budget, match_name=False
        )
    else:
        regenerated = {
            "skipped": True,
            "condition": "user_feature_row_count",
            "minimum": survival_minimum,
            "budgetMs": regenerate_budget,
            "reason": (
                "the regeneration wait was skipped on the short path "
                "(verify_commit=false): its adaptive budget can exceed one call's "
                "transport budget and the caller has taken over confirmation"
            ),
        }

    features = read_partstudio_features(page)
    state = feature_state(features, feature_name)
    created = created_user_feature_rows(user_feature_rows(features), baseline_names)
    accepted_ok = bool(accepted.get("clicked"))
    # The read taken straight after the accept is NOT authoritative, and it does not
    # gate the confirming reload. Measured live 2026-09-21: it returned ZERO user rows
    # 25 ms after an accepted insert that then survived the reload, because the accept
    # starts a re-render that clears the list before re-rendering it. It is reported
    # as `workbenchAppeared` evidence; the reload is what decides.
    workbench_appeared = len(user_feature_rows(features)) >= survival_minimum

    # A row in the workbench is not a workspace commit (verify_insert_committed):
    # reload once and require the row to survive, then report that read.
    if verify_commit:
        commit = verify_insert_committed(
            page,
            feature_name,
            minimum=minimum,
            survival_minimum=survival_minimum,
            baseline_names=baseline_names,
            appeared=accepted_ok,
            timeout_ms=survival_budget,
        )
    else:
        # The caller chose the short path because this element's confirmation is
        # known to outlive the transport (see the docstring). This is reported as
        # evidence, never as a passed check: `committed` stays None so nothing below
        # can read it as a success.
        commit = {
            "verified": False,
            "committed": None,
            "skipped": True,
            "reason": (
                "the confirming reload was skipped (verify_commit=false): on an "
                "element where it outlives the ~60 s transport limit a timed-out call "
                "returns no verdict at all while possibly having created a real row. "
                "The reads above are evidence, not a verdict -- confirm the new row "
                "and its values (browser_read_feature_parameters, or a feature-list "
                "read) before the next step."
            ),
        }
    if isinstance(commit.get("features"), dict):
        features = commit["features"]
        state = feature_state(features, feature_name)
        created = created_user_feature_rows(
            user_feature_rows(features), baseline_names
        )

    # `listed`/`errored` describe the row this call created. Reporting the
    # name-matched state alone would call a template-named row (which never
    # displays its Feature Type Name) absent, and miss an error on it.
    listed = state["listed"] or bool(created)
    errored = state["errored"] or any(row["hasError"] for row in created)
    created_names = [row["name"] for row in created]
    # The model's own statement of the values it took: a feature with a "Feature
    # Name Template" writes them into its row text, which is the only place an
    # expression's evaluated value can be read (see the docstring).
    row_verified = True if not expect_row else any(
        str(expect_row) in name for name in created_names
    )
    # `inserted` is a tri-state on the short path: None means the row may or may not
    # be there and the caller has to confirm it itself. It is never True there,
    # because the evidence that makes it True (the survived reload) was not taken.
    if not accepted_ok:
        inserted: bool | None = False
    elif not verify_commit:
        inserted = None
    elif commit.get("bootReady") is False:
        # The confirming reload landed on a document that never rendered its UI, so
        # the row was never counted. That is a non-verdict, not a failure: measured
        # live 2026-09-21, a slow post-accept boot made every step of a 23-row build
        # report ``inserted: False`` while the rows were in fact committed, and only
        # a re-read showed them. Never claim an outcome the read could not observe.
        inserted = None
    else:
        inserted = bool(commit["committed"]) and row_verified

    result = {
        "inserted": inserted,
        "applyState": (
            "pending_verification"
            if inserted is None
            else ("verified" if inserted else "not_inserted")
        ),
        "accepted": accepted,
        "parameters": filled,
        "expressionFields": expression_fields,
        "expectRow": expect_row,
        "expectValues": filled["expectValues"] if filled else {},
        "rowVerified": row_verified,
        "verifyCommit": verify_commit,
        "expressionWait": expression_wait,
        "listed": listed,
        "errored": errored,
        "workbenchAppeared": workbench_appeared,
        "featureRows": state["rows"],
        "createdRows": created,
        "baselineRows": baseline,
        "commit": {key: value for key, value in commit.items() if key != "features"},
        "waits": {
            "menu": opened,
            "dialog": dialog,
            "regeneration": regenerated,
            "commitSurvival": commit.get("survived"),
            "expressionResolve": expression_wait,
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
    if errored:
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
    elif commit.get("bootReady") is False:
        result["reason"] = (
            f"{commit.get('reason') or ''} The row was never counted, so this call "
            "reports neither success nor failure: re-read the Part Studio (or re-run "
            "the step) before assuming the feature was not applied."
        )
    elif commit.get("skipped"):
        result["reason"] = str(commit.get("reason") or "")
    elif not commit["committed"]:
        result["reason"] = str(commit.get("reason") or "")
    elif not row_verified:
        # The dialog WAS accepted, so this row is real and computed: it carries
        # values the caller did not ask for. It has to be deleted, not ignored --
        # the same rule as a refusal's default-valued row.
        result["reason"] = (
            f"the created row does not carry the expected text {expect_row!r}; it "
            f"reads {created_names!r}, so this row holds values the caller did not "
            "ask for and must be deleted before the step is retried"
        )
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
