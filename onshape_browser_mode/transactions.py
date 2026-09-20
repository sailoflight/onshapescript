"""Browser L2 transactions for Feature Studio and the shared document shell."""

from __future__ import annotations

import hashlib
import re
import time
from typing import Any

from onshape_browser_mode import actions, selectors


#: Bounded wait for a Parameter dialog to close after its accept button is
#: clicked. Kept for the one-shot form (``wait_for_regeneration=True``). The apply
#: stage no longer waits on it by default, because the close turned out **not** to be
#: a completion signal for an edit that changes a parameter: measured live 2026-09-20,
#: such an accept commits in seconds and the panel was still present 95 s later,
#: while an accept that changed nothing satisfied the condition in 4-5 ms.
PS_DIALOG_CLOSE_TIMEOUT_MS = 60_000

#: Second-stage probe for the same condition, and the discriminator for a real edit.
#: Four accepts on one feature with the accept's own before/after as the only
#: variable measured a bimodal latency — 4-5 ms when nothing changed, still
#: unsatisfied after 95 s when a parameter did — so a short bounded probe is what
#: separates them. A close that would have arrived after the probe is not lost: the
#: recovery path reads the same persisted values from a reloaded page.
PS_VERIFY_PROBE_TIMEOUT_MS = 3_000

#: Bounded wait for the reopened dialog that reads persisted values back.
PS_REOPEN_TIMEOUT_MS = 5_000

DOC_NAME = selectors.DOC_NAME
DOC_MENU = selectors.DOC_MENU
PANEL_ROOT = selectors.PANEL_ROOT
PANEL_FILTER = selectors.PANEL_FILTER
PANEL_CONTENT = selectors.PANEL_CONTENT
PANEL_SPLITTERS = selectors.PANEL_SPLITTERS
SELECTION_PREVIEW = selectors.SELECTION_PREVIEW
NOTIFICATIONS = selectors.DOCUMENTS_NOTIFICATION
NOTIFICATIONS_DRAWER = selectors.NOTIFICATIONS_DRAWER
SHARE_BUTTON = selectors.SHARE_BUTTON
SHARE_DIALOG = selectors.SHARE_DIALOG
VIEW_CUBE = selectors.VIEW_CUBE


def _visible_count(locator: Any) -> int:
    return sum(1 for index in range(locator.count()) if locator.nth(index).is_visible())


def _exact_text(locator: Any, expected: str) -> Any | None:
    normalized = expected.strip()
    matches = []
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible() and candidate.inner_text().strip() == normalized:
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _ace_cursor(page: Any) -> dict[str, Any]:
    result = page.evaluate(
        """
        () => {
          const el = document.querySelector('.ace_editor');
          const ed = el && ((el.env && el.env.editor) || (window.ace && window.ace.edit(el)));
          if (!ed) return {found: false};
          const cursor = ed.getCursorPosition();
          const lineText = ed.session.getLine(cursor.row) || '';
          return {found: true, row: cursor.row, column: cursor.column, lineText};
        }
        """
    )
    return result if isinstance(result, dict) else {"found": False}


def fs_goto_definition(page: Any, symbol: str) -> dict[str, Any]:
    """Navigate to a top-level definition through Module outline."""
    inventory = actions.read_featurescript_symbols(page)
    available = [item.get("name") for item in inventory.get("symbols", [])]
    if symbol not in available:
        return {
            "definitionFound": False,
            "symbol": symbol,
            "availableSymbols": available,
            "reason": f"symbol {symbol!r} is not present in Module outline",
        }
    before = _ace_cursor(page)
    item = _exact_text(page.locator(selectors.FS_MODULE_OUTLINE_NAME), symbol)
    if item is None:
        return {"definitionFound": False, "symbol": symbol, "reason": "exact outline symbol row not found"}
    item.click()
    page.wait_for_timeout(250)
    after = _ace_cursor(page)
    line_tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", str(after.get("lineText", "")))
    target_verified = bool(after.get("found")) and symbol in line_tokens
    cursor_changed = (before.get("row"), before.get("column")) != (after.get("row"), after.get("column"))
    return {
        "definitionFound": target_verified,
        "symbol": symbol,
        "beforeCursor": before,
        "cursor": after,
        "cursorChanged": cursor_changed,
        "alreadyAtDefinition": target_verified and not cursor_changed,
        "navigation": "module-outline",
    }


def _insert_source_text(
    page: Any,
    snippet: str,
    *,
    row: int | None = None,
    column: int | None = None,
) -> dict[str, Any]:
    """Insert caller-provided FeatureScript text through the Ace API."""
    before_commit = actions.commit_button_state(page)
    result = page.evaluate(
        """
        (args) => {
          const el = document.querySelector('.ace_editor');
          const ed = el && ((el.env && el.env.editor) || (window.ace && window.ace.edit(el)));
          if (!ed) return {snippetInserted: false, reason: 'FeatureScript editor not found'};
          const before = ed.getValue();
          const cursor = ed.getCursorPosition();
          const row = Number.isInteger(args.row) ? args.row : cursor.row;
          const column = Number.isInteger(args.column) ? args.column : cursor.column;
          ed.session.insert({row, column}, args.snippet);
          const after = ed.getValue();
          return {
            snippetInserted: after.length === before.length + args.snippet.length,
            row,
            column,
            beforeLength: before.length,
            afterLength: after.length,
            insertedLength: args.snippet.length,
            sourceChanged: before !== after,
          };
        }
        """,
        {"snippet": snippet, "row": row, "column": column},
    )
    if not isinstance(result, dict):
        return {"snippetInserted": False, "reason": "Ace insertion returned no state"}
    after_commit = actions.commit_button_state(page)
    dirty = after_commit.get("found") and after_commit.get("disabled") is False
    result.update({
        "snippetInserted": bool(result.get("snippetInserted")) and dirty,
        "commitDirty": dirty,
        "commitBefore": before_commit,
        "commitAfter": after_commit,
    })
    return result


