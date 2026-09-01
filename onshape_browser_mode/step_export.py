from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from onshape_browser_mode import selectors
from onshape_browser_mode.fdm_adapter import step_artifact_from_browser_export


OUTPUT_ROOT = Path(__file__).resolve().parent / "outputs" / "step_exports"
_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _identifier(value: str, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"{label} must be a nonempty opaque identifier")
    return value


def plan_browser_step_export(
    *,
    source_tab: str,
    export_id: str,
    output_root: Path = OUTPUT_ROOT,
) -> dict[str, Any]:
    if not isinstance(source_tab, str) or not source_tab.strip():
        raise ValueError("source_tab is required")
    eid = _identifier(export_id, "export_id")
    destination = output_root.resolve() / eid
    return {
        "dryRun": True,
        "operation": "browser-part-studio-step-export",
        "sourceTab": source_tab,
        "exportId": eid,
        "destination": str(destination),
        "destinationAvailable": not destination.exists(),
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
) -> dict[str, Any]:
    plan = plan_browser_step_export(
        source_tab=source_tab,
        export_id=export_id,
        output_root=output_root,
    )
    if not plan["destinationAvailable"]:
        raise ValueError("browser STEP staging destination already exists")

    tab = page.locator(selectors.TAB_BAR_TAB).filter(has_text=source_tab).first
    if tab.count() != 1:
        raise ValueError(f"Part Studio tab not found uniquely: {source_tab!r}")
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

    staging = output_root.resolve() / export_id
    staging.mkdir(parents=True)
    destination = staging / "model.step"
    download.save_as(str(destination))
    dialog.wait_for(state="hidden", timeout=30_000)
    registered = register_downloaded_browser_step(
        export_id=export_id,
        file_name=destination.name,
        page_url=page.url,
        document_id=document_id,
        workspace_id=workspace_id,
        element_id=element_id,
        output_root=output_root,
    )
    return {
        "exported": True,
        "browserActionPerformed": True,
        "sourceTab": source_tab,
        "suggestedFilename": suggested,
        **registered,
        "configuration": plan["configuration"],
        "apiRequests": 0,
        "bambuIncluded": False,
    }
