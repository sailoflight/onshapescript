from __future__ import annotations

import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

from fdm_analysis.contracts import file_sha256

from onshape_browser_mode import selectors
from onshape_browser_mode.fdm_adapter import step_artifact_from_browser_export


OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs" / "step_exports"
_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{label} must be a nonempty opaque identifier")
    return value


def _close_internal_download_pages(page: Any) -> int:
    """Request a close for browser-internal downloads pages this download left open.

    Edge opens ``edge://downloads-hub/`` as its own target once a download is
    saved. A page-level probe on that target times out and keeps the shared page
    channel busy for every later tool call, so the export must not leave one
    behind. Guarded and zero-quota: a missing context or a native failure is not
    an export failure.

    Returns the number of ACCEPTED close requests, not of pages that disappeared;
    ``_internal_pages_remaining`` reports the observable half of that question.
    """
    try:
        pages = list(page.context.pages or [])
    except Exception:
        return 0
    from onshape_browser_mode.session import _close_browser_internal_pages

    try:
        return _close_browser_internal_pages(pages)
    except Exception:
        return 0


def _internal_pages_remaining() -> int | None:
    """Browser-internal page targets still listed after a close was requested.

    ``None`` means the count was not determined: the browser's DevTools endpoint
    could not be reached (or the caller had nothing to re-check). Guarded:
    probing must never fail an export.
    """
    from onshape_browser_mode.session import _browser_internal_pages_remaining

    try:
        return _browser_internal_pages_remaining()
    except Exception:
        return None


def _page_alive(page: Any) -> bool:
    """Whether the injected page still answers a liveness probe.

    Only the page object is probed. ``session.health()`` is deliberately NOT used
    here: it cannot distinguish a dead browser from a live child that simply holds
    no page, so it would report "browser_not_running" for a perfectly good export
    context. A page object with no probe at all is reported alive because it was
    handed to this call; assuming death would add a false warning to every result.
    A probe that raises (Playwright raises ``TargetClosedError`` on a dead target)
    means the page is gone.
    """
    try:
        probe = getattr(page, "is_closed", None)
        if not callable(probe):
            return True
        return not bool(probe())
    except Exception:
        return False


def _file_present(path: Path) -> bool:
    """True only for a non-empty regular file; never raises."""
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _staging_inventory(staging: Path) -> list[dict[str, Any]]:
    """Every regular file currently under one staging directory, with its hash.

    Read-only and guarded: this mostly runs on the failure path, where it must
    describe what survived instead of replacing the real error with an inventory
    error, so an unreadable entry is skipped rather than raised.
    """
    if not staging.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(staging.rglob("*")):
        if not path.is_file():
            continue
        try:
            size = path.stat().st_size
            sha256 = file_sha256(path)
        except OSError:
            continue
        entries.append(
            {
                "path": str(path),
                "fileName": path.name,
                "bytes": size,
                "sha256": sha256,
            }
        )
    return entries


def _complete_staged_export(staging: Path, export_id: str) -> dict[str, Any] | None:
    """The manifest of an already-COMPLETE staged export, or ``None``.

    "Complete" means the manifest exists, names this export, and its artifact
    stays inside staging, is a non-empty file, and still hashes to the digest the
    manifest recorded. An incomplete staging (most importantly: an artifact saved
    without its manifest) is NOT reusable and returns ``None``.
    """
    manifest_path = staging / "step-manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict) or payload.get("exportId") != export_id:
        return None
    artifact = payload.get("artifact")
    if not isinstance(artifact, dict):
        return None
    relative = PurePosixPath(str(artifact.get("path", "")))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        return None
    path = staging.joinpath(*relative.parts)
    if not _file_present(path):
        return None
    try:
        if file_sha256(path) != artifact.get("sha256"):
            return None
    except OSError:
        return None
    return payload


