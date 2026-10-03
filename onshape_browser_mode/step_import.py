"""Browser-leg STEP import: drive the Import dialog, then PROVE an element landed.

Why this leg exists at all: the REST route for import is `createTranslation`, whose body is
`multipart/form-data` with a binary `file` part, while this repository's REST client sends JSON only --
`onshape_rest_api_mode/step_import.py` therefore refuses a live import with
`multipart_transport_unavailable` instead of pretending. The browser route spends **0 Onshape API
quota**, which is this repository's default preference.

The honest core is the LANDING PROOF. A finished translation is not an imported element, and the
Import dialog's own success UI is not evidence either: the dialog selectors below are UNVERIFIED
candidates (recorded in the pending-live-verification ledger), while the row lists used as proof
(`.os-tab-bar-tab`, `.os-list-item.ns-user-feature`) ARE live-observed. The verdict is therefore
computed from a before/after row read taken through the verified selectors, never from the dialog.

Two import modes need two different proofs:

* ``new-tab`` -- exactly one new tab row must appear (a document-level import creates an element);
* ``into-part-studio`` -- the Part Studio's user-feature rows must gain exactly one row, and the
  verdict is ``imported: true`` only when the caller's ``expect_feature_name`` matches that row.
  Without that match the answer is ``imported: None`` (landing unproven), because a new row proves
  that *something* was added, not that the file landed.

No Playwright import happens here: the module takes a page-like object, so it is testable offline
against fakes and never launches a browser by itself.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from . import selectors

OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs" / "step_imports"

#: The ledger a live session must answer before these selectors may be trusted.
LEDGER = "onshape_docs/verification/pending-live-verification-step-import-2026-10-03.json"
LEDGER_CHECKS = ("I1", "I2", "I3", "I4", "I5")

#: STEP is the handoff format this repository produces and consumes. IGES is deliberately out of
#: scope: nothing here produces it, so accepting it would advertise a path nobody exercises.
_FORMAT_BY_SUFFIX = {".step": "STEP", ".stp": "STEP"}
_MEDIA_TYPE = "model/step"
_ID = re.compile(r"^[A-Za-z0-9_-]+$")

#: The Import entry point is reached by its label, not by a guessed class. MEASURED 2026-10-03: the
#: label carries an ellipsis (`导入…` / `Import…`) and the item is a *hidden* dropdown item, so these
#: are substring needles for a page-JavaScript click, and the locator chain below them is a fallback.
IMPORT_ENTRY_LABELS = ("导入", "Import")

#: Click the import item the way the page exposes it. The item exists in the DOM while its dropdown is
#: closed (`#upload-button` inside `#document-tabs-create-ul`), and Playwright's visibility-gated
#: locators cannot click a hidden element -- measured: every one of them missed on a live page while
#: the item was present, and the same technique is what makes the neighbouring `创建 X` items work
#: (actions.create_document_tab).
_ENTRY_ITEM_JS = """
(labels) => {
  const needles = (labels || []).map((s) => String(s).toLowerCase());
  const norm = (el) => (el.textContent || '').trim().replace(/\\s+/g, ' ');
  const items = Array.from(document.querySelectorAll(
    'a.dropdown-item, .dropdown-item, li.dropdown-item, #upload-button'));
  const item = items.find((el) => {
    const text = norm(el).toLowerCase();
    return needles.some((needle) => needle && text.includes(needle));
  });
  if (!item) {
    return {clicked: false, reason: 'dropdown item not found',
            items: items.map((el) => norm(el).slice(0, 60))};
  }
  item.click();
  return {clicked: true, text: norm(item).slice(0, 60), itemId: item.id || ''};
}
"""

_TAB_ROWS_JS = """
() => Array.from(document.querySelectorAll('.os-tab-bar-tab')).map((row) => ({
  name: ((row.querySelector('.os-tab-name') || row).textContent || '').trim(),
  elementId: row.getAttribute('data-element-id') || row.getAttribute('data-id') || '',
  group: String(row.className || '').indexOf('os-tab-bar-tab-group') !== -1,
}))
"""

_FEATURE_ROWS_JS = """
() => Array.from(document.querySelectorAll('.os-list-item.ns-user-feature')).map(
  (row) => (row.textContent || '').trim()
)
"""


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{label} must be a nonempty opaque identifier")
    return value


_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def _declared_sha256(handoff: str | Path | dict[str, Any] | None) -> dict[str, Any]:
    """Read the digest a handoff addresses, from the handoff itself.

    Accepts either path of the two real shapes: the cross-plane declaration
    (``declaration.identity.sha256``) or the staged browser export manifest's own field
    (``artifact.sha256``). Anything else is refused by name rather than guessed, because a digest
    taken from the wrong place would silently re-address the import to different bytes.
    """
    if handoff is None or (isinstance(handoff, str) and not handoff.strip()):
        # `""` is how every caller in this repo spells "no handoff"; treating it as a path would resolve to
        # `Path("")` == the current directory and produce a confusing FileNotFoundError for `.` instead of
        # the true statement "nothing was declared here".
        return {"declaredSha256": "", "handoffPath": "", "handoffSchema": "", "handoffUnits": "",
                "handoffIdentityRule": ""}
    path_text = ""
    if isinstance(handoff, (str, Path)):
        resolved = Path(handoff)
        if not resolved.is_file():
            raise FileNotFoundError(f"handoff manifest is not a readable file: {resolved}")
        path_text = str(resolved)
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    elif isinstance(handoff, dict):
        payload = handoff
    else:
        raise ValueError("handoff_manifest must be a manifest path or a manifest mapping")
    if not isinstance(payload, dict):
        raise ValueError("handoff manifest must be a JSON object")

    declaration = payload.get("declaration") if isinstance(payload.get("declaration"), dict) else {}
    identity = declaration.get("identity") if isinstance(declaration.get("identity"), dict) else {}
    artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
    declared = identity.get("sha256") or artifact.get("sha256") or payload.get("sha256") or ""
    declared = str(declared)
    if not _DIGEST.fullmatch(declared):
        raise ValueError(
            "the handoff declares no usable sha256: look for declaration.identity.sha256 or "
            "artifact.sha256 — a handoff that cannot name its bytes cannot address an import"
        )
    rule = identity.get("identity_rule") if isinstance(identity.get("identity_rule"), dict) else {}
    return {
        "declaredSha256": declared,
        "handoffPath": path_text,
        "handoffSchema": str(declaration.get("schema") or payload.get("schema") or ""),
        "handoffUnits": str(declaration.get("units") or payload.get("units") or ""),
        "handoffIdentityRule": str(rule.get("version") or ""),
    }


def source_facts(
    path: str | Path,
    *,
    expect_sha256: str = "",
    handoff: str | Path | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Measure the local source file, and check it against a handoff's addressed bytes.

    Read-only; no network, no browser. **Address by digest, resolve by path**: when a digest is declared
    (directly or through a handoff manifest), the file at this path must hash to it, otherwise the import
    is refused *before anything touches the page*. That refusal is the whole point -- re-exporting the same
    geometry produces different bytes (an ISO-10303-21 header timestamp lands in the file), so a path alone
    cannot say which delivery is being imported, and an unchecked path is how the wrong bytes get in.
    """
    resolved = Path(path)
    if not resolved.is_file():
        raise FileNotFoundError(f"import source is not a readable file: {resolved}")
    suffix = resolved.suffix.lower()
    if suffix not in _FORMAT_BY_SUFFIX:
        raise ValueError("import source must be a .step or .stp file (IGES is out of scope for this leg)")
    if expect_sha256 and not _DIGEST.fullmatch(str(expect_sha256)):
        raise ValueError("expect_sha256 must be a lowercase 64-character hex digest")
    addressed = _declared_sha256(handoff)
    declared = str(expect_sha256) or addressed["declaredSha256"]
    payload = resolved.read_bytes()
    actual = hashlib.sha256(payload).hexdigest()
    matches = None if not declared else actual == declared
    if matches is False:
        raise ValueError(
            "the file at this path is not the addressed artifact: "
            f"sha256 {actual} != declared {declared}. Address by digest, resolve by path: re-export the "
            "handoff's delivery or pass the digest of the bytes you actually mean to import"
        )
    return {
        "path": str(resolved),
        "fileName": resolved.name,
        "formatName": _FORMAT_BY_SUFFIX[suffix],
        "mediaType": _MEDIA_TYPE,
        "byteCount": len(payload),
        "sha256": actual,
        # Same rule as the REST planner and the cross-plane manifest: a STEP byte digest is download
        # integrity, not content identity (two real exports of one geometry differ by 34 header bytes).
        "sha256Stable": False,
        "sha256Note": "STEP carries a GUID and a timestamp in its header; this digest is not content identity",
        "addressedBy": "sha256" if declared else "path",
        "expectedSha256": declared or None,
        "matchesExpected": matches,
        "handoff": {key: value for key, value in addressed.items() if value} or None,
    }


