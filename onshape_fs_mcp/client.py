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
# Parameter sets live under config/ by default. Example folders override this
# with ONSHAPE_PARAMETERS_DIR so their parameter sets stay self-contained.
PARAMETERS_DIR = Path(os.environ.get(
    "ONSHAPE_PARAMETERS_DIR",
    ROOT / "config",
))
DEFAULT_PARAMETERS_PATH = PARAMETERS_DIR / "model.default.json"
# Rendered previews and reports default to outputs/ under the project root.
OUTPUTS_DIR = Path(os.environ.get(
    "ONSHAPE_OUTPUTS_DIR",
    ROOT / "outputs",
))
PREVIEW_DIR = OUTPUTS_DIR / "previews"
REPORT_DIR = OUTPUTS_DIR / "reports"
# Local API-usage ledger. Onshape has no public "query my quota" endpoint, so we
# passively bookkeep: every 2xx/3xx counts toward the annual limit (per the
# official docs) and every response's X-Rate-Limit-Remaining header is captured.
# This costs zero extra API calls. A 402 response is the server's signal that the
# annual limit is exhausted.
USAGE_PATH = Path(os.environ.get(
    "ONSHAPE_API_USAGE",
    ROOT / "config" / "api-usage.json",
))


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


class RateLimited(RuntimeError):
    """Raised immediately on HTTP 429. NEVER retried — the Retry-After wait time
    (also captured in config/api-usage.json) is surfaced so callers can exit
    and wait instead of hammering the rate limit."""


class RateLimitedHold(RuntimeError):
    """Raised BEFORE any request when the ledger shows the account is still
    under a long rate-limit hold (rate-limit remaining 0 with a large
    Retry-After). Like RateLimited, callers must exit and wait — never retry."""


def rate_limit_reason(usage: dict[str, Any] | None = None) -> str | None:
    """Return a reason string if the account is under a long rate-limit hold,
    else None. Zero network cost: reads the passive usage ledger only.

    Onshape's Retry-After landed at ~72910s (~20h) on 2026-08-14 with
    rate-limit remaining 0, so a run started during the hold would only burn
    futile requests. Every live entrypoint (MCP server + scripts) gates on this
    BEFORE the first request.
    """
    if usage is None:
        try:
            usage = load_json(USAGE_PATH)
        except Exception:
            return None
    retry_after = int(usage.get("lastRetryAfter") or 0)
    remaining = str(usage.get("lastRateLimitRemaining") or "")
    if remaining == "0" and retry_after > 60:
        return (
            f"Onshape rate-limited: Retry-After {retry_after}s "
            f"(~{retry_after // 3600}h), rate-limit remaining 0"
        )
    return None


class LiveApiDisabled(RuntimeError):
    """Raised when a live request is attempted while LIVE_API_ENABLED is off.

    The protocol's top constraint is that real API requests are explicit, not a
    script default — so the flag defaults to off and the transport refuses to
    send any request until the operator opts in.
    """