def fs_insert_snippet(
    page: Any,
    *,
    row: int | None = None,
    column: int | None = None,
) -> dict[str, Any]:
    """Invoke the verified Ace 插入代码段 command and verify its exact delta."""
    before = actions.read_featurescript_editor(page)
    if before is None:
        return {"snippetInserted": False, "reason": "FeatureScript editor not found"}
    before_commit = actions.commit_button_state(page)
    point = page.evaluate(
        """
        (args) => {
          const el = document.querySelector('.ace_editor');
          const ed = el && ((el.env && el.env.editor) || (window.ace && window.ace.edit(el)));
          if (!ed) return null;
          const cursor = ed.getCursorPosition();
          const row = Number.isInteger(args.row) ? args.row : cursor.row;
          const column = Number.isInteger(args.column) ? args.column : cursor.column;
          ed.moveCursorTo(row, column);
          ed.clearSelection();
          ed.renderer.scrollCursorIntoView();
          const screen = ed.renderer.textToScreenCoordinates(row, column);
          return {row, column, x: screen.pageX, y: screen.pageY};
        }
        """,
        {"row": row, "column": column},
    )
    if not isinstance(point, dict):
        return {"snippetInserted": False, "reason": "Ace cursor coordinates unavailable"}
    page.mouse.click(point["x"], point["y"], button="right")
    command = _exact_text(page.locator(selectors.TAB_CONTEXT_MENU_ITEM), "插入代码段")
    if command is None:
        return {"snippetInserted": False, "reason": "exact 插入代码段 command not found", "cursor": point}
    command.click()
    page.wait_for_timeout(250)
    after = actions.read_featurescript_editor(page)
    after_commit = actions.commit_button_state(page)
    if not isinstance(after, str):
        return {"snippetInserted": False, "reason": "FeatureScript source unreadable after command"}
    prefix = 0
    while prefix < min(len(before), len(after)) and before[prefix] == after[prefix]:
        prefix += 1
    suffix = 0
    while suffix < min(len(before) - prefix, len(after) - prefix) and before[-1 - suffix] == after[-1 - suffix]:
        suffix += 1
    inserted = after[prefix:len(after) - suffix if suffix else len(after)]
    dirty = after_commit.get("found") and after_commit.get("disabled") is False
    return {
        "snippetInserted": bool(inserted) and len(after) > len(before) and dirty,
        "cursor": {"row": point["row"], "column": point["column"]},
        "beforeLength": len(before),
        "afterLength": len(after),
        "insertedLength": len(inserted),
        "insertedPreview": inserted[:500],
        "commitDirty": dirty,
        "commitBefore": before_commit,
        "commitAfter": after_commit,
        "command": "插入代码段",
    }


def fs_insert_parameter(
    page: Any,
    *,
    parameter_source: str = "",
    row: int | None = None,
    column: int | None = None,
) -> dict[str, Any]:
    """Insert a Length parameter template or explicit parameter source."""
    if parameter_source:
        before_commit = actions.commit_button_state(page)
        result = _insert_source_text(page, parameter_source, row=row, column=column)
        after_commit = actions.commit_button_state(page)
        dirty = after_commit.get("found") and after_commit.get("disabled") is False
        return {
            "parameterInserted": bool(result.get("snippetInserted")) and dirty,
            "mode": "source",
            "commitDirty": dirty,
            "commitBefore": before_commit,
            "commitAfter": after_commit,
            **result,
        }
    before = actions.read_featurescript_editor(page)
    if before is None:
        return {"parameterInserted": False, "reason": "FeatureScript editor not found"}
    button = page.locator(selectors.FS_TOOLBAR).locator(selectors.FS_TOOL_BUTTON).filter(has_text="Length parameter")
    if button.count() == 0:
        return {"parameterInserted": False, "reason": "Length parameter toolbar button not found"}
    if row is not None or column is not None:
        page.evaluate(
            """
            (args) => {
              const el = document.querySelector('.ace_editor');
              const ed = el && ((el.env && el.env.editor) || (window.ace && window.ace.edit(el)));
              if (!ed) return false;
              const cursor = ed.getCursorPosition();
              ed.moveCursorTo(Number.isInteger(args.row) ? args.row : cursor.row,
                              Number.isInteger(args.column) ? args.column : cursor.column);
              ed.clearSelection();
              ed.focus();
              return true;
            }
            """,
            {"row": row, "column": column},
        )
    before_commit = actions.commit_button_state(page)
    button.first.click()
    page.wait_for_timeout(300)
    after = actions.read_featurescript_editor(page)
    after_commit = actions.commit_button_state(page)
    dirty = after_commit.get("found") and after_commit.get("disabled") is False
    return {
        "parameterInserted": isinstance(after, str) and after != before and dirty,
        "mode": "toolbar",
        "beforeLength": len(before),
        "afterLength": len(after) if isinstance(after, str) else None,
        "sourceChanged": isinstance(after, str) and after != before,
        "commitDirty": dirty,
        "commitBefore": before_commit,
        "commitAfter": after_commit,
    }


def fs_toggle_fold(page: Any, *, row: int | None = None, action: str = "toggle") -> dict[str, Any]:
    """Fold, unfold, or toggle the fold at an Ace row and return all folds."""
    result = page.evaluate(
        """
        (args) => {
          const el = document.querySelector('.ace_editor');
          const ed = el && ((el.env && el.env.editor) || (window.ace && window.ace.edit(el)));
          if (!ed) return {foldChanged: false, reason: 'FeatureScript editor not found'};
          const targetRow = Number.isInteger(args.row) ? args.row : ed.getCursorPosition().row;
          const serialize = () => (ed.session.getAllFolds ? ed.session.getAllFolds() : []).map(fold => ({
            startRow: fold.start.row,
            startColumn: fold.start.column,
            endRow: fold.end.row,
            endColumn: fold.end.column,
            placeholder: String(fold.placeholder || ''),
          }));
          const before = serialize();
          ed.moveCursorTo(targetRow, 0);
          const command = args.action === 'fold' ? 'fold' : (args.action === 'unfold' ? 'unfold' : 'toggleFoldWidget');
          ed.execCommand(command);
          const after = serialize();
          const changed = JSON.stringify(before) !== JSON.stringify(after);
          const targetFolded = after.some(fold => fold.startRow <= targetRow && fold.endRow >= targetRow);
          return {
            foldChanged: changed,
            foldStateApplied: args.action === 'toggle' ? changed : (args.action === 'fold' ? targetFolded : !targetFolded),
            targetFolded,
            alreadyInState: !changed && ((args.action === 'fold' && targetFolded) || (args.action === 'unfold' && !targetFolded)),
            action: args.action,
            row: targetRow,
            beforeFolds: before,
            foldedRanges: after,
            foldCount: after.length,
          };
        }
        """,
        {"row": row, "action": action},
    )
    return result if isinstance(result, dict) else {"foldChanged": False, "reason": "Ace fold command returned no state"}