def plan_browser_step_import(
    *,
    source_path: str | Path,
    expect_sha256: str = "",
    handoff_manifest: str | Path | dict[str, Any] | None = None,
    mode: str = "new-tab",
    target_tab: str = "",
    document_id: str = "",
    workspace_id: str = "",
    expect_feature_name: str = "",
    timeout_ms: int = 120_000,
) -> dict[str, Any]:
    """The offline half: exactly what a live call would do, and how it would be judged."""
    if mode not in {"new-tab", "into-part-studio"}:
        raise ValueError("mode must be 'new-tab' or 'into-part-studio'")
    if not isinstance(timeout_ms, int) or not 1000 <= timeout_ms <= 600_000:
        raise ValueError("timeout_ms must be an integer between 1000 and 600000")
    if mode == "into-part-studio" and not isinstance(target_tab, str):
        raise ValueError("target_tab must be a string")
    if mode == "into-part-studio" and not target_tab.strip():
        raise ValueError("into-part-studio requires target_tab")
    facts = source_facts(source_path, expect_sha256=expect_sha256, handoff=handoff_manifest)
    for value, label in ((document_id, "document_id"), (workspace_id, "workspace_id")):
        if value:
            _identifier(value, label)
    if mode == "into-part-studio" and not document_id:
        raise ValueError("into-part-studio requires document_id")

    if mode == "new-tab":
        proof = {
            "mode": "new-tab",
            "reads": "the document tab bar (`.os-tab-bar-tab`, live-observed)",
            "rule": ("exactly one new DOCUMENT ELEMENT row must appear after the import; Onshape's internal "
                     "CAD-import bookkeeping row (`CAD 导入`, `.os-tab-bar-tab-group`, id `CADImportBlobs`) "
                     "is not an element and is reported separately; two or more new elements are refused "
                     "as ambiguous"),
            "importedTrueRequires": ("one new row that is not a group row and whose id is a 24-hex document "
                                     "element id"),
        }
    else:
        proof = {
            "mode": "into-part-studio",
            "reads": "the Part Studio user-feature rows (`.os-list-item.ns-user-feature`, live-observed)",
            "rule": ("exactly one new user-feature row must appear AND its text must contain "
                     "expect_feature_name, otherwise the answer is imported=null (landing unproven)"),
            "importedTrueRequires": "one new row whose text contains expect_feature_name",
        }

    return {
        "dryRun": True,
        "operation": "browser-step-import",
        "source": facts,
        "mode": mode,
        "target": {
            "documentId": document_id or None,
            "workspaceId": workspace_id or None,
            "tab": target_tab or None,
            "expectFeatureName": expect_feature_name or None,
        },
        "configuration": {
            "format": "STEP",
            "version": "AP242",
            "unit": "Millimeter",
            "translate": True,
            "destination": "current document" if mode == "new-tab" else f"tab {target_tab}",
        },
        "selectors": {
            # The entry is MEASURED (2026-10-03); the dialog constants below are still candidates.
            "importEntryLabels": list(IMPORT_ENTRY_LABELS),
            "importEntry": {
                "menu": selectors.DOCUMENT_TABS_CREATE_MENU,
                "item": selectors.DOCUMENT_TABS_IMPORT_ITEM,
                "iconAutomation": selectors.DOCUMENT_TABS_IMPORT_AUTOMATION,
                "observedLabel": "导入…",
                "measured": "2026-10-03",
                "how": "hidden dropdown item; clicked in page JavaScript, not by a visible locator",
            },
            "dialog": selectors.IMPORT_DIALOG,
            "fileInput": selectors.IMPORT_FILE_INPUT,
            "submit": selectors.IMPORT_SUBMIT,
            "cancel": selectors.IMPORT_CANCEL,
            "progress": selectors.ASM_PROGRESS,
            # Verified anchors, used as the landing proof rather than as the entry point.
            "tabRow": selectors.TAB_BAR_TAB,
            "tabName": selectors.TAB_NAME,
            "userFeatureRow": selectors.PS_USER_FEATURE,
        },
        "landingProof": proof,
        "timeoutMs": timeout_ms,
        "network": "browser",
        "estimatedApiRequests": 0,
        "maxApiRequests": 0,
        "mutating": True,
        "liveAcceptance": {
            "ledger": LEDGER,
            "checks": list(LEDGER_CHECKS),
            "status": "pending-live-verification",
            "unverifiedSelectors": ["dialog", "fileInput", "submit"],
            "why": ("the Import DIALOG has never been opened by this code on a real page -- the first "
                    "live attempt (2026-10-03) refused at the entry point, which is now measured -- and "
                    "the row lists used as proof are live-observed, so a false success is impossible "
                    "even while the dialog constants are unverified"),
        },
        "refusalRules": [
            "source not a .step/.stp file, or unreadable -> refuse before touching the page",
            "before-read of the proof row list fails -> refuse: landing cannot be judged without it",
            "Import entry never appears -> refuse with the page facts (url + tab names)",
            "file input cannot be attached -> refuse with the page facts (a dialog that opens but has no "
            "file input is a different failure from a dialog that never opens)",
            "after-read fails -> imported=False with reason element_read_failed, never a success",
            "the internal CAD-import bookkeeping row appears alone -> imported=False with reason "
            "element_not_yet_visible; that row is not the imported geometry, and the wait continues",
            "two or more new document elements -> refused as ambiguous, never guessed",
            "into-part-studio without a matching expect_feature_name -> imported=None, not True",
        ],
    }


