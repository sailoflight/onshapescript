#!/usr/bin/env python3
"""Query helpers for the vendored Onshape auth + error-handling docs.

The MCP onshape_api_auth / onshape_api_error_codes tools read the structured
api_docs.json built by onshape_docs/scripts/build_onshape_api_docs_index.py. These pages are
public Onshape developer docs; nothing here contacts the network or Onshape.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DOCS_ROOT = Path(__file__).resolve().parents[1]
API_DOCS_PATH = DOCS_ROOT / "reference" / "index" / "onshape-api-docs" / "api_docs.json"

_docs: dict[str, Any] | None = None

# h3 step headings that make up the OAuth2 authorization-code workflow.
OAUTH_STEPS = (
    "1: Register the app",
    "2: Get the user authorization code",
    "3: Exchange the code for an access token",
    "4: Use the access token",
    "5: Refresh the token",
    "6: Grant authorization",
)


def _load() -> dict[str, Any]:
    global _docs
    if _docs is None:
        if not API_DOCS_PATH.is_file():
            raise FileNotFoundError(
                f"{API_DOCS_PATH} is missing; run onshape_docs/scripts/fetch_onshape_api_docs.py "
                "and onshape_docs/scripts/build_onshape_api_docs_index.py"
            )
        _docs = json.loads(API_DOCS_PATH.read_text(encoding="utf-8"))
    return _docs


def reload() -> None:
    """Drop the cached index so a re-fetch + rebuild is visible immediately."""
    global _docs
    _docs = None


def _page(docs: dict[str, Any], page: str) -> dict[str, Any]:
    for entry in docs["pages"]:
        if entry["page"] == page:
            return entry
    raise ValueError(f"page {page!r} is not in the vendored API docs")


def _render_section(section: dict[str, Any]) -> str:
    lines: list[str] = []
    for block in section["blocks"]:
        kind = block["type"]
        if kind in ("para", "note"):
            lines.append(block["text"])
        elif kind == "code":
            lines.append(f"```{block.get('language', '')}\n{block['text']}\n```")
        elif kind == "list":
            lines.extend("- " + item for item in block["items"])
        elif kind == "table":
            rows = ["| " + " | ".join(row) + " |" for row in block["rows"]]
            if rows:
                lines.append(rows[0])
                lines.append("|" + "---|" * (len(block["rows"][0])))
                lines.extend(rows[1:])
    return "\n".join(lines)


def _sections(page: dict[str, Any], level: int = 3) -> list[dict[str, Any]]:
    return [s for s in page["sections"] if s["level"] == level]


def auth(section: str | None = None) -> dict[str, Any]:
    """OAuth2 + API-key authentication reference.

    Without a section: a distilled summary (workflow step titles with their
    opening summary, plus API-key steps). With a section title: the full section
    text including code blocks.
    """
    docs = _load()
    oauth = _page(docs, "oauth")
    apikeys = _page(docs, "apikeys")

    if section:
        for page in (oauth, apikeys):
            for entry in page["sections"]:
                if section.lower() in entry["title"].lower():
                    return {
                        "page": page["page"],
                        "title": entry["title"],
                        "text": _render_section(entry),
                    }
        raise ValueError(
            f"no section matching {section!r}; available: "
            + ", ".join(s["title"] for p in (oauth, apikeys) for s in _sections(p))
        )

    steps = []
    for entry in _sections(oauth):
        if entry["title"] in OAUTH_STEPS:
            summary = ""
            for block in entry["blocks"]:
                if block["type"] == "para":
                    summary = block["text"]
                    break
            steps.append({
                "step": entry["title"],
                "summary": (summary[:400] + "…") if len(summary) > 400 else summary,
            })
    key_steps = [
        {
            "step": entry["title"],
            "summary": next(
                (b["text"][:200] for b in entry["blocks"]
                 if b["type"] in ("para", "list")),
                "",
            ),
        }
        for entry in _sections(apikeys)
    ]
    return {
        "oauthWorkflowSteps": steps,
        "apiKeySteps": key_steps,
        "oauthSectionTitles": [s["title"] for s in _sections(oauth)],
        "apiKeySectionTitles": [s["title"] for s in _sections(apikeys)],
        "note": "Pass section=<title> to get the full text of one step, including code.",
    }


def error_codes(status: int | None = None) -> dict[str, Any]:
    """HTTP response codes + API call limits.

    status filters to one code (e.g. 429); without it, the full table plus the
    rate-limit / annual-limit text from the official limits page.
    """
    docs = _load()
    codes = docs["errorCodes"]
    if status is not None:
        matches = [c for c in codes if c["code"] == status]
        if not matches:
            raise ValueError(
                f"no error code {status}; available: "
                + ", ".join(str(c["code"]) for c in codes)
            )
        return {"errorCodes": matches, "count": 1}
    limits = _page(docs, "limits")
    return {
        "count": len(codes),
        "errorCodes": codes,
        "apiLimits": _render_section(limits["sections"][1])
        if len(limits["sections"]) > 1 else "",
        "note": "Pass status=<code> (e.g. 429) for one error's detail.",
    }