def _dialog_values(page: Any) -> dict[str, str]:
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


def _locate_feature_row(page: Any, feature_name: str) -> tuple[Any | None, dict[str, Any]]:
    """Locate exactly one custom-feature row from ONE enumeration of the DOM.

    Identity and position must come from the same enumeration, because a read that
    FILTERS and a locator that COUNTS are different sets. Measured live 2026-09-20:
    ``read_partstudio_features`` drops a row whose ``innerText`` and ``textContent``
    are both empty, while ``page.locator('.os-list-item.ns-user-feature')`` counts
    it, so the two disagreed by exactly one on every Part Studio — 1 named row
    against 2, and 11 against 12. Comparing them therefore refused on EVERY element,
    which was the right instinct (the locator's set contains a row the read cannot
    account for) and still made this tool unusable. Measured again after the fix on
    ``Spiral ridge PS``, that nameless node is the LAST node in document order, so
    the index itself was never shifted and the refusal came from the count
    comparison alone. Position is not a contract — the replacement below is correct
    whatever position such a node occupies.

    That is also why the earlier name-only locator failed: measured live
    2026-09-20, ``.filter(has_text='Sr Spiral ridge 7')`` reported a count other
    than one for the row a read returned as the single match, deterministically
    over four attempts and two page reloads.

    So: wait for the panel to render, enumerate the custom-feature rows once
    (``enumerate_user_feature_rows``), and take the match and its click index from
    that one list. The locator count is kept only as a staleness check: it
    re-queries the page, so a change between the enumeration and the click is
    reported instead of clicked through.
    """
    panel_ready = actions.wait_for_panel_rows(page, actions.PARTSTUDIO_PANEL_READY_TIMEOUT_MS)
    enumerated = actions.enumerate_user_feature_rows(page, selectors.PS_USER_FEATURE)
    names = enumerated["names"]
    indices = actions.match_user_feature_row_indices(names, feature_name)
    evidence: dict[str, Any] = {
        "panelReady": panel_ready,
        "featureRows": names,
        "matchedRows": [names[index] for index in indices],
        "locatorRows": enumerated["count"],
    }
    if not names:
        reason = (
            "no custom-feature row is on screen (the live enumeration found "
            f"{enumerated['count']} matching node(s))"
        )
        if not panel_ready.get("waited"):
            reason += f"; the panel never rendered rows: {panel_ready.get('error', '')}"
        evidence["reason"] = reason
        return None, evidence
    if len(indices) != 1:
        evidence["reason"] = (
            f"feature {feature_name!r} matched {len(indices)} of "
            f"{len(names)} custom-feature rows: "
            f"{[names[index] for index in indices]}"
        )
        return None, evidence
    rows = page.locator(selectors.PS_USER_FEATURE)
    seen = rows.count()
    evidence["locatorRows"] = seen
    if seen != enumerated["count"]:
        evidence["reason"] = (
            f"the page enumeration lists {enumerated['count']} custom-feature rows "
            f"but the row locator sees {seen}; refusing to click a row that may be "
            "a different one"
        )
        return None, evidence
    return rows.nth(indices[0]), evidence


def _wait_for_dialog_close(page: Any, timeout_ms: int) -> dict[str, Any]:
    """Wait until the Parameter dialog is gone, or report how long it was given.

    Timeout is returned as data, never raised: on the apply stage a timeout is not a
    failure (the accept click already committed the edit) and on the verify stage it
    only means "not finished yet".
    """
    started = time.monotonic()
    try:
        page.wait_for_function(
            "(selector) => document.querySelector(selector) === null",
            arg=selectors.PS_FEATURE_DIALOG,
            timeout=timeout_ms,
        )
        waited, error = True, ""
    except Exception as exc:  # noqa: BLE001 - a timeout is evidence, not a crash
        waited, error = False, f"{type(exc).__name__}: {exc}"
    return {
        "waited": waited,
        "condition": "feature_dialog_absent",
        "timeoutMs": timeout_ms,
        "elapsedMs": round((time.monotonic() - started) * 1000),
        **({"error": error} if error else {}),
    }