def _read_rows(page: Any, script: str) -> dict[str, Any]:
    """One read of a verified row list. A failure is reported, never swallowed."""
    try:
        rows = page.evaluate(script)
    except Exception as error:  # pragma: no cover - exercised through the fakes
        return {"ok": False, "error": f"{type(error).__name__}: {error}", "rows": []}
    if not isinstance(rows, list):
        return {"ok": False, "error": "row read did not return a list", "rows": []}
    return {"ok": True, "error": None, "rows": rows}


def _page_facts(page: Any, rows: list[Any] | None = None) -> dict[str, Any]:
    """The facts a selector miss must be reported with.

    When the caller already read the row list, reuse it: a second read would both waste a page
    round trip and report a state the verdict was not computed from.
    """
    try:
        url = getattr(page, "url", "")
    except Exception:  # pragma: no cover - defensive
        url = ""
    if rows is None:
        tabs = _read_rows(page, _TAB_ROWS_JS)
        rows, error = tabs["rows"], tabs["error"]
    else:
        error = None
    names = [row.get("name") if isinstance(row, dict) else row for row in rows]
    return {"url": url, "tabNames": names, "tabReadError": error}


def _click_text_candidate(page: Any, labels: tuple[str, ...]) -> dict[str, Any]:
    """Click the first present label. Playwright's own locator API, nothing invented."""
    tried: list[str] = []
    for label in labels:
        for strategy in ("get_by_text", "locator"):
            try:
                if strategy == "get_by_text":
                    target = page.get_by_text(label, exact=False)
                else:
                    target = page.locator(f"text={label}")
                target = target.first
                target.wait_for(state="visible", timeout=2000)
                target.click()
                return {"clicked": True, "label": label, "strategy": strategy, "tried": tried}
            except Exception:
                tried.append(f"{strategy}:{label}")
    return {"clicked": False, "label": None, "strategy": None, "tried": tried}


