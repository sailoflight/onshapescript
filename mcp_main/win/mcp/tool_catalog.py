"""Bounded discovery over the registry: index, search, describe, status.

The registry model, the per-profile selection and the confirmation
classification are the shared ``mcp_surface`` library's (see
``docs/development/MCP_SURFACE_INTEGRATION.md``): a tool's semantic level,
default exposure, absorbed-compatibility flag and confirmation mode all come
from one ``ToolRecord``/``Surface`` built by ``tool_views.build_surface``, so
this module does not keep a second metadata model. The bounded *lookup* engine
is the library's ``ToolCatalog`` where it is contract-compatible (name
resolution and the unknown-name path in ``describe``); the result rendering,
filters and capability cards below are this project's, because the documented
``mcp_tool_catalog`` contract carries keys the generic library does not emit.

Retrieval is not free, which is the whole reason these bounds exist: a
three-result ``search`` measures ~6,800 characters because every summary carries
its concurrency and confirmation contract, and one ``describe`` of a modelling
tool ~10,500. So ``index`` is the cheap map, ``search`` is bounded and never
returns a schema, and ``describe`` is the only schema path. Caps come from the
shared library (``MAX_SEARCH_RESULTS``/``MAX_INDEX_RESULTS``) so the mechanism
and its arithmetic cannot drift between the two.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from mcp_surface import (
    DEFAULT_INDEX_RESULTS,
    DEFAULT_SEARCH_RESULTS,
    MAX_INDEX_RESULTS,
    MAX_SEARCH_RESULTS,
    ToolCatalog,
    UnknownToolName,
    compact,
    tokenize,
)

from mcp_main.win.mcp.concurrency import CONCURRENCY_CONTRACT_VERSION
from mcp_main.win.mcp.tool_views import (
    BROWSER_LEVEL_PRIORITY_ORDER,
    REST_REFERENCE_TOOL_NAMES,
    VALID_PROFILES,
    VALID_SEMANTIC_LEVELS,
    build_surface,
)


VALID_MODULES = (
    "control",
    "browser",
    "rest",
    "rest_reference",
    "featurescript",
    "documentation",
)
VALID_NETWORKS = ("offline", "browser", "live")
# The one tool that takes a `capability` plus bounded `values`. A capability is
# not a registered tool, so it is never returned as a tool summary.
CAPABILITY_DEPLOY_TOOL = "browser_deploy_and_apply_featurescript"

#: One sentence per category, so a caller can route without reading a tool.
MODULE_PURPOSES = {
    "control": "Discovery, catalog search, and this connection's tool-view state.",
    "browser": "Zero-quota browser leg: session, tabs, Feature Studio, thin-feature modelling, runner, exports.",
    "rest": "Onshape REST operations (quota-spending) and local state/geometry helpers.",
    "rest_reference": "Offline Onshape REST API reference: endpoints, schemas, auth, error codes.",
    "featurescript": "Offline FeatureScript reference: functions, types, guides, and source checks.",
    "documentation": "Project documentation index and section reads.",
}
#: Token weights and the level tie-break are the shared surface's; this project
#: reads its declared preference tuple instead of keeping a second copy.
_BROWSER_LEVEL_PRIORITY = {
    level: index for index, level in enumerate(BROWSER_LEVEL_PRIORITY_ORDER)
}


def tool_module(name: str) -> str:
    if name.startswith("mcp_"):
        return "control"
    if name.startswith("browser_"):
        return "browser"
    if name.startswith("docs_"):
        return "documentation"
    if name.startswith("fs_"):
        return "featurescript"
    if name in REST_REFERENCE_TOOL_NAMES:
        return "rest_reference"
    if name.startswith("onshape_"):
        return "rest"
    raise ValueError(f"registered tool has no catalog module: {name}")


def _tokens(value: str) -> tuple[str, ...]:
    return tokenize(value)


def _compact(value: str, limit: int = 180) -> str:
    return compact(value, limit)


def capability_section(query: str, limit: int = 3) -> dict[str, Any]:
    """Matching whole-feature capability cards, with the call that uses one.

    Shared by every discovery entry (the catalog and `browser_discover_tools`)
    so a card cannot describe one invocation in one place and another elsewhere.
    This layer is deliberately NOT in the shared library: a capability card
    names a FeatureScript job this project owns.
    """
    from onshape_browser_mode import capabilities

    matches = capabilities.search(query, limit=limit)
    if not matches:
        return {}
    for match in matches:
        match["invocation"]["tool"] = CAPABILITY_DEPLOY_TOOL
    return {"capabilities": matches, "capabilityInvocationTool": CAPABILITY_DEPLOY_TOOL}


def _browser_semantics(name: str) -> dict[str, Any] | None:
    if not name.startswith("browser_"):
        return None
    from onshape_browser_mode.semantics import semantic_metadata

    return semantic_metadata(name)


def _validate_string_list(
    value: Any,
    *,
    field: str,
    allowed: tuple[str, ...],
) -> tuple[str, ...] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item in allowed for item in value)
    ):
        raise ValueError(f"{field} must be a non-empty list containing: {', '.join(allowed)}")
    if len(set(value)) != len(value):
        raise ValueError(f"{field} must not contain duplicates")
    return tuple(value)


def _catalog_metadata(name: str, tool: dict[str, Any]) -> dict[str, Any]:
    """The catalog-specific facts layered onto one shared ``ToolRecord``.

    Module taxonomy, network classification, mutation/cost annotations and the
    one confirmation overrides the schema rule cannot express
    (``onshape_eval_featurescript``'s budget override) live here, so the record
    carries them and the generic rule stays in the library.
    """
    cost = tool.get("cost") or {}
    annotations = tool.get("annotations") or {}
    concurrency = cost.get("concurrency")
    if not isinstance(concurrency, dict):
        raise ValueError(f"tool {name} is missing concurrency metadata")
    network = str(cost.get("network", "offline"))
    if network not in VALID_NETWORKS:
        raise ValueError(f"tool {name} has unsupported network value: {network}")
    semantic = _browser_semantics(name)
    properties = (tool.get("inputSchema") or {}).get("properties") or {}
    return {
        "category": tool_module(name),
        # The semantic name is searchable text in the original index; the
        # library derives `search_tokens` from name + keywords + category +
        # description, so this keeps the token set identical.
        "keywords": (semantic.get("semanticName", ""),) if semantic else (),
        "network": network,
        "mutating": bool(cost.get("mutating", not annotations.get("readOnlyHint", True))),
        "dry_run": "dry_run" in properties,
        "side_effects": tuple(str(value) for value in cost.get("side_effects") or ()),
        "concurrency": dict(concurrency),
        "confirmation_override": (
            "budget_override" if name == "onshape_eval_featurescript" else None
        ),
    }


@dataclass(frozen=True)
class CatalogEntry:
    tool: dict[str, Any]
    name: str
    description: str
    module: str
    profiles: tuple[str, ...]
    semantic: dict[str, Any] | None
    network: str
    mutating: bool
    dry_run: bool
    confirmation_exposed: bool
    confirmation_required: bool
    confirmation_schema_required: bool
    confirmation_mode: str
    side_effects: tuple[str, ...]
    concurrency: dict[str, Any]
    required: tuple[str, ...]
    name_tokens: tuple[str, ...]
    search_tokens: frozenset[str]

    @property
    def semantic_level(self) -> str | None:
        return self.semantic.get("semanticLevel") if self.semantic else None

    def summary(self, *, visible: bool, score: int) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": _compact(self.description),
            "module": self.module,
            "profiles": list(self.profiles),
            "semanticLevel": self.semantic_level,
            "network": self.network,
            "requiresBrowserSession": bool((self.tool.get("cost") or {}).get("requires_browser_session", False)),
            "mutating": self.mutating,
            "dryRun": self.dry_run,
            "confirmationExposed": self.confirmation_exposed,
            "confirmationRequired": self.confirmation_required,
            "confirmationSchemaRequired": self.confirmation_schema_required,
            "confirmationMode": self.confirmation_mode,
            "sideEffects": list(self.side_effects),
            "concurrency": {
                "workflowIsolation": self.concurrency["workflowIsolation"],
                "classificationOnly": True,
                "access": self.concurrency["access"],
                "scope": self.concurrency["scope"],
                "sharedTargetState": self.concurrency["sharedTargetState"],
                "sharedLocalState": self.concurrency["sharedLocalState"],
                "safeDuringMutationWorkflow": self.concurrency[
                    "safeDuringMutationWorkflow"
                ],
                "safeDuringMutationWorkflowWhenExplicitTarget": self.concurrency[
                    "safeDuringMutationWorkflowWhenExplicitTarget"
                ],
                "requiresExplicitTargetForConcurrentUse": self.concurrency[
                    "requiresExplicitTargetForConcurrentUse"
                ],
                "callerMustVerifyScopeKeyPresence": self.concurrency[
                    "callerMustVerifyScopeKeyPresence"
                ],
            },
            "required": list(self.required),
            "visibleInCurrentView": visible,
            "matchScore": score,
        }

    def detail(self, *, visible: bool) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "module": self.module,
            "profiles": list(self.profiles),
            "semantic": self.semantic,
            "visibleInCurrentView": visible,
            "inputSchema": self.tool.get("inputSchema") or {"type": "object", "properties": {}},
            "annotations": self.tool.get("annotations") or {},
            "cost": self.tool.get("cost") or {},
            "sideEffects": list(self.side_effects),
            "concurrency": self.concurrency,
            "confirmation": {
                "exposed": self.confirmation_exposed,
                "requiredForRealCall": self.confirmation_required,
                "schemaRequired": self.confirmation_schema_required,
                "mode": self.confirmation_mode,
            },
            "conventionOnly": True,
            "authorityChanged": False,
            "knownNameCallAvailable": True,
        }


class ToolCatalogIndex:
    """Immutable, one-build search index over the authoritative tool registry.

    The registry is wrapped as the shared library's ``Surface`` once; every
    derived fact (level, default exposure, absorbed flag, confirmation mode,
    search tokens) is read back off that record rather than recomputed here.
    """

    def __init__(self, tools: list[dict[str, Any]]) -> None:
        names = [tool.get("name") for tool in tools]
        if any(not isinstance(name, str) or not name for name in names):
            raise ValueError("every catalog tool must have a non-empty string name")
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        if duplicates:
            raise ValueError(f"duplicate catalog tool names: {duplicates}")

        surface = build_surface(tools, metadata=_catalog_metadata)
        self.surface = surface
        # The shared bounded-lookup engine over the same surface. The project's
        # filters, paging and result keys layer on top; `describe` resolves a
        # name through it so the unknown-name path is the library's.
        self.lookup = ToolCatalog(surface)

        profile_names: dict[str, set[str]] = {
            profile: {record.name for record in surface.select(profile=profile)}
            for profile in VALID_PROFILES
        }

        entries: list[CatalogEntry] = []
        postings: dict[str, set[str]] = defaultdict(set)
        for tool, record in zip(tools, surface.records):
            name = record.name
            confirmation_mode = record.confirmation_mode
            entry = CatalogEntry(
                tool=tool,
                name=name,
                description=record.description,
                module=record.category,
                profiles=tuple(
                    profile for profile in VALID_PROFILES if name in profile_names[profile]
                ),
                semantic=_browser_semantics(name),
                network=record.network,
                mutating=record.mutating,
                dry_run=record.dry_run,
                confirmation_exposed=record.confirmation_exposed,
                confirmation_required=confirmation_mode
                in {"always", "non_dry_run", "runtime_required"},
                confirmation_schema_required=record.confirmation_schema_required,
                confirmation_mode=confirmation_mode,
                side_effects=record.side_effects,
                concurrency=dict(record.concurrency),
                required=tuple((tool.get("inputSchema") or {}).get("required") or ()),
                name_tokens=record.name_tokens,
                search_tokens=record.search_tokens,
            )
            entries.append(entry)
            for token in entry.search_tokens:
                postings[token].add(name)

        self._entries = tuple(entries)
        self._by_name = {entry.name: entry for entry in entries}
        self._postings = {token: frozenset(values) for token, values in postings.items()}
        fingerprint_source = [
            {
                "name": entry.name,
                "description": entry.description,
                "module": entry.module,
                "profiles": entry.profiles,
                "semanticLevel": entry.semantic_level,
                "network": entry.network,
                "mutating": entry.mutating,
                "concurrency": entry.concurrency,
                "inputSchema": entry.tool.get("inputSchema"),
            }
            for entry in entries
        ]
        canonical = json.dumps(fingerprint_source, sort_keys=True, separators=(",", ":"))
        self.fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        self.build_count = 1

    def status(self, *, visible_names: set[str]) -> dict[str, Any]:
        return {
            "registryCount": len(self._entries),
            "indexedCount": len(self._by_name),
            "visibleCount": len(visible_names),
            "fingerprint": self.fingerprint,
            "buildCount": self.build_count,
            "maxSearchResults": MAX_SEARCH_RESULTS,
            "defaultSearchResults": DEFAULT_SEARCH_RESULTS,
            "schemaPolicy": "exact-describe-only",
            "concurrencyPolicy": {
                "contractVersion": CONCURRENCY_CONTRACT_VERSION,
                "workflowIsolation": "none",
                "productionMutationMode": "single_modifying_agent",
                "classificationOnly": True,
                "authorityChanged": False,
            },
            "modules": dict(sorted(Counter(entry.module for entry in self._entries).items())),
            "profiles": {
                profile: sum(profile in entry.profiles for entry in self._entries)
                for profile in VALID_PROFILES
            },
            "networks": dict(sorted(Counter(entry.network for entry in self._entries).items())),
            "filters": {
                "modules": list(VALID_MODULES),
                "profiles": list(VALID_PROFILES),
                "semanticLevels": list(VALID_SEMANTIC_LEVELS),
                "networks": list(VALID_NETWORKS),
                "mutating": [False, True],
                "visibleOnly": [False, True],
            },
            "conventionOnly": True,
            "authorityChanged": False,
        }

    def _query_candidates(self, query_tokens: tuple[str, ...]) -> Iterable[CatalogEntry]:
        if not query_tokens:
            return self._entries
        matching_names: set[str] | None = None
        for token in query_tokens:
            token_matches: set[str] = set()
            for indexed_token, names in self._postings.items():
                if indexed_token.startswith(token):
                    token_matches.update(names)
            if matching_names is None:
                matching_names = token_matches
            else:
                matching_names.intersection_update(token_matches)
        return (self._by_name[name] for name in (matching_names or ()))

    @staticmethod
    def _score(entry: CatalogEntry, query: str, query_tokens: tuple[str, ...]) -> int:
        normalized_name = entry.name.lower()
        normalized_query = query.lower().strip()
        if normalized_query and normalized_name == normalized_query:
            return 0
        if normalized_query and normalized_name.startswith(normalized_query):
            return 10
        if query_tokens and all(token in entry.name_tokens for token in query_tokens):
            return 20
        if query_tokens and all(any(name_token.startswith(token) for name_token in entry.name_tokens) for token in query_tokens):
            return 30
        if query_tokens:
            return 40
        return 50

    def search(self, arguments: dict[str, Any], *, visible_names: set[str]) -> dict[str, Any]:
        query = arguments.get("query", "")
        if not isinstance(query, str):
            raise ValueError("query must be a string")
        query = " ".join(query.split())
        if len(query) > 200:
            raise ValueError("query must be at most 200 characters")
        modules = _validate_string_list(arguments.get("modules"), field="modules", allowed=VALID_MODULES)
        profiles = _validate_string_list(arguments.get("profiles"), field="profiles", allowed=VALID_PROFILES)
        levels = _validate_string_list(
            arguments.get("semantic_levels"), field="semantic_levels", allowed=VALID_SEMANTIC_LEVELS
        )
        network = arguments.get("network")
        if network is not None and network not in VALID_NETWORKS:
            raise ValueError(f"network must be one of: {', '.join(VALID_NETWORKS)}")
        mutating = arguments.get("mutating")
        if mutating is not None and not isinstance(mutating, bool):
            raise ValueError("mutating must be a boolean")
        visible_only = arguments.get("visible_only", False)
        if not isinstance(visible_only, bool):
            raise ValueError("visible_only must be a boolean")
        limit = arguments.get("limit", DEFAULT_SEARCH_RESULTS)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_SEARCH_RESULTS:
            raise ValueError(f"limit must be from 1 through {MAX_SEARCH_RESULTS}")

        query_tokens = _tokens(query)
        matches: list[tuple[int, CatalogEntry]] = []
        # An empty query browses the registry. A non-empty query the tokenizer
        # cannot read (Chinese, for example) matches no tool summary at all --
        # claiming every tool is a routing failure, not a broad search. Such a
        # query can still resolve a capability card below.
        if not query:
            candidates: Iterable[CatalogEntry] = self._entries
        elif not query_tokens:
            candidates = ()
        else:
            candidates = self._query_candidates(query_tokens)
        for entry in candidates:
            if modules and entry.module not in modules:
                continue
            if profiles and not any(profile in entry.profiles for profile in profiles):
                continue
            if levels and entry.semantic_level not in levels:
                continue
            if network is not None and entry.network != network:
                continue
            if mutating is not None and entry.mutating is not mutating:
                continue
            if visible_only and entry.name not in visible_names:
                continue
            matches.append((self._score(entry, query, query_tokens), entry))
        matches.sort(key=lambda item: (
            item[0],
            _BROWSER_LEVEL_PRIORITY.get(item[1].semantic_level, 4),
            item[1].name,
        ))
        returned = matches[:limit]
        result = {
            "query": query,
            "totalMatches": len(matches),
            "returnedCount": len(returned),
            "truncated": len(matches) > limit,
            "results": [
                entry.summary(visible=entry.name in visible_names, score=score)
                for score, entry in returned
            ],
            "schemaIncluded": False,
            "describeAction": "describe",
            "fingerprint": self.fingerprint,
            "conventionOnly": True,
            "authorityChanged": False,
        }
        # A capability is a whole-feature contract, not a tool: it rides beside
        # the summaries and names the deploy call that uses it.
        result.update(capability_section(query, limit=min(3, limit)))
        return result

    def describe(self, arguments: dict[str, Any], *, visible_names: set[str]) -> dict[str, Any]:
        name = arguments.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("name is required for action=describe")
        try:
            resolved = self.lookup.describe(name, view=visible_names)
        except UnknownToolName as error:
            raise ValueError(
                "name must exactly match one registered tool; use action=search first"
            ) from error
        entry = self._by_name[resolved["name"]]
        return {
            "tool": entry.detail(visible=entry.name in visible_names),
            "schemaIncluded": True,
            "fingerprint": self.fingerprint,
            "conventionOnly": True,
            "authorityChanged": False,
        }

    def index(self, arguments: dict[str, Any], *, visible_names: set[str]) -> dict[str, Any]:
        """One cheap map of the registry, by category.

        Retrieval is not free: a three-result `search` measures ~6,800 characters
        because every summary carries its concurrency and confirmation contract,
        and one `describe` of a modelling tool measures ~10,500. A caller that
        only needs to know WHAT EXISTS should not pay either. So this action
        answers with `name -- purpose` lines plus a small fixed metadata block:

        * no `category`: one line per category with its tool count and purpose,
          enough to choose a category without reading a single tool;
        * `category`: that category's entries, alphabetically, one compact line
          each, capped by `limit`.

        The map is derived from the same one-build index as `search`, so it
        cannot drift from the registry, and an unknown category is refused rather
        than silently answered as "everything".
        """
        category = arguments.get("category")
        if category is not None and (
            not isinstance(category, str) or category not in VALID_MODULES
        ):
            raise ValueError(f"category must be one of: {', '.join(VALID_MODULES)}")
        limit = arguments.get("limit", DEFAULT_INDEX_RESULTS)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_INDEX_RESULTS:
            raise ValueError(f"limit must be from 1 through {MAX_INDEX_RESULTS}")
        offset = arguments.get("offset", 0)
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValueError("offset must be a non-negative integer")

        grouped: dict[str, list[CatalogEntry]] = defaultdict(list)
        for entry in self._entries:
            grouped[entry.module].append(entry)

        if category is None:
            return {
                "index": "categories",
                "categories": [
                    {
                        "category": module,
                        "toolCount": len(grouped.get(module, ())),
                        "visibleCount": sum(
                            1 for entry in grouped.get(module, ()) if entry.name in visible_names
                        ),
                        "purpose": MODULE_PURPOSES.get(module, ""),
                    }
                    for module in VALID_MODULES
                ],
                "registryCount": len(self._entries),
                "lineFormat": "name -- purpose",
                "growth": "call again with category=<name> for that category's lines",
                "schemaIncluded": False,
                "describeAction": "describe",
                "fingerprint": self.fingerprint,
                "conventionOnly": True,
                "authorityChanged": False,
            }

        entries = sorted(grouped.get(category, ()), key=lambda item: item.name)
        page = entries[offset : offset + limit]
        next_offset = offset + len(page)
        truncated = next_offset < len(entries)
        return {
            "index": "category",
            "category": category,
            "purpose": MODULE_PURPOSES.get(category, ""),
            "toolCount": len(entries),
            "returnedCount": len(page),
            "offset": offset,
            "truncated": truncated,
            "nextOffset": next_offset if truncated else None,
            "lines": [
                {
                    "name": entry.name,
                    "purpose": _compact(entry.description, 100),
                    "network": entry.network,
                    "mutating": entry.mutating,
                    "visibleInCurrentView": entry.name in visible_names,
                }
                for entry in page
            ],
            "schemaIncluded": False,
            "describeAction": "describe",
            "fingerprint": self.fingerprint,
            "conventionOnly": True,
            "authorityChanged": False,
        }

    def apply(self, arguments: dict[str, Any], *, visible_names: set[str]) -> dict[str, Any]:
        action = arguments.get("action", "status")
        if action == "status":
            return self.status(visible_names=visible_names)
        if action == "search":
            return self.search(arguments, visible_names=visible_names)
        if action == "describe":
            return self.describe(arguments, visible_names=visible_names)
        if action == "index":
            return self.index(arguments, visible_names=visible_names)
        raise ValueError("action must be status, search, describe, or index")