def edit_feature_parameters(
    page: Any,
    feature_name: str,
    parameters: dict[str, Any],
    *,
    accept: bool = True,
    wait_for_regeneration: bool = False,
) -> dict[str, Any]:
    """Open a custom feature dialog, update named fields, and accept it.

    Two stages, because one stage does not fit a transport budget. Accepting a
    Parameter dialog re-evaluates the model before the dialog reports closed, and on
    an element with 11 user features that measured **61.7 s** end to end — past a
    60 s relay limit, so the caller received ``-32001 downstream_timeout`` for an
    operation that had very likely been applied. Losing the result of a write is the
    same false-negative class as the locate defect this path was just fixed for, so:

    * the default (``wait_for_regeneration=False``) returns as soon as the accept
      button is clicked. Wall time is the locate, the dialog, the fills and the
      readback — seconds — and the result says ``applyState:
      "pending_verification"`` with ``parametersApplied: None``, never ``False``,
      because the write is not known to have failed. ``verifyWith`` carries the
      exact follow-up call.
    * ``wait_for_regeneration=True`` keeps the original one-shot behaviour for a
      caller whose transport budget allows it.

    The verdict belongs to :func:`verify_feature_parameters`.

    Every return carries ``featureRow``: the read-identified row evidence
    (``panelReady``, ``featureRows``, ``matchedRows``, ``locatorRows``). A refusal
    without a click reports which rows existed and which ones the name matched, so
    an unusable row name is diagnosable from the result alone.
    """
    row, evidence = _locate_feature_row(page, feature_name)
    if row is None:
        return {
            "parametersApplied": False,
            "applyState": "refused",
            "pendingVerification": False,
            "featureName": feature_name,
            "featureRow": evidence,
            "reason": evidence.get("reason", ""),
        }
    row.dblclick()
    dialog = page.locator(selectors.PS_FEATURE_DIALOG).first
    try:
        dialog.wait_for(state="visible", timeout=10_000)
    except Exception as exc:  # noqa: BLE001
        return {
            "parametersApplied": False,
            "applyState": "failed",
            "pendingVerification": False,
            "featureName": feature_name,
            "featureRow": evidence,
            "reason": f"feature dialog did not open: {exc}",
        }
    before = _dialog_values(page)
    missing = []
    updated = []
    for key, value in parameters.items():
        locator = dialog.locator(
            f'[data-parameter-id="{key}"] input, [parameter-id="{key}"] input, '
            f'input[name="{key}"], textarea[name="{key}"], select[name="{key}"], #{key}'
        )
        if locator.count() == 0:
            container = dialog.locator(".parameter-item, .feature-parameter").filter(has_text=str(key))
            locator = container.locator("input, textarea, select") if container.count() else locator
        if locator.count() == 0:
            missing.append(str(key))
            continue
        target = locator.first
        if isinstance(value, bool):
            checked = target.is_checked()
            if checked != value:
                target.click()
        else:
            target.fill(str(value))
        updated.append(str(key))
    after = _dialog_values(page)
    desired = {key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in parameters.items()}
    readback_ok = all(str(after.get(key, "")).lower() == value.lower() for key, value in desired.items())
    accepted = False
    accept_evidence: dict[str, Any] = {}
    if accept and not missing and readback_ok:
        button = dialog.locator(selectors.PS_FEATURE_DIALOG_ACCEPT)
        if button.count() == 0:
            button = page.locator(selectors.PS_FEATURE_DIALOG_ACCEPT)
        accept_evidence = {"clicked": False, "waitMs": 0}
        if button.count() > 0:
            button.first.click()
            accept_evidence["clicked"] = True
            if not wait_for_regeneration:
                # The click is the commit; the dialog closes when the model has been
                # re-evaluated. Return now and let the second stage answer.
                return {
                    "parametersApplied": None,
                    "applyState": "pending_verification",
                    "pendingVerification": True,
                    "featureName": feature_name,
                    "updated": updated,
                    "missing": missing,
                    "before": before,
                    "after": after,
                    "readbackOk": readback_ok,
                    "accept": accept_evidence,
                    "featureRow": evidence,
                    "verifyWith": {
                        "tool": "browser_verify_feature_parameters",
                        "arguments": {
                            "feature_name": feature_name,
                            "parameters": parameters,
                        },
                    },
                    "reason": (
                        "the dialog was accepted and the model is re-evaluating; this "
                        "stage returns before the dialog reports closed so the call "
                        "fits the transport budget. The edit is neither confirmed nor "
                        "failed — verify with browser_verify_feature_parameters"
                    ),
                }
            # The dialog closes only after the model has been re-evaluated, and a
            # real Part Studio takes seconds to do that. A fixed sleep here
            # misreports a successful edit as a failure: measured live 2026-09-20
            # on a 7-feature element, a 500 ms sleep + count check returned
            # `accepted: false` for an edit that HAD been applied (the next run
            # opened the dialog on the new values). Wait on the condition instead,
            # bounded, and report how long it took.
            close = _wait_for_dialog_close(page, PS_DIALOG_CLOSE_TIMEOUT_MS)
            accepted = close["waited"] or page.locator(selectors.PS_FEATURE_DIALOG).count() == 0
            accept_evidence["timeoutMs"] = close["timeoutMs"]
            accept_evidence["waited"] = accepted
            accept_evidence["waitMs"] = close["elapsedMs"]
    after_state = actions.feature_state(
        actions.read_partstudio_features(page) if accepted else {"features": []},
        feature_name,
    )
    matching_features = after_state["rows"]
    regeneration_ok = len(matching_features) == 1 and not after_state["errored"]
    persisted = {}
    persistence_ok = False
    if accepted and regeneration_ok:
        row.dblclick()
        reopened = page.locator(selectors.PS_FEATURE_DIALOG).first
        try:
            reopened.wait_for(state="visible", timeout=PS_REOPEN_TIMEOUT_MS)
            persisted = _dialog_values(page)
            persistence_ok = all(str(persisted.get(key, "")).lower() == value.lower() for key, value in desired.items())
        except Exception:
            persistence_ok = False
        finally:
            page.keyboard.press("Escape")
    applied = (
        not missing
        and len(updated) == len(parameters)
        and readback_ok
        and accepted
        and regeneration_ok
        and persistence_ok
    )
    return {
        "parametersApplied": applied,
        "applyState": "confirmed" if applied else "failed",
        "pendingVerification": False,
        "featureName": feature_name,
        "updated": updated,
        "missing": missing,
        "before": before,
        "after": after,
        "readbackOk": readback_ok,
        "accepted": accepted,
        "accept": accept_evidence,
        "regenerationOk": regeneration_ok,
        "persisted": persisted,
        "persistenceOk": persistence_ok,
        "featureState": matching_features,
        "featureRow": evidence,
    }


def _values_match(persisted: dict[str, Any], requested: dict[str, Any]) -> bool:
    """Compare a read-back against the requested values, case-insensitively.

    A checkbox yields ``"true"``/``"false"``, and a length arrives already formatted
    (``"12 mm"``), so an exact comparison is the only honest one: no unit is guessed and
    no value is coerced.
    """
    return all(
        str(persisted.get(key, "")).lower()
        == (str(value).lower() if isinstance(value, bool) else str(value)).lower()
        for key, value in requested.items()
    )