def _click_import_entry(page: Any, labels: tuple[str, ...] = IMPORT_ENTRY_LABELS) -> dict[str, Any]:
    """Click the Import entry at its measured address, then fall back to its label.

    Measured 2026-10-03: the entry is a *hidden* dropdown item (``#upload-button`` with the label
    ``导入…``), so the visibility-gated locator chain cannot reach it. The page-JavaScript click runs
    first; the locator chain stays as recorded evidence of what was tried, and a miss is never
    retried blindly.
    """
    tried: list[str] = []
    try:
        outcome = page.evaluate(_ENTRY_ITEM_JS, list(labels))
        if isinstance(outcome, dict) and outcome.get("clicked"):
            return {
                "clicked": True,
                "label": outcome.get("text", ""),
                "strategy": "page_js_dropdown_item",
                "itemId": outcome.get("itemId", ""),
                "candidates": outcome.get("items", []),
                "tried": tried,
            }
        tried.append("page_js_dropdown_item")
    except Exception as error:  # noqa: BLE001 - a failed click is a refusal, not a crash
        tried.append(f"page_js_dropdown_item raised {type(error).__name__}")
    fallback = _click_text_candidate(page, labels)
    return {**fallback, "tried": tried + list(fallback.get("tried", []))}


def _attach_file(page: Any, path: Path) -> dict[str, Any]:
    for selector in (selectors.IMPORT_FILE_INPUT, "input[type=file]"):
        try:
            target = page.locator(selector).first
            target.set_input_files(str(path))
            return {"attached": True, "selector": selector, "error": None}
        except Exception as error:
            last = f"{type(error).__name__}: {error}"
    return {"attached": False, "selector": None, "error": last}