def _manifest_matches_request(
    manifest: dict[str, Any],
    *,
    document_id: str,
    workspace_id: str,
    element_id: str,
) -> bool:
    """True when a staged manifest's provenance IS the requested target.

    Reuse (issue #8) answers from an artifact that an EARLIER call exported, so
    it must prove that artifact belongs to the document/workspace/element being
    asked about. Without this check a caller passing a mismatched ``element_id``
    would receive another document's STEP and be told the export succeeded.

    A manifest that records nothing comparable is NOT a match: reuse is allowed
    only on positive evidence, never by default. Recorded provenance lives at
    ``artifact.source.identifiers`` (see
    :func:`onshape_browser_mode.fdm_adapter.step_artifact_from_browser_export`).
    """
    artifact = manifest.get("artifact")
    if not isinstance(artifact, dict):
        return False
    source = artifact.get("source")
    if not isinstance(source, dict):
        return False
    recorded = source.get("identifiers")
    if not isinstance(recorded, dict):
        return False
    requested = {
        "documentId": document_id,
        "workspaceId": workspace_id,
        "elementId": element_id,
    }
    for key, value in requested.items():
        if not isinstance(value, str) or not value.strip():
            return False
        if recorded.get(key) != value:
            return False
    return True


def _clear_staging(staging: Path, output_root: Path) -> None:
    """Remove ONLY ``output_root.resolve()/<export_id>`` and nothing outside it.

    The caller asked for ``overwrite`` after a PARTIAL staging; a complete one is
    reused before this function is ever reached. The parent/root re-check keeps a
    future refactor from turning overwrite into an arbitrary recursive delete.
    """
    root = output_root.resolve()
    target = staging.resolve()
    if target == root or target.parent != root:
        raise ValueError("refusing to clear a staging path outside the export output root")
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()


def _recovery_actions() -> list[dict[str, str]]:
    """Executable next steps for a structured STEP export failure.

    NOTE the deliberate shape divergence: ``transactions.py`` reports one
    machine-readable recovery OBJECT (or ``None``) for a single failed workflow
    step. A failed browser export has no single next step -- reusing what reached
    disk, retrying under a new id, retrying with ``overwrite``, asking an operator
    to enable the REST leg, and hand-exporting are all valid and cost differently
    -- so this reports a LIST of candidate actions. Requested by issue #8; do not
    "simplify" it back to one dict without checking the callers.
    """
    return [
        {"action": "retry_new_export_id"},
        {"action": "retry_same_export_id", "requires": "overwrite=true"},
        {"action": "browser_build_geometry_package", "requires": "stagingComplete"},
        {"action": "enable_live_api", "requires": "operator"},
        {"action": "human_export_dialog"},
    ]