def _open_and_read_parameters(page: Any, feature_name: str) -> dict[str, Any]:
    """Open one feature's Parameter dialog, read its values, then cancel it.

    Reading is the whole point, so no field is ever filled and the dialog is always
    cancelled with Escape: the only cloud-visible act is the dialog's own open and
    cancel. ``read`` says the dialog opened and its fields were read. A feature whose
    ``precondition`` carries no parameter annotations opens a real dialog that has no
    editable fields, which is ``read: True`` with ``parameterCount: 0`` — an
    observation, not an error.
    """
    row, evidence = _locate_feature_row(page, feature_name)
    result: dict[str, Any] = {
        "read": False,
        "parameters": {},
        "parameterCount": 0,
        "featureRow": evidence,
    }
    if row is None:
        result["reason"] = evidence.get("reason", "")
        return result
    row.dblclick()
    dialog = page.locator(selectors.PS_FEATURE_DIALOG).first
    values: dict[str, Any] = {}
    opened = False
    try:
        dialog.wait_for(state="visible", timeout=PS_REOPEN_TIMEOUT_MS)
        opened = True
        values = _dialog_values(page)
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["reason"] = f"feature dialog did not open: {exc}"
    finally:
        # Opened only to be read, so it is always cancelled. When it never opened this
        # is a no-op on a page that has no dialog in front.
        page.keyboard.press("Escape")
    result["read"] = opened
    result["parameters"] = values
    result["parameterCount"] = len(values)
    return result


def read_feature_parameters(
    page: Any,
    feature_name: str,
    *,
    dialog_timeout_ms: int = PS_VERIFY_PROBE_TIMEOUT_MS,
    allow_reload: bool = False,
) -> dict[str, Any]:
    """Read one feature's current parameter values without changing the model.

    A dialog's fields show what was last typed into them, so a dialog that is already
    open cannot separate a typed-but-uncommitted value from a persisted one. This
    therefore reads from a dialog it opens itself, and its only dialog gesture is
    Escape.

    When a Parameter dialog is already on screen and ``allow_reload`` is false, the
    call reads nothing and says so rather than guessing: an accept that changes a
    parameter commits and can leave the panel open for minutes (measured live
    2026-09-20: still present 95 s after the accept, where a no-op accept closed in
    4-5 ms). ``allow_reload`` permits the bounded page reload that discards such a panel
    without reverting the commit — the recovery :func:`verify_feature_parameters` uses
    by default. It is off here because a read should not silently navigate the page.
    """
    close = _wait_for_dialog_close(page, dialog_timeout_ms)
    recovery: dict[str, Any] | None = None
    feature_list: dict[str, Any] | None = None
    if not close["waited"]:
        if not allow_reload:
            return {
                "read": False,
                "featureName": feature_name,
                "parameters": {},
                "parameterCount": 0,
                "dialogClosed": close,
                "retryable": True,
                "reason": (
                    "a Parameter dialog is already open and its fields show what was "
                    "last typed into them rather than what is persisted, so nothing "
                    "was read. Clear it first (browser_session reload) and call again, "
                    "pass allow_reload=true, or call "
                    "browser_verify_feature_parameters, which reloads and reads."
                ),
            }
        recovery = actions.reload_page(page)
        if not recovery.get("reloaded"):
            return {
                "read": False,
                "featureName": feature_name,
                "parameters": {},
                "parameterCount": 0,
                "dialogClosed": close,
                "recovery": recovery,
                "retryable": True,
                "reason": (
                    "a Parameter dialog was open and the recovery reload did not "
                    "complete, so no committed page could be read"
                ),
            }
        close = _wait_for_dialog_close(page, PS_REOPEN_TIMEOUT_MS)
        # The reload replaced the DOM with a page that renders in stages. Waiting only
        # for "some list item exists" is not enough: measured live 2026-09-20 that
        # condition was satisfied 2736 ms into the reload while the row enumeration
        # still found 0 custom features and even the tab strip was missing, so the read
        # raced the render and reported no row. Wait for the Feature List itself.
        feature_list = actions.wait_for_feature_list(
            page, actions.PARTSTUDIO_PANEL_READY_TIMEOUT_MS, selector=selectors.PS_USER_FEATURE
        )
    read = _open_and_read_parameters(page, feature_name)
    return {
        "read": read["read"],
        "featureName": feature_name,
        "parameters": read["parameters"],
        "parameterCount": read["parameterCount"],
        "featureRow": read["featureRow"],
        "dialogClosed": close,
        "recovery": recovery,
        **({"featureListReady": feature_list} if recovery else {}),
        **({"reason": read["reason"]} if read.get("reason") else {}),
        **({"error": read["error"]} if read.get("error") else {}),
    }