def _click_submit(page: Any) -> dict[str, Any]:
    for selector in (selectors.IMPORT_SUBMIT, selectors.IMPORT_DIALOG + " button.btn-primary[type='submit']"):
        try:
            target = page.locator(selector).first
            target.click()
            return {"submitted": True, "selector": selector}
        except Exception:
            continue
    return {"submitted": False, "selector": None}


def _poll_for_change(
    page: Any,
    script: str,
    before: dict[str, Any],
    *,
    timeout_ms: int,
    interval_ms: int,
    pause: Any,
    now: Any,
    require_element: bool = False,
) -> dict[str, Any]:
    """Bounded wait for the proof list to change. Terminates on the injected clock.

    With ``require_element`` (mode new-tab) an internal bookkeeping row appearing alone does NOT end
    the wait: the translated element is what the proof needs, so the loop keeps polling until it
    appears or the budget runs out.
    """
    deadline = now() + (timeout_ms / 1000.0)
    reads = 0
    last = before
    while now() < deadline:
        pause(interval_ms)
        last = _read_rows(page, script)
        reads += 1
        if not last["ok"]:
            continue
        if len(last["rows"]) == len(before["rows"]):
            continue
        if require_element and not any(
            _is_document_element(row) for row in _new_rows(before["rows"], last["rows"])
        ):
            continue
        return {"changed": True, "reads": reads, "after": last}
    return {"changed": False, "reads": reads, "after": last}


def _new_rows(before: list[Any], after: list[Any]) -> list[Any]:
    if before and isinstance(before[0], dict) and isinstance(after[0], dict):
        seen = {row.get("elementId") or row.get("name") for row in before}
        return [row for row in after if (row.get("elementId") or row.get("name")) not in seen]
    return [row for row in after if row not in before]


#: A real document element's tab row carries a 24-hex element id; the CAD-import bookkeeping row does
#: not (measured 2026-10-03: its `data-id` is literally `CADImportBlobs` and it also carries the
#: `os-tab-bar-tab-group` class).
_ELEMENT_ID = re.compile(r"^[0-9a-f]{24}$")