def live_api_enabled() -> bool:
    """Whether live Onshape API calls are explicitly allowed.

    Reads LIVE_API_ENABLED (truthy values: 1 / true / yes / on). Default off:
    real requests must be explicit, per the protocol's top constraint. Zero
    network cost; checked by the transport (OnshapeClient.request) and by every
    live entrypoint's gate.
    """
    return os.environ.get("LIVE_API_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _live_disabled_reason(label: str) -> str:
    return (
        f"Live Onshape API calls are disabled (LIVE_API_ENABLED not set to 1). "
        f"Real requests must be explicit: set LIVE_API_ENABLED=1 to allow "
        f"'{label}'. Dry runs and all offline tools still work."
    )


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
        self.usage_path = USAGE_PATH
        self._usage = self._load_usage()

    def _load_usage(self) -> dict[str, Any]:
        if self.usage_path.is_file():
            try:
                return json.loads(self.usage_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "consumed": 0,
            "calls": [],
            "lastRateLimitRemaining": None,
            "lastRetryAfter": None,
            "last402At": None,
        }

    def _record_usage(
        self,
        method: str,
        path: str,
        status: int | None,
        headers: Any,
    ) -> None:
        """Bookkeep one API call. 2xx/3xx count toward the annual limit (4xx/5xx
        do not, per the official docs); capture rate-limit headers when present.
        Never raises: bookkeeping must not break a request."""
        usage = self._usage
        if status is not None and status < 400:
            usage["consumed"] = int(usage.get("consumed", 0)) + 1
        remaining = headers.get("x-rate-limit-remaining") if headers else None
        if remaining is not None:
            usage["lastRateLimitRemaining"] = str(remaining)
            # A healthy remaining count means any prior Retry-After hold has
            # cleared. Clear it so api_usage stops surfacing a stale wait time
            # (e.g. the 72910s from 2026-08-14's burst) after recovery.
            try:
                if int(str(remaining)) > 0:
                    usage["lastRetryAfter"] = None
            except ValueError:
                pass
        retry_after = headers.get("retry-after") if headers else None
        if retry_after is not None:
            usage["lastRetryAfter"] = str(retry_after)
        if status == 402:
            usage["last402At"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        usage.setdefault("calls", []).append({
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "method": method,
            "path": path,
            "status": status,
        })
        usage["calls"] = usage["calls"][-100:]
        try:
            self.usage_path.parent.mkdir(parents=True, exist_ok=True)
            self.usage_path.write_text(json.dumps(usage, indent=1), encoding="utf-8")
        except OSError:
            pass

    def request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
        timeout: int = 180,
    ) -> Any:
        # Transport-level backstop: a real request is never sent while the
        # explicit opt-in is off, regardless of whether a caller forgot to gate
        # at its own entrypoint. Dry runs and offline tools never reach here.
        if not live_api_enabled():
            raise LiveApiDisabled(_live_disabled_reason(f"{method} {path}"))
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
        mutating = method in ("POST", "PATCH", "DELETE")
        # Mutations never auto-retry (a timeout != "not executed"; re-sending
        # risks double-execution). Only idempotent GET retries on transient
        # 5xx/network errors.
        attempts = 1 if mutating else 4
        last_error: Exception | None = None
        for attempt in range(attempts):
            request = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    payload = response.read()
                    self._record_usage(method, path, response.status, response.headers)
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
                self._record_usage(method, path, error.code, getattr(error, "headers", None))
                if error.code == 429:
                    # 429 is NEVER retried: raise immediately with the wait time
                    # (the Retry-After header is already persisted to the ledger
                    # by _record_usage) so callers exit and wait instead of
                    # hammering the rate limit.
                    headers = getattr(error, "headers", None) or {}
                    retry_after = headers.get("Retry-After") or headers.get("retry-after") or "?"
                    raise RateLimited(
                        f"HTTP 429 rate-limited, wait ~{retry_after}s: "
                        f"{json.dumps(details, ensure_ascii=False)}"
                    ) from error
                if error.code < 500 or mutating:
                    # Non-retryable (4xx), or a mutation we must never re-send.
                    raise RuntimeError(
                        f"HTTP {error.code}: {json.dumps(details, ensure_ascii=False)}"
                    ) from error
                # 5xx on an idempotent GET: transient server error, retry below.
                last_error = RuntimeError(
                    f"HTTP {error.code}: {json.dumps(details, ensure_ascii=False)}"
                )
            except urllib.error.URLError as error:
                if mutating:
                    # Timeout/network error on a mutation is ambiguous (it may
                    # have executed server-side) — never re-send.
                    raise RuntimeError(
                        f"{error} on {method} {path} (not retried: timeout != not executed)"
                    ) from error
                last_error = error
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Onshape request failed after retries: {last_error}")

    def describe(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build the exact request request() would send — method, URL, headers,
        body — WITHOUT sending it. The Authorization header is redacted (secrets
        must never reach dry-run output, logs, or fixtures). This is the shared
        request builder behind dry_run so a dry run shows the real payload, not
        a re-typed approximation."""
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query, doseq=True)
        headers = {
            "Authorization": "<REDACTED>",
            "Accept": "application/json;charset=UTF-8; qs=0.09",
        }
        if body is not None:
            headers["Content-Type"] = "application/json;charset=UTF-8; qs=0.09"
        return {"method": method, "url": url, "headers": headers, "body": body}


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