def verify_feature_parameters(
    page: Any,
    feature_name: str,
    parameters: dict[str, Any],
    *,
    dialog_timeout_ms: int = PS_VERIFY_PROBE_TIMEOUT_MS,
    allow_reload: bool = True,
) -> dict[str, Any]:
    """Second stage of :func:`edit_feature_parameters`: confirm what was applied.

    One stage cannot both commit and confirm inside a transport budget, so the apply
    stage returns ``pending_verification`` and this stage answers later. It never
    guesses, and the fourth live step (2026-09-20) showed that the panel's removal is
    not a signal to guess from: an accept that changed a parameter had committed while
    ``.feature-dialog`` was still present 95 s later, where an accept that changed
    nothing satisfied the same condition in 4-5 ms.

    So the condition is probed briefly and then, by default, **recovered by reloading
    the page**. That is the pattern this repository already uses to prove a commit (see
    :func:`actions.confirm_workspace_commit`): a bounded reload discards the open panel,
    does not revert a committed edit (measured twice on 2026-09-20), and yields a row
    list that cannot be the pre-accept DOM. It also spends 0 API quota. Pass
    ``allow_reload=False`` to refuse the navigation and keep the previous "call again"
    behaviour.

    A non-verdict reached after a recovery reload is reported as ``parametersApplied:
    None`` with ``retryVerify: true``, never as a failure, because that reload may have
    raced the commit. The next call finds the panel already gone, reads a committed
    page, and can then answer definitively. Only a non-verdict read without a recovery
    reload is a definitive ``False``.
    """
    close = _wait_for_dialog_close(page, dialog_timeout_ms)
    recovery: dict[str, Any] | None = None
    feature_list: dict[str, Any] | None = None
    recovered_by = ""
    if not close["waited"]:
        if not allow_reload:
            return {
                "verified": False,
                "parametersApplied": None,
                "featureName": feature_name,
                "dialogClosed": close,
                "regenerationOk": False,
                "persistenceOk": None,
                "featureState": [],
                "persisted": {},
                "retryVerify": True,
                "reason": (
                    "the feature dialog had not reported closed after "
                    f"{close['timeoutMs']} ms and the recovery reload is disabled, so "
                    "the row list may still be the pre-accept DOM and the persisted "
                    "values cannot be read yet; call again"
                ),
            }
        recovery = actions.reload_page(page)
        if not recovery.get("reloaded"):
            return {
                "verified": False,
                "parametersApplied": None,
                "featureName": feature_name,
                "dialogClosed": close,
                "recovery": recovery,
                "regenerationOk": False,
                "persistenceOk": None,
                "featureState": [],
                "persisted": {},
                "retryVerify": True,
                "reason": (
                    "the feature dialog had not reported closed after "
                    f"{close['timeoutMs']} ms and the recovery reload did not "
                    "complete, so the persisted values could not be read from a "
                    "committed page; call again"
                ),
            }
        recovered_by = "page_reload"
        # The reload replaces the DOM, so nothing read from here on can be the
        # pre-accept page, and the panel went with the old page.
        close = _wait_for_dialog_close(page, PS_REOPEN_TIMEOUT_MS)
        # A fresh page renders in stages, and reading the rows before the Feature List
        # exists is what made the first live run of this recovery return "0 rows" and
        # no verdict (measured 2026-09-20: the whole recovery block finished in 151 ms
        # against a page whose tab strip had not rendered yet). Wait for the CUSTOM-feature
        # rows this stage is about to enumerate -- a bare list-item count is satisfied by
        # part-list rows and the tab strip, which is how the read probe's wait passed at
        # 2736 ms on a page that still enumerated 0 features.
        feature_list = actions.wait_for_feature_list(
            page, actions.PARTSTUDIO_PANEL_READY_TIMEOUT_MS, selector=selectors.PS_USER_FEATURE
        )
    state = actions.feature_state(actions.read_partstudio_features(page), feature_name)
    rows = state["rows"]
    regeneration_ok = len(rows) == 1 and not state["errored"]
    result: dict[str, Any] = {
        "verified": False,
        "parametersApplied": None,
        "featureName": feature_name,
        "dialogClosed": close,
        "regenerationOk": regeneration_ok,
        "persistenceOk": None,
        "featureState": rows,
        "persisted": {},
        "featureRow": {},
    }
    if recovered_by:
        result["recoveredBy"] = recovered_by
        result["recovery"] = recovery
        result["featureListReady"] = feature_list
    failure = ""
    if not regeneration_ok:
        result["persistenceOk"] = False
        failure = (
            f"the accepted edit left {len(rows)} row(s) named {feature_name!r} and "
            f"errored={state['errored']}, so it did not regenerate cleanly"
        )
    else:
        read = _open_and_read_parameters(page, feature_name)
        result["featureRow"] = read["featureRow"]
        if not read["read"]:
            result["retryVerify"] = True
            result["reason"] = (
                "the row could not be re-located and re-opened to read its values "
                f"back: {read.get('reason', '')}"
            )
            if read.get("error"):
                result["error"] = read["error"]
            return result
        persisted = read["parameters"]
        persistence_ok = _values_match(persisted, parameters)
        result["persisted"] = persisted
        result["persistenceOk"] = persistence_ok
        result["verified"] = persistence_ok
        if not persistence_ok:
            failure = (
                "the accepted edit regenerated cleanly but the reopened dialog did "
                f"not show the requested values: persisted={persisted}"
            )
    if result["verified"]:
        result["parametersApplied"] = True
        return result
    if recovered_by:
        result["parametersApplied"] = None
        result["retryVerify"] = True
        result["reason"] = (
            f"{failure}; this read followed the recovery page reload, which may have "
            "raced the commit, so it is not reported as a failure — call again; the "
            "dialog is closed now and the next call reads a committed page"
        )
        return result
    result["parametersApplied"] = False
    result["reason"] = failure
    return result



def fs_watch_part_studio(
    page: Any,
    part_studio: str,
    *,
    mode: str = "watch",
) -> dict[str, Any]:
    """Select one exact watch/configure target and verify toolbar readback."""
    prefix = "监控" if mode == "watch" else "配置文件"
    desired = f"{prefix} {part_studio}"
    root = page.locator(selectors.FS_WATCH_CONFIG_MENU)
    current = page.locator(selectors.FS_WATCH_CONFIG_CURRENT)
    if root.count() != 1 or current.count() != 1:
        return {"watchConfigured": False, "reason": "watch/configure toolbar control not found uniquely"}
    before = current.first.inner_text().strip()
    if before == desired:
        return {
            "watchConfigured": True,
            "mode": mode,
            "partStudio": part_studio,
            "before": before,
            "after": before,
            "changed": False,
            "alreadyConfigured": True,
            "compileStatus": actions.read_featurescript_compile_status(page),
        }
    opener = page.locator(selectors.FS_WATCH_CONFIG_OPEN)
    if opener.count() != 1:
        return {"watchConfigured": False, "reason": "watch/configure dropdown opener not found uniquely"}
    opener.first.click()
    items = page.locator(selectors.FS_WATCH_CONFIG_ITEM)
    try:
        items.first.wait_for(state="visible", timeout=5_000)
    except Exception as exc:  # noqa: BLE001
        return {"watchConfigured": False, "reason": f"watch/configure dropdown did not open: {exc}"}
    labels = [
        items.nth(index).inner_text().strip()
        for index in range(items.count())
        if items.nth(index).is_visible() and items.nth(index).inner_text().strip()
    ]
    target = _exact_text(items, desired)
    if target is None:
        return {"watchConfigured": False, "desired": desired, "menuItems": labels, "reason": "exact watch/configure target not found"}
    target.click()
    try:
        page.wait_for_function(
            "(args) => { const el = document.querySelector(args.selector); return !!el && (el.innerText || el.textContent || '').trim() === args.desired; }",
            arg={"selector": selectors.FS_WATCH_CONFIG_CURRENT, "desired": desired},
            timeout=10_000,
        )
    except Exception:
        pass
    after = current.first.inner_text().strip()
    return {
        "watchConfigured": after == desired,
        "mode": mode,
        "partStudio": part_studio,
        "before": before,
        "after": after,
        "changed": before != after,
        "alreadyConfigured": False,
        "menuItems": labels,
        "compileStatus": actions.read_featurescript_compile_status(page),
    }