def _is_document_element(row: Any) -> bool:
    """Is this tab row an actual document element, rather than Onshape's import bookkeeping row?

    MEASURED 2026-10-03: importing a STEP file adds TWO tab rows. The internal `CAD 导入` row
    (`.os-tab-bar-tab-group`, ``data-id="CADImportBlobs"``) appears FIRST -- as soon as the file is
    uploaded, before the translation exists -- and the translated element (`model`, a 24-hex id)
    follows. Counting *any* new row therefore reported the bookkeeping row as the landed element.
    A row is an element only when it is not a group row and carries an element-shaped id: this proof
    prefers a false negative (refuse and keep waiting) over attributing a bookkeeping row.
    """
    if not isinstance(row, dict):
        return False
    if row.get("group"):
        return False
    return bool(_ELEMENT_ID.match(str(row.get("elementId") or "")))


def _split_new_rows(new: list[Any]) -> tuple[list[Any], list[Any]]:
    elements = [row for row in new if _is_document_element(row)]
    internal = [row for row in new if not _is_document_element(row)]
    return elements, internal


def _verdict(mode: str, before: dict[str, Any], polled: dict[str, Any], expect_feature_name: str) -> dict[str, Any]:
    if not polled["after"]["ok"]:
        return {"imported": False, "reason": "element_read_failed", "detail": polled["after"]["error"],
                "translationCompleted": "unknown"}
    new = _new_rows(before["rows"], polled["after"]["rows"])
    elements, internal = _split_new_rows(new) if mode == "new-tab" else (new, [])
    if not new:
        return {"imported": False, "reason": "no_new_element",
                "detail": ("the proof list did not change within the budget; the translation may still be "
                           "running, which is not the same as a failed import"),
                "translationCompleted": "unknown", "newRows": []}
    if not elements and internal:
        return {"imported": False, "reason": "element_not_yet_visible",
                "detail": ("the import was accepted -- Onshape's internal CAD-import bookkeeping row "
                           f"{internal[0].get('name') if isinstance(internal[0], dict) else internal[0]!r} "
                           "appeared -- but no translated document element is visible yet; a slow "
                           "translation is not a failed import, and the bookkeeping row is not the "
                           "imported geometry"),
                "translationCompleted": "unknown", "newRows": [], "internalRows": internal}
    if len(elements) > 1:
        return {"imported": False, "reason": "ambiguous_new_elements",
                "detail": "more than one document element appeared; refusing to guess which one is this import",
                "translationCompleted": "unknown", "newRows": elements, "internalRows": internal}
    if mode == "new-tab":
        row = elements[0]
        if not (isinstance(row, dict) and (row.get("name") or row.get("elementId"))):
            return {"imported": False, "reason": "unidentified_new_element",
                    "detail": "the new document-element row carries neither a name nor an element id",
                    "translationCompleted": "unknown", "newRows": elements, "internalRows": internal}
        return {"imported": True, "reason": "new_tab_landed", "newElement": row,
                "translationCompleted": "assumed", "newRows": elements, "internalRows": internal}
    # into-part-studio: a new feature row proves *something* was added, not that this file landed.
    text = str(new[0])
    if not expect_feature_name:
        return {"imported": None, "reason": "landing_unproven",
                "detail": "a new feature row appeared, but no expect_feature_name was supplied to match it",
                "translationCompleted": "unknown", "newRows": elements}
    if expect_feature_name.lower() in text.lower():
        return {"imported": True, "reason": "feature_row_matched", "newElement": {"name": text},
                "translationCompleted": "assumed", "newRows": elements}
    return {"imported": False, "reason": "feature_row_mismatch",
            "detail": f"the new row {text!r} does not contain {expect_feature_name!r}",
            "translationCompleted": "unknown", "newRows": elements}


