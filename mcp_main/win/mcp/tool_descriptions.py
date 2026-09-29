"""Split each tool description into a short advertised text and a kept full text.

A caller pays for ``tools/list`` before it makes a single call, and this
registry's 111 descriptions carry 53,409 characters. Most of that is contract (a
precondition, an irreversibility, a refusal) or routing (a parameter name, an
``action='...'`` value, another tool to call next); the rest is narrative --
"measured live <date>" evidence, historical "why" prose, and rationale a caller
needs neither to route with nor to avoid a trap.

This module performs the split **once**, at import time, with no library
change: the payload that ``tools/list`` advertises keeps a short summary, while
the shared ``ToolRecord`` (and therefore ``mcp_tool_catalog action=describe``)
keeps the complete original text.

A sentence is **kept** when it is:

1. the opening sentence, verbatim;
2. a sentence stating a prohibition, a precondition or an irreversibility,
   matched by :data:`SAFETY_MARKERS`;
3. a sentence with an uppercase emphasis negation (:data:`EMPHASIS_NEGATIONS`) --
   this registry writes its hazards in caps;
4. a sentence containing a phrase in :data:`REQUIRED_PHRASES`, the exact set the
   test suite asserts must appear in the advertised payload;
5. a **routing** sentence: one naming one of this tool's parameter names,
   another registered tool, a configuration knob, an ``action='...'`` value, or
   a backticked identifier or value (:class:`RoutingContext`).

Everything else is dropped from the payload and stays reachable: :func:`apply`
records the original text and :func:`detail_for` returns it for any record built
from the same registry, so ``describe`` is never lossy. The visible text is
always a **subsequence of whole sentences** of the original, so it can only
shrink, every kept sentence is byte-identical to its source, and -- the point of
rule 5 -- no parameter name, action value, peer-tool reference, config knob or
backticked value can leave the advertised payload.

Determinism: :func:`summarize_tool_description` is a pure function of
``(name, description, context)``. Same input, same output; no clock, no
environment, no iteration over an unordered collection.

This module must not import ``server`` or ``tool_views``: ``server`` imports
this at assembly time, and importing back would be a cycle. It only holds the
summary rule plus the small registry that makes the full text reachable.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

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

#: Rule 3: the emphasis negations this registry writes in capitals when a
#: sentence carries a hazard a lowercase marker might miss ("false means no
#: marker was found, NOT that the profile is anonymous").
EMPHASIS_NEGATIONS: tuple[str, ...] = ("NOT", "NEVER", "MUST", "ONLY", "CANNOT")

#: Sentence-final abbreviations that must not end a sentence boundary. Without
#: this, "... calls with (context, id), e.g. 'function(...)'." would split into a
#: fragment ending in "e.g." and a detached code example.
_ABBREVIATIONS: tuple[str, ...] = ("e.g.", "i.e.", "vs.", "etc.", "no.", "cf.", "resp.")

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_EMPHASIS = re.compile(r"\b(?:" + "|".join(EMPHASIS_NEGATIONS) + r")\b")
_BACKTICKED = re.compile(r"`[^`]+`")
_ACTION_VALUE = re.compile(r"action\s*=\s*['\"][^'\"]+['\"]")
_CONFIG_KNOB = re.compile(r"\b(?:MCP|ONSHAPE)_[A-Z][A-Z_]*\b")

#: name -> (advertised summary, complete original text) for every split tool.
#: Written once by :func:`apply` during server assembly and read-only after.
_SPLIT: dict[str, tuple[str, str]] = {}


def _word_pattern(words: Iterable[str], *, exclude: Iterable[str] = ()) -> re.Pattern[str] | None:
    """Compile a word-boundary alternation, longest first, or ``None`` if empty."""
    try:
        skip = set(exclude)
    except TypeError:  # pragma: no cover - defensive
        skip = set()
    kept = sorted({word for word in words if word and word not in skip}, key=lambda w: (-len(w), w))
    if not kept:
        return None
    return re.compile(r"\b(?:" + "|".join(re.escape(word) for word in kept) + r")\b")


class RoutingContext:
    """The names that make a sentence routing-relevant for one tool.

    Built once per registry by :func:`routing_contexts`; matching is
    word-bounded so a parameter name is not found inside a longer word. A
    compiled pattern is a pure value, so two contexts built from the same
    arguments behave identically.
    """

    __slots__ = ("name", "parameters", "tool_names", "_parameters", "_peers")

    def __init__(
        self,
        name: str,
        parameters: Sequence[str] = (),
        tool_names: Sequence[str] = (),
    ) -> None:
        self.name = name
        self.parameters = tuple(parameters)
        self.tool_names = tuple(tool_names)
        self._parameters = _word_pattern(self.parameters)
        self._peers = _word_pattern(self.tool_names, exclude=(name,))

    def carries_routing(self, sentence: str) -> bool:
        """True when dropping this sentence could hide how to drive or route."""
        if _BACKTICKED.search(sentence) or _ACTION_VALUE.search(sentence):
            return True
        if _CONFIG_KNOB.search(sentence):
            return True
        if self._parameters is not None and self._parameters.search(sentence) is not None:
            return True
        return self._peers is not None and self._peers.search(sentence) is not None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"RoutingContext(name={self.name!r}, parameters={len(self.parameters)}, "
            f"tool_names={len(self.tool_names)})"
        )


def routing_contexts(tools: Sequence[Mapping[str, Any]]) -> dict[str, RoutingContext]:
    """One :class:`RoutingContext` per tool, from the registry itself.

    The parameter names come from each tool's ``inputSchema.properties`` and the
    peer names from the registry, so the rule needs no hand-maintained list of
    names that could drift from the schemas it describes.
    """
    names = tuple(str(tool["name"]) for tool in tools)
    contexts: dict[str, RoutingContext] = {}
    for tool in tools:
        properties = (tool.get("inputSchema") or {}).get("properties") or {}
        contexts[str(tool["name"])] = RoutingContext(
            str(tool["name"]), tuple(str(key) for key in properties), names
        )
    return contexts


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


def summarize_tool_description(
    name: str,
    description: str,
    context: RoutingContext | None = None,
) -> str:
    """Return the short advertised text for one tool, per the module docstring.

    Pure and deterministic given the registry-derived ``context`` (rule 5 needs
    the tool's parameter names and its peers; without one, only the name-free
    routing classes apply). The result is a subsequence of whole original
    sentences in their original order, so it is never longer than
    ``description``; when the rules retain every sentence the original string is
    returned unchanged.
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
        if (
            any(phrase in sentence for phrase in required)
            or any(marker in lowered[index] for marker in SAFETY_MARKERS)
            or _EMPHASIS.search(sentence) is not None
            or (context is not None and context.carries_routing(sentence))
        ):
            keep.add(index)
    return " ".join(sentences[index] for index in sorted(keep))


def apply(tools: list[dict[str, Any]]) -> dict[str, str]:
    """Split every tool's description in place; return ``name -> full text``.

    The registry is the single source of truth for the long literals, so this
    only rewrites ``description`` after recording the original. Returns one
    entry per tool so the caller can thread the full text into records
    explicitly.
    """
    details: dict[str, str] = {}
    contexts = routing_contexts(tools)
    for tool in tools:
        name = str(tool["name"])
        original = tool.get("description")
        if not isinstance(original, str):
            continue
        summary = summarize_tool_description(name, original, contexts.get(name))
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