def open_doc_menu(page: Any, command: str = "") -> dict[str, Any]:
    """Open the document-name menu and optionally trigger one exact command."""
    button = page.locator(DOC_NAME)
    if button.count() == 0:
        return {"menuOpened": False, "reason": "document name control not found"}
    button.first.click()
    menu = page.locator(DOC_MENU).first
    try:
        menu.wait_for(state="visible", timeout=5_000)
    except Exception as exc:  # noqa: BLE001
        return {"menuOpened": False, "reason": f"document menu did not open: {exc}"}
    rows = menu.locator("a, button, li")
    items = [rows.nth(index).inner_text().strip() for index in range(rows.count()) if rows.nth(index).inner_text().strip()]
    triggered = False
    if command:
        target = _exact_text(rows, command)
        if target is not None:
            target.click()
            triggered = True
    return {
        "menuOpened": not command or triggered,
        "menuVisible": True,
        "items": items,
        "command": command,
        "commandTriggered": triggered,
    }


def set_panel_filter(page: Any, query: str) -> dict[str, Any]:
    """Set the left-panel filter and verify the visible tree narrows."""
    root = page.locator(PANEL_ROOT).first
    field = page.locator(PANEL_FILTER).first
    if root.count() == 0 or field.count() == 0:
        return {"filterApplied": False, "reason": "left-panel filter not found"}
    rows = root.locator(selectors.PS_FEATURE_LIST_ITEM)
    before = _visible_count(rows)
    field.fill(query)
    page.wait_for_timeout(250)
    after = _visible_count(rows)
    value = field.input_value()
    return {
        "filterApplied": value == query and after <= before,
        "query": query,
        "inputValue": value,
        "beforeCount": before,
        "afterCount": after,
        "treeNarrowed": after < before,
    }


def _panel_state(page: Any, panel_selector: str = PANEL_CONTENT) -> dict[str, Any]:
    result = page.evaluate(
        """
        (selector) => {
          const panel = document.querySelector(selector);
          if (!panel) return {present: false, visible: false, x: 0, width: 0};
          const rect = panel.getBoundingClientRect();
          return {present: true, visible: !!panel.offsetParent && rect.width > 20, x: rect.x, width: rect.width, height: rect.height};
        }
        """,
        panel_selector,
    )
    return result if isinstance(result, dict) else {"present": False, "visible": False, "width": 0}


def toggle_left_panel(
    page: Any,
    *,
    target: str = "toggle",
    panel_selector: str = PANEL_CONTENT,
    splitter_selector: str = PANEL_SPLITTERS,
    expanded_width: int = 200,
) -> dict[str, Any]:
    """Collapse or expand the left panel by dragging its vertical splitter."""
    before = _panel_state(page, panel_selector)
    desired = not before.get("visible") if target == "toggle" else target == "show"
    if bool(before.get("visible")) == desired:
        return {"panelToggled": True, "target": target, "before": before, "after": before, "changed": False}
    splitter = page.evaluate(
        """
        (args) => {
          const candidates = Array.from(document.querySelectorAll(args.selector))
            .map(el => ({el, rect: el.getBoundingClientRect()}))
            .filter(item => item.rect.height > 100 && item.rect.width <= 8);
          if (!candidates.length) return null;
          candidates.sort((a, b) => Math.abs(a.rect.x - args.targetX) - Math.abs(b.rect.x - args.targetX));
          const r = candidates[0].rect;
          return {x: r.x + r.width / 2, y: r.y + r.height / 2};
        }
        """,
        {"selector": splitter_selector, "targetX": before.get("x", 0) + before.get("width", 0)},
    )
    if not isinstance(splitter, dict):
        return {"panelToggled": False, "target": target, "before": before, "reason": "vertical panel splitter not found"}
    page.mouse.move(splitter["x"], splitter["y"])
    page.mouse.down()
    target_x = before.get("x", 0) + (expanded_width if desired else 8)
    page.mouse.move(target_x, splitter["y"], steps=5)
    page.mouse.up()
    page.wait_for_timeout(250)
    after = _panel_state(page, panel_selector)
    return {
        "panelToggled": bool(after.get("visible")) == desired,
        "target": target,
        "before": before,
        "after": after,
        "changed": bool(before.get("visible")) != bool(after.get("visible")),
    }


def read_selection_preview(page: Any, selector: str = SELECTION_PREVIEW) -> dict[str, Any]:
    """Read a visible selection/tab-preview card without changing selection."""
    result = page.evaluate(
        """
        (selector) => {
          const candidate = Array.from(document.querySelectorAll(selector)).find(el => el.offsetParent);
          if (!candidate) return {previewFound: false, text: '', fields: []};
          const fields = Array.from(candidate.querySelectorAll('[aria-label], [title], dt, dd')).map(el => ({
            label: el.getAttribute('aria-label') || el.getAttribute('title') || (el.tagName === 'DT' ? (el.textContent || '').trim() : ''),
            value: (el.innerText || el.textContent || '').trim(),
          })).filter(item => item.label || item.value);
          return {previewFound: true, text: (candidate.innerText || candidate.textContent || '').trim(), fields};
        }
        """,
        selector,
    )
    return result if isinstance(result, dict) else {"previewFound": False, "text": "", "fields": []}


def _tab_locator(page: Any, *, element_id: str = "", element_name: str = "") -> Any:
    locator = page.locator(
        f'{selectors.TAB_BAR_TAB}[data-id="{element_id}"]' if element_id else selectors.TAB_BAR_TAB
    )
    return locator if element_id else locator.filter(has_text=element_name)


