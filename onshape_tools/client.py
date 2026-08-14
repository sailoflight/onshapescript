#!/usr/bin/env python3
"""Small authenticated Onshape client used by the local helper scripts."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_PATH = Path(os.environ.get(
    "ONSHAPE_CREDENTIALS",
    ROOT / "onshape-credentials.json",
))
STATE_PATH = Path(os.environ.get(
    "ONSHAPE_STATE",
    ROOT / "config" / "onshape-state.json",
))
DEFAULT_PARAMETERS_PATH = ROOT / "config" / "model.default.json"
PREVIEW_DIR = ROOT / "outputs" / "previews"
REPORT_DIR = ROOT / "outputs" / "reports"


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


class OnshapeClient:
    def __init__(self) -> None:
        credentials = load_json(CREDENTIALS_PATH)
        self.state = load_json(STATE_PATH)
        self.base_url = credentials.get("baseUrl", self.state.get("baseUrl", "https://cad.onshape.com")).rstrip("/")
        if credentials.get("accessToken"):
            self.authorization = "Bearer " + credentials["accessToken"]
        else:
            raw = f"{credentials['accessKey']}:{credentials['secretKey']}".encode()
            self.authorization = "Basic " + base64.b64encode(raw).decode()

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        timeout: int = 180,
    ) -> Any:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        headers = {
            "Authorization": self.authorization,
            "Accept": "application/json;charset=UTF-8; qs=0.09",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json;charset=UTF-8; qs=0.09"
        last_error: Exception | None = None
        for attempt in range(4):
            request = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    payload = response.read()
                    if not payload:
                        return {"httpStatus": response.status}
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type:
                        return json.loads(payload)
                    return payload
            except urllib.error.HTTPError as error:
                payload = error.read().decode("utf-8", "replace")
                try:
                    details = json.loads(payload)
                except json.JSONDecodeError:
                    details = {"message": payload[:4000]}
                if error.code != 429 and error.code < 500:
                    raise RuntimeError(
                        f"HTTP {error.code}: {json.dumps(details, ensure_ascii=False)}"
                    ) from error
                last_error = RuntimeError(
                    f"HTTP {error.code}: {json.dumps(details, ensure_ascii=False)}"
                )
            except urllib.error.URLError as error:
                last_error = error
            if attempt < 3:
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Onshape request failed after retries: {last_error}")


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def parameter_payload(parameters: dict[str, Any]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for parameter_id, value in parameters.items():
        if isinstance(value, bool):
            payload.append({
                "btType": "BTMParameterBoolean-144",
                "parameterId": parameter_id,
                "value": value,
            })
        else:
            payload.append({
                "btType": "BTMParameterQuantity-147",
                "parameterId": parameter_id,
                "expression": str(value),
                "isInteger": False,
            })
    return payload


def compact_feature_response(payload: dict[str, Any]) -> dict[str, Any]:
    state = payload.get("featureState") or {}
    feature = payload.get("feature") or {}
    return {
        "featureStatus": state.get("featureStatus"),
        "inactive": state.get("inactive"),
        "featureId": feature.get("featureId"),
        "featureType": feature.get("featureType"),
        "namespace": feature.get("namespace"),
        "sourceMicroversion": payload.get("sourceMicroversion"),
    }
