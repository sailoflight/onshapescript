"""Split each tool description into a short advertised text and a kept full text.

A caller pays for ``tools/list`` before it makes a single call, and this
registry's 111 descriptions carry 53,409 characters. Most of that is contract
(a precondition, an irreversibility, a refusal), but a real part is narrative:
"measured live <date>" evidence, historical "why" prose, and rationale a caller
does not need to route or to avoid a trap.

This module performs the split **once**, at import time, with no library
change: the payload that ``tools/list`` advertises keeps a short summary, while
the shared ``ToolRecord`` (and therefore ``mcp_tool_catalog action=describe``)
keeps the complete original text.

The rule, in order:

1. the opening sentence, verbatim;
2. every sentence that states a prohibition, a precondition or an
   irreversibility, matched by :data:`SAFETY_MARKERS` (a documented helper, not
   the authority -- the authority is item 3);
3. every sentence containing a phrase in :data:`REQUIRED_PHRASES`, which is the
   exact set the test suite asserts must appear in the advertised payload;
4. optionally further leading sentences, in order, while the accumulated
   summary stays at or below :data:`SUMMARY_CHAR_CAP`.

Everything removed stays reachable: :func:`apply` records the original text and
:func:`detail_for` returns it for any record built from the same registry, so
``describe`` is never lossy. The visible text is always a **subsequence of
whole sentences** of the original, so the advertised text can only shrink and
every kept sentence is byte-identical to its source.

Determinism: :func:`summarize_tool_description` is a pure function of
``(name, description)``. Same input, same output; no clock, no environment, no
iteration over an unordered collection.

This module must not import ``server`` or ``tool_views``: ``server`` imports
this at assembly time, and importing back would be a cycle. It only holds the
summary rule plus the small registry that makes the full text reachable.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

#: The per-tool target for the optional leading-sentence extension. Rule 1-3
#: sentences are mandatory and may push a summary past the cap; the cap only
#: bounds how much *further* routing prose is carried.
SUMMARY_CHAR_CAP = 600

#: Phrases the existing suite asserts appear in the ADVERTISED payload
#: (``server.TOOLS[name]["description"]``). They are the tripwire proving the
#: visible text still carries the contract: the builder keeps the whole sentence
#: that contains each phrase. Each entry names the test that requires it; do not
#: drop one without changing that test first.
REQUIRED_PHRASES: dict[str, tuple[str, ...]] = {
    # dev/tests/test_browser_mode.py::test_browser_session_exposes_cooperative_release
    "browser_session": (
        "loses login state",
        "does NOT",
        "keeps the window",
        "another MCP process",
    ),
    # dev/tests/test_browser_mode.py::test_export_step_schema_declares_overwrite
    "browser_export_step": ("stagedArtifacts", "recovery"),
    # dev/tests/test_browser_mode.py::test_tool_view_schema_advertises_the_collapse_expand_control
    # (plus "not an authorization boundary", asserted by
    # dev/tests/test_mcp_server.py on the tools/list payload)
    "mcp_tool_view": (
        "not an authorization boundary",
        "CONNECTION-scoped",
        "in-memory",
        "revoking a permission",
        "gateway",
    ),
    # dev/tests/test_browser_mode.py::test_fs_read_notices_schema_declares_include_stale
    "browser_fs_read_notices": ("outOfDate", "staleNotices", "includeStale=true"),
    # dev/tests/test_reference_miss.py::test_fs_get_function_schema_exposes_full
    "fs_get_function": ("full=true",),
}

#: Sentence-level markers for rule 2. A sentence carrying one of these states a
#: prohibition, a precondition or an irreversibility, and is kept wherever it
#: sits in the description. The list is deliberately narrow enough to still
#: drop pure narrative ("measured live <date>: ...", "because ...") while
#: covering the modal and negation vocabulary this registry actually uses.
SAFETY_MARKERS: tuple[str, ...] = (
    "do not",
    "does not",
    "never",
    "must",
    "cannot",
    "can not",
    "refuse",
    "irreversible",
    "only when",
    "only if",
    "only in",
    "only on",
    "without ",
    "unless ",
    "requires",
    "is not the completion",
    "not the completion signal",
    # The persistent-profile identity warning: "THE BROWSER IS NOT ANONYMOUS".
    "not anonymous",
)

#: Sentence-final abbreviations that must not end a sentence boundary. Without
#: this, "... calls with (context, id), e.g. 'function(...)'." would split into a
#: fragment ending in "e.g." and a detached code example.
_ABBREVIATIONS: tuple[str, ...] = ("e.g.", "i.e.", "vs.", "etc.", "no.", "cf.", "resp.")

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")

#: name -> (advertised summary, complete original text) for every split tool.
#: Written once by :func:`apply` during server assembly and read-only after.
_SPLIT: dict[str, tuple[str, str]] = {}


def split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries, refusing to break after an abbreviation."""
    sentences: list[str] = []
    buffer = ""
    for piece in _SENTENCE_BOUNDARY.split(text):
        buffer = piece if not buffer else f"{buffer} {piece}"
        if any(buffer.lower().endswith(abbreviation) for abbreviation in _ABBREVIATIONS):
            continue
        sentences.append(buffer)
        buffer = ""
    if buffer:
        sentences.append(buffer)
    return sentences


def summarize_tool_description(name: str, description: str) -> str:
    """Return the short advertised text for one tool, per the module docstring.

    Pure and deterministic. The result is a subset of the original sentences in
    their original order, so it is never longer than ``description``; when the
    rules retain every sentence the original string is returned unchanged.
    """
    sentences = split_sentences(description)
    if not sentences:
        return description
    lowered = [sentence.lower() for sentence in sentences]
    required = REQUIRED_PHRASES.get(name, ())
    keep = {0}
    for index, sentence in enumerate(sentences):
        if index == 0:
            continue
        if any(phrase in sentence for phrase in required) or any(
            marker in lowered[index] for marker in SAFETY_MARKERS
        ):
            keep.add(index)
    # Rule 4: extend the leading run while it still fits the cap. Mandatory
    # sentences already in `keep` are counted but never block the extension of
    # an earlier, still-missing leading sentence.
    running = len(sentences[0])
    for index in range(1, len(sentences)):
        if index not in keep and running + 1 + len(sentences[index]) > SUMMARY_CHAR_CAP:
            break
        keep.add(index)
        running += 1 + len(sentences[index])
    return " ".join(sentences[index] for index in sorted(keep))


def apply(tools: list[dict[str, Any]]) -> dict[str, str]:
    """Split every tool's description in place; return ``name -> full text``.

    The registry is the single source of truth for the long literals, so this
    only rewrites ``description`` after recording the original. Returns one
    entry per tool so the caller can thread the full text into records
    explicitly.
    """
    details: dict[str, str] = {}
    for tool in tools:
        name = str(tool["name"])
        original = tool.get("description")
        if not isinstance(original, str):
            continue
        summary = summarize_tool_description(name, original)
        details[name] = original
        _SPLIT[name] = (summary, original)
        if summary != original:
            tool["description"] = summary
    return details


def detail_for(name: str, advertised: str) -> str:
    """The complete original text for ``name``, or ``advertised`` unchanged.

    Substitution only happens when the payload still carries the exact summary
    this module produced, so a synthetic or edited registry that reuses a real
    name cannot be handed this registry's text by accident.
    """
    entry = _SPLIT.get(name)
    if entry is not None and entry[0] == advertised:
        return entry[1]
    return advertised


def recorded_details() -> Mapping[str, str]:
    """The complete original text of every split tool, as an immutable mapping."""
    return {name: original for name, (_summary, original) in _SPLIT.items()}