def element_context_menu(page: Any, *, element_id: str = "", element_name: str = "") -> dict[str, Any]:
    """Open a document-element tab context menu and return its visible items."""
    tab = _tab_locator(page, element_id=element_id, element_name=element_name)
    if tab.count() == 0:
        return {"contextMenuOpened": False, "reason": "document element tab not found"}
    actions.dismiss_stale_context_menu(page)
    tab.first.click(button="right")
    menu = page.locator(selectors.TAB_CONTEXT_MENU).first
    try:
        menu.wait_for(state="visible", timeout=5_000)
    except Exception as exc:  # noqa: BLE001
        return {"contextMenuOpened": False, "reason": f"context menu did not open: {exc}"}
    rows = page.locator(selectors.TAB_CONTEXT_MENU_ITEM)
    items = [
        rows.nth(index).inner_text().strip()
        for index in range(rows.count())
        if rows.nth(index).is_visible() and rows.nth(index).inner_text().strip()
    ]
    return {
        "contextMenuOpened": bool(items),
        "elementId": element_id,
        "elementName": element_name,
        "items": items,
    }


def duplicate_element(
    page: Any,
    *,
    element_id: str = "",
    element_name: str = "",
    new_name: str = "",
) -> dict[str, Any]:
    """Copy one visible document element and verify a new tab appears."""
    before = actions.list_document_tabs(page).get("tabs", [])
    opened = element_context_menu(page, element_id=element_id, element_name=element_name)
    if not opened.get("contextMenuOpened"):
        return {"duplicated": False, **opened}
    item = _exact_text(page.locator(selectors.TAB_CONTEXT_MENU_ITEM), "复制")
    if item is None:
        return {"duplicated": False, **opened, "reason": "exact 复制 menu item not found"}
    item.click()
    dialog = page.locator(".copy-element-dialog, [class*='copy'][class*='dialog']")
    if dialog.count() > 0:
        if new_name:
            field = dialog.first.locator("input")
            if field.count() > 0:
                field.first.fill(new_name)
        accept = dialog.first.locator(selectors.DIALOG_ACCEPT)
        if accept.count() > 0:
            accept.first.click()
    # An ordered list, not a set: a set's iteration order is randomised per
    # process (string hash seed), so the same call would send a different
    # argument list on different runs and make the result unreproducible.
    before_ids = [str(item.get("id")) for item in before if item.get("id")]
    before_id_set = set(before_ids)
    try:
        page.wait_for_function(
            """
            (ids) => Array.from(document.querySelectorAll('.os-tab-bar-tab'))
              .map(el => el.getAttribute('data-id')).filter(Boolean)
              .filter(id => !ids.includes(id)).length === 1
            """,
            arg=list(before_ids),
            timeout=10_000,
        )
    except Exception:
        pass
    after = actions.list_document_tabs(page).get("tabs", [])
    created = [item for item in after if item.get("id") and item.get("id") not in before_id_set]
    source_still_present = any(
        item.get("id") == element_id for item in after
    ) if element_id else any(item.get("name") == element_name for item in after)
    return {
        "duplicated": len(created) == 1 and len(after) == len(before) + 1 and source_still_present,
        "sourceElementId": element_id,
        "sourceElementName": element_name,
        "newTabs": created,
        "sourceStillPresent": source_still_present,
        "beforeCount": len(before),
        "afterCount": len(after),
    }


def notifications_status(page: Any, *, open_drawer: bool = False) -> dict[str, Any]:
    """Read the unread notification count and optionally the visible drawer."""
    root = page.locator(NOTIFICATIONS)
    if root.count() == 0:
        return {"notificationsRead": False, "reason": "notification control not found"}
    text = root.first.inner_text().strip()
    match = re.search(r"\d+", text)
    if open_drawer:
        root.first.click()
        page.wait_for_timeout(200)
    drawer = page.locator(NOTIFICATIONS_DRAWER)
    drawer_text = drawer.first.inner_text().strip() if drawer.count() else ""
    return {
        "notificationsRead": True,
        "unreadCount": int(match.group(0)) if match else 0,
        "drawerOpened": bool(open_drawer and drawer.count()),
        "drawerText": drawer_text,
    }


def share_document(page: Any) -> dict[str, Any]:
    """Open the document share dialog without changing permissions."""
    button = page.locator(SHARE_BUTTON).filter(has_text="共享")
    if button.count() == 0:
        return {"shareOpened": False, "reason": "share button not found"}
    button.first.click()
    dialog = page.locator(SHARE_DIALOG)
    try:
        dialog.first.wait_for(state="visible", timeout=5_000)
    except Exception as exc:  # noqa: BLE001
        return {"shareOpened": False, "reason": f"share dialog did not open: {exc}"}
    text = dialog.first.inner_text().strip()
    return {"shareOpened": True, "dialogText": text[:1000]}


def view_orientation(
    page: Any,
    *,
    orientation: str = "",
    point: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Read the view-cube state or click a requested orientation point."""
    cube = page.locator(VIEW_CUBE)
    if cube.count() == 0:
        return {"orientationRead": False, "orientationSet": False, "reason": "view cube not found"}
    box = cube.first.bounding_box()
    if not box:
        return {"orientationRead": False, "orientationSet": False, "reason": "view cube is not visible"}
    before = cube.first.screenshot()
    before_sha = hashlib.sha256(before).hexdigest()
    if not orientation and point is None:
        return {
            "orientationRead": True,
            "orientationSet": False,
            "orientation": "visual-state",
            "viewCubeSha256": before_sha,
            "bounds": box,
        }
    normalized = {
        "front": (0.50, 0.62),
        "back": (0.50, 0.42),
        "top": (0.50, 0.22),
        "bottom": (0.50, 0.82),
        "left": (0.26, 0.58),
        "right": (0.74, 0.58),
        "iso": (0.70, 0.28),
    }
    if point is not None:
        x = box["x"] + float(point["x"])
        y = box["y"] + float(point["y"])
    elif orientation in normalized:
        px, py = normalized[orientation]
        x = box["x"] + box["width"] * px
        y = box["y"] + box["height"] * py
    else:
        return {"orientationRead": True, "orientationSet": False, "reason": f"unsupported orientation {orientation!r}"}
    page.mouse.click(x, y)
    page.wait_for_timeout(500)
    after = cube.first.screenshot()
    after_sha = hashlib.sha256(after).hexdigest()
    return {
        "orientationRead": True,
        "orientationSet": before_sha != after_sha,
        "orientation": orientation or "custom",
        "beforeSha256": before_sha,
        "afterSha256": after_sha,
        "clickPoint": {"x": x, "y": y},
    }