def import_browser_step(
    page: Any,
    *,
    source_path: str | Path,
    expect_sha256: str = "",
    handoff_manifest: str | Path | dict[str, Any] | None = None,
    mode: str = "new-tab",
    target_tab: str = "",
    document_id: str = "",
    workspace_id: str = "",
    expect_feature_name: str = "",
    timeout_ms: int = 120_000,
    pause: Any = None,
    now: Any = None,
) -> dict[str, Any]:
    """The live half. Every exit states what was and was not proven."""
    import time

    plan = plan_browser_step_import(
        source_path=source_path,
        expect_sha256=expect_sha256,
        handoff_manifest=handoff_manifest,
        mode=mode,
        target_tab=target_tab,
        document_id=document_id,
        workspace_id=workspace_id,
        expect_feature_name=expect_feature_name,
        timeout_ms=timeout_ms,
    )
    pause = pause or (lambda milliseconds: time.sleep(milliseconds / 1000.0))
    now = now or time.monotonic

    script = _TAB_ROWS_JS if mode == "new-tab" else _FEATURE_ROWS_JS
    before = _read_rows(page, script)
    facts = _page_facts(page, rows=before["rows"] if before["ok"] else None)
    result: dict[str, Any] = {
        "imported": False,
        "reason": None,
        "mode": mode,
        "source": plan["source"],
        "target": plan["target"],
        "before": before,
        "after": None,
        "newRows": [],
        "pageFacts": facts,
        "configuration": plan["configuration"],
        "landingProof": plan["landingProof"],
        "selectorsUsed": plan["selectors"],
        "unverifiedSelectors": plan["liveAcceptance"]["unverifiedSelectors"],
        "network": "browser",
        "estimatedApiRequests": 0,
        "spentApiRequests": 0,
        "spentQuota": 0,
    }
    if not before["ok"]:
        result["reason"] = "before_read_failed"
        result["detail"] = ("the proof row list could not be read before the import, so landing cannot "
                            f"be judged: {before['error']}")
        return result

    entry = _click_import_entry(page, IMPORT_ENTRY_LABELS)
    result["importEntry"] = entry
    if not entry["clicked"]:
        result["reason"] = "import_entry_missing"
        result["detail"] = f"no Import entry matched {entry['tried']}"
        return result

    attached = _attach_file(page, Path(plan["source"]["path"]))
    result["fileAttach"] = attached
    if not attached["attached"]:
        result["reason"] = "file_input_missing"
        result["detail"] = attached["error"]
        return result

    result["submit"] = _click_submit(page)
    polled = _poll_for_change(
        page, script, before, timeout_ms=timeout_ms, interval_ms=500, pause=pause, now=now,
        require_element=(mode == "new-tab"),
    )
    result["polls"] = {"reads": polled["reads"], "changed": polled["changed"]}
    result["after"] = polled["after"]
    verdict = _verdict(mode, before, polled, expect_feature_name)
    result.update(verdict)
    return result


def register_imported_browser_step(
    *,
    import_id: str,
    result: dict[str, Any],
    document_id: str,
    workspace_id: str,
    output_root: Path = OUTPUT_ROOT,
) -> dict[str, Any]:
    """Record a live import as a reusable manifest, including what was NOT proven."""
    iid = _identifier(import_id, "import_id")
    if not result.get("imported"):
        raise ValueError("only an import answered imported=True can be registered")
    for value, label in ((document_id, "document_id"), (workspace_id, "workspace_id")):
        _identifier(value, label)
    destination = output_root.resolve() / iid
    manifest_path = destination / "import-manifest.json"
    if manifest_path.exists():
        raise ValueError("import manifest already exists")
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schemaVersion": 1,
        "artifactType": "imported-browser-step",
        "importId": iid,
        "target": {"documentId": document_id, "workspaceId": workspace_id, **result.get("target", {})},
        "source": result.get("source"),
        "newElement": result.get("newElement"),
        "verdict": {"imported": result.get("imported"), "reason": result.get("reason"),
                    "translationCompleted": result.get("translationCompleted")},
        "landingProof": result.get("landingProof"),
        "pageFacts": result.get("pageFacts"),
        "provenance": {
            "route": "browser",
            "spentQuota": 0,
            "unverifiedSelectors": result.get("unverifiedSelectors", []),
            "ledger": LEDGER,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"registered": True, "importId": iid, "manifestPath": str(manifest_path), "manifest": manifest}