def plan_browser_step_export(
    *,
    source_tab: str,
    export_id: str,
    output_root: Path = OUTPUT_ROOT,
    overwrite: bool = False,
    document_id: str | None = None,
    workspace_id: str | None = None,
    element_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(source_tab, str) or not source_tab.strip():
        raise ValueError("source_tab is required")
    eid = _identifier(export_id, "export_id")
    destination = output_root.resolve() / eid
    manifest = _complete_staged_export(destination, eid)
    # The plan must not advertise a reuse the real call will refuse. Provenance
    # can only be judged when the caller supplies the target ids; without them
    # the plan reports the artifact-level answer and says so.
    provenance_known = all(
        isinstance(value, str) and value.strip()
        for value in (document_id, workspace_id, element_id)
    )
    provenance_matches = provenance_known and manifest is not None and _manifest_matches_request(
        manifest,
        document_id=document_id or "",
        workspace_id=workspace_id or "",
        element_id=element_id or "",
    )
    already_staged = manifest is not None and (not provenance_known or provenance_matches)
    return {
        "dryRun": True,
        "operation": "browser-part-studio-step-export",
        "sourceTab": source_tab,
        "exportId": eid,
        "destination": str(destination),
        # A complete staged export is reusable as-is, and overwrite makes partial
        # staging replaceable, so both count as available for this plan.
        "destinationAvailable": not destination.exists() or bool(overwrite) or already_staged,
        "overwrite": bool(overwrite),
        "stagingComplete": already_staged,
        "alreadyStaged": already_staged,
        "stagingProvenanceChecked": provenance_known,
        "stagingProvenanceMatches": provenance_matches if provenance_known else None,
        "configuration": {
            "format": "STEP",
            "version": "AP242",
            "customUnits": True,
            "unit": "Millimeter",
            "option": "下载",
            "individualFiles": False,
            "includeHiddenEntities": False,
        },
        "selectors": {
            "tab": selectors.TAB_BAR_TAB,
            "contextMenuItem": selectors.TAB_CONTEXT_MENU_ITEM,
            "dialog": selectors.EXPORT_DIALOG,
            "filename": selectors.EXPORT_FILENAME,
            "format": selectors.EXPORT_FORMAT,
            "stepVersion": selectors.EXPORT_STEP_VERSION,
            "latestVersion": selectors.EXPORT_LATEST_VERSION,
            "customUnits": selectors.EXPORT_CUSTOM_STEP_UNITS,
            "stepUnits": selectors.EXPORT_STEP_UNITS,
            "options": selectors.EXPORT_OPTIONS,
            "individualFiles": selectors.EXPORT_INDIVIDUAL_FILES,
            "hiddenEntities": selectors.EXPORT_HIDDEN_ENTITIES,
            "submit": selectors.EXPORT_SUBMIT,
        },
        "network": "browser",
        "estimatedApiRequests": 0,
        "bambuIncluded": False,
    }


def register_downloaded_browser_step(
    *,
    export_id: str,
    file_name: str,
    page_url: str,
    document_id: str,
    workspace_id: str,
    element_id: str,
    output_root: Path = OUTPUT_ROOT,
) -> dict[str, Any]:
    eid = _identifier(export_id, "export_id")
    if not isinstance(file_name, str) or not re.fullmatch(r"[A-Za-z0-9._-]+\.(?:step|stp)", file_name, re.I):
        raise ValueError("file_name must be a simple .step or .stp filename")
    staging = output_root.resolve() / eid
    manifest_path = staging / "step-manifest.json"
    if manifest_path.exists():
        raise ValueError("browser STEP staging manifest already exists")
    artifact = step_artifact_from_browser_export(
        staging / file_name,
        page_url=page_url,
        document_id=document_id,
        workspace_id=workspace_id,
        element_id=element_id,
        units="mm",
    )
    payload = artifact.as_dict()
    manifest = {
        "schemaVersion": 1,
        "artifactType": "canonical-step",
        "exportId": eid,
        "artifact": {
            **payload,
            "path": file_name,
            "byteCount": artifact.path.stat().st_size,
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "registered": True,
        "exportId": eid,
        "step": payload,
        "stepManifestPath": str(manifest_path),
    }


def export_browser_step(
    page: Any,
    *,
    source_tab: str,
    export_id: str,
    document_id: str,
    workspace_id: str,
    element_id: str,
    output_root: Path = OUTPUT_ROOT,
    timeout_ms: int = 120_000,
    overwrite: bool = False,
) -> dict[str, Any]:
    plan = plan_browser_step_export(
        source_tab=source_tab,
        export_id=export_id,
        output_root=output_root,
        overwrite=overwrite,
        document_id=document_id,
        workspace_id=workspace_id,
        element_id=element_id,
    )
    eid = plan["exportId"]
    staging = output_root.resolve() / eid
    alive_before = _page_alive(page)

    # Issue #8: an attempt that saved the STEP and then lost the dialog left a
    # COMPLETE artifact on disk behind a failure. Reuse it and report success
    # instead of re-exporting (or refusing). ``overwrite`` does not force a
    # re-export either -- only a new export_id can do that; overwrite exists to
    # clear PARTIAL staging below.
    #
    # Reuse is conditional on PROVENANCE, not just on the artifact being intact:
    # the caller's document/workspace/element must be the ones the manifest
    # recorded. A mismatch is a pre-flight refusal, or an explicit overwrite --
    # never a success that silently answers with another document's STEP.
    overwrite_applied = False
    manifest = _complete_staged_export(staging, eid)
    if manifest is not None and not _manifest_matches_request(
        manifest,
        document_id=document_id,
        workspace_id=workspace_id,
        element_id=element_id,
    ):
        if not overwrite:
            raise ValueError(
                f"browser STEP staging for export_id {eid!r} holds a STEP exported "
                "from a different document/workspace/element; pass a new export_id, "
                "or overwrite=true to replace it"
            )
        _clear_staging(staging, output_root)
        overwrite_applied = True
        manifest = None
    if manifest is not None:
        artifact = manifest.get("artifact")
        artifact = artifact if isinstance(artifact, dict) else {}
        return {
            "exported": True,
            # No page was touched: this call only re-reported an earlier export.
            "browserActionPerformed": False,
            "sourceTab": source_tab,
            "suggestedFilename": PurePosixPath(str(artifact.get("path", ""))).name,
            "browserInternalPagesCloseRequested": 0,
            "browserInternalPagesRemaining": None,
            "registered": True,
            "exportId": eid,
            "step": artifact,
            "stepManifestPath": str(staging / "step-manifest.json"),
            "alreadyStaged": True,
            "overwriteApplied": False,
            "stagedArtifacts": _staging_inventory(staging),
            "browserAliveBefore": alive_before,
            "browserAliveAfter": _page_alive(page),
            "configuration": plan["configuration"],
            "apiRequests": 0,
            "bambuIncluded": False,
        }

    if staging.exists():
        # Partial staging -- most importantly an artifact whose manifest never
        # got written (issue #8) -- stays a hard pre-flight refusal unless the
        # caller explicitly asked for cleanup.
        if not overwrite:
            raise ValueError("browser STEP staging destination already exists")
        _clear_staging(staging, output_root)
        overwrite_applied = True

    # The tab is selected by EXACT visible name and clicked through its own
    # data-id. `.filter(has_text=...).first` matched substrings, and `.first`
    # defeated the count check below it, so a name that prefixes another tab's
    # name selected the wrong tab and failed later with a URL mismatch.
    from onshape_browser_mode.actions import resolve_exact_tab

    resolved = resolve_exact_tab(page, source_tab)
    if resolved["matchCount"] != 1:
        raise ValueError(
            f"Part Studio tab {source_tab!r} must match exactly one visible tab name "
            f"(exact match): matchCount={resolved['matchCount']}, "
            f"containingName={resolved['contains']}, tabs={resolved['names']}"
        )
    if not resolved["id"]:
        raise ValueError(f"the matched Part Studio tab {source_tab!r} carries no data-id")
    target_id = resolved["id"]
    tab = page.locator(f'{selectors.TAB_BAR_TAB}[data-id="{target_id}"]')
    tab.click()
    from onshape_browser_mode.actions import parse_document_url

    observed = parse_document_url(page.url)
    expected = {
        "documentId": document_id,
        "workspaceId": workspace_id,
        "elementId": element_id,
    }
    if any(observed.get(key) != value for key, value in expected.items()):
        raise RuntimeError("active Part Studio URL does not match requested document/workspace/element IDs")
    tab.click(button="right")
    export_item = page.locator(selectors.TAB_CONTEXT_MENU_ITEM).filter(
        has_text=selectors.TAB_CONTEXT_MENU_TEXT["export"],
    ).first
    if export_item.count() != 1:
        raise RuntimeError("Part Studio export context action is unavailable")
    export_item.click()

    dialog = page.locator(selectors.EXPORT_DIALOG).first
    dialog.wait_for(state="visible", timeout=30_000)
    page.locator(selectors.EXPORT_FILENAME).fill(export_id)
    page.locator(selectors.EXPORT_FORMAT).select_option(label="STEP")

    latest = page.locator(selectors.EXPORT_LATEST_VERSION)
    if latest.is_checked():
        latest.click()
    page.locator(selectors.EXPORT_STEP_VERSION).select_option(label="AP242")

    custom_units = page.locator(selectors.EXPORT_CUSTOM_STEP_UNITS)
    if not custom_units.is_checked():
        custom_units.click()
    page.locator(selectors.EXPORT_STEP_UNITS).select_option(label="Millimeter")
    page.locator(selectors.EXPORT_OPTIONS).select_option(label="下载")

    individual = page.locator(selectors.EXPORT_INDIVIDUAL_FILES)
    if individual.is_checked():
        individual.click()
    hidden = page.locator(selectors.EXPORT_HIDDEN_ENTITIES)
    if hidden.is_checked():
        hidden.click()

    with page.expect_download(timeout=timeout_ms) as pending:
        page.locator(selectors.EXPORT_SUBMIT).click()
    download = pending.value
    suggested = str(download.suggested_filename)
    if Path(suggested).suffix.lower() not in {".step", ".stp"}:
        raise RuntimeError(f"browser export returned a non-STEP download: {suggested}")
    failure = download.failure()
    if failure:
        raise RuntimeError(f"browser STEP download failed: {failure}")

    destination = staging / "model.step"
    internal_pages_close_requested = 0
    internal_pages_remaining: int | None = None

    def _register() -> dict[str, Any]:
        return register_downloaded_browser_step(
            export_id=eid,
            file_name=destination.name,
            page_url=page.url,
            document_id=document_id,
            workspace_id=workspace_id,
            element_id=element_id,
            output_root=output_root,
        )

    # Only the save/dialog/register tail is structured-failure territory. The
    # tab/URL/dialog-config and non-STEP/download.failure pre-flight raises above
    # stay raises: they leave nothing on disk and existing callers rely on them.
    phase = "stage_artifact"
    try:
        staging.mkdir(parents=True, exist_ok=True)
        phase = "save_download"
        download.save_as(str(destination))
        if not _file_present(destination):
            raise RuntimeError(f"browser STEP download saved no artifact: {destination}")
        phase = "close_internal_download_pages"
        internal_pages_close_requested = _close_internal_download_pages(page)
        # Only a requested close needs re-checking. With nothing requested the count is
        # not this export's question, and probing anyway would add an unrelated
        # DevTools call (and an environment dependency) to every export.
        internal_pages_remaining = (
            _internal_pages_remaining() if internal_pages_close_requested else None
        )
        phase = "wait_for_dialog_hidden"
        dialog.wait_for(state="hidden", timeout=30_000)
        phase = "register_manifest"
        registered = _register()
    except Exception as error:
        # A STEP already written to disk is a fact, not a failed download. Give it
        # its manifest when provenance is still readable so the staged artifact can
        # be consumed (``browser_build_geometry_package`` needs the manifest), and
        # never mask the original error with a bookkeeping one.
        if _file_present(destination):
            try:
                _register()
            except Exception:
                pass
        complete = _complete_staged_export(staging, eid) is not None
        return {
            "exported": False,
            "browserActionPerformed": True,
            "sourceTab": source_tab,
            "exportId": eid,
            "suggestedFilename": suggested,
            # ``phase`` names where it broke: a failure at "wait_for_dialog_hidden"
            # with ``stagingComplete: true`` is NOT a download failure -- the STEP is
            # on disk and reusable.
            "failure": {
                "phase": phase,
                "error": f"{type(error).__name__}: {error}",
            },
            "stagedArtifacts": _staging_inventory(staging),
            "stagingComplete": complete,
            # Whether this export_id now resolves to a complete, reusable staging.
            "alreadyStaged": complete,
            "browserAliveBefore": alive_before,
            "browserAliveAfter": _page_alive(page),
            "recovery": _recovery_actions(),
            "browserInternalPagesCloseRequested": internal_pages_close_requested,
            "browserInternalPagesRemaining": internal_pages_remaining,
            "configuration": plan["configuration"],
            "apiRequests": 0,
            "bambuIncluded": False,
        }
    return {
        "exported": True,
        "browserActionPerformed": True,
        "sourceTab": source_tab,
        "suggestedFilename": suggested,
        # An accepted close is not proof of removal (measured live 2026-09-20:
        # Edge keeps edge://downloads-hub/ listed as "Target is closing"), so the
        # two facts are reported separately instead of one "closed" count.
        "browserInternalPagesCloseRequested": internal_pages_close_requested,
        "browserInternalPagesRemaining": internal_pages_remaining,
        **registered,
        "alreadyStaged": False,
        "overwriteApplied": overwrite_applied,
        "stagedArtifacts": _staging_inventory(staging),
        "browserAliveBefore": alive_before,
        "browserAliveAfter": _page_alive(page),
        "configuration": plan["configuration"],
        "apiRequests": 0,
        "bambuIncluded": False,
    }
