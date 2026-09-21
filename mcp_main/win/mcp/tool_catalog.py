from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

from mcp_main.win.mcp.concurrency import CONCURRENCY_CONTRACT_VERSION
from mcp_main.win.mcp.tool_views import (
    REST_REFERENCE_TOOL_NAMES,
    VALID_PROFILES,
    VALID_SEMANTIC_LEVELS,
    select_view_tools,
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
MAX_SEARCH_RESULTS = 12
DEFAULT_SEARCH_RESULTS = 8
#: The compact index is deliberately small: one line per category, or a bounded
#: page of lines for one category. 40 is above the largest category (browser, 70)
#: only when asked twice, which keeps a single answer in the low single-digit
#: kilobytes instead of echoing the whole registry.
MAX_INDEX_RESULTS = 40
DEFAULT_INDEX_RESULTS = 40

#: One sentence per category, so a caller can route without reading a tool.
MODULE_PURPOSES = {
    "control": "Discovery, catalog search, and this connection's tool-view state.",
    "browser": "Zero-quota browser leg: session, tabs, Feature Studio, thin-feature modelling, runner, exports.",
    "rest": "Onshape REST operations (quota-spending) and local state/geometry helpers.",
    "rest_reference": "Offline Onshape REST API reference: endpoints, schemas, auth, error codes.",
    "featurescript": "Offline FeatureScript reference: functions, types, guides, and source checks.",
    "documentation": "Project documentation index and section reads.",
}
_TOKEN = re.compile(r"[a-z0-9]+")
_BROWSER_LEVEL_PRIORITY = {
    "L5": 0,
    "L4": 1,
    "L2": 2,
    "L6": 3,
    None: 4,
    "L3": 5,
    "L1": 6,
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
    return tuple(_TOKEN.findall(value.lower().replace("_", " ").replace("-", " ")))


def capability_section(query: str, limit: int = 3) -> dict[str, Any]:
    """Matching whole-feature capability cards, with the call that uses one.

    Shared by every discovery entry (the catalog and `browser_discover_tools`)
    so a card cannot describe one invocation in one place and another elsewhere.
    """
    from onshape_browser_mode import capabilities

    matches = capabilities.search(query, limit=limit)
    if not matches:
        return {}
    for match in matches:
        match["invocation"]["tool"] = CAPABILITY_DEPLOY_TOOL
    return {"capabilities": matches, "capabilityInvocationTool": CAPABILITY_DEPLOY_TOOL}


def _compact(value: str, limit: int = 180) -> str:
    normalized = " ".join(value.split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


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


def _confirmation_mode(
    name: str,
    properties: dict[str, Any],
    required: tuple[str, ...],
) -> str:
    if "confirm_mutation" not in properties:
        return "none"
    if name == "onshape_eval_featurescript":
        return "budget_override"
    if "dry_run" in properties:
        return "non_dry_run"
    if "confirm_mutation" in required:
        return "always"
    return "runtime_required"


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
    """Immutable, one-build search index over the authoritative tool registry."""

    def __init__(self, tools: list[dict[str, Any]]) -> None:
        names = [tool.get("name") for tool in tools]
        if any(not isinstance(name, str) or not name for name in names):
            raise ValueError("every catalog tool must have a non-empty string name")
        duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
        if duplicates:
            raise ValueError(f"duplicate catalog tool names: {duplicates}")

        profile_names: dict[str, set[str]] = {}
        for profile in VALID_PROFILES:
            profile_names[profile] = {
                tool["name"]
                for tool in select_view_tools(tools, profile=profile, semantic_levels=None)
            }

        entries: list[CatalogEntry] = []
        postings: dict[str, set[str]] = defaultdict(set)
        for tool in tools:
            name = tool["name"]
            description = str(tool.get("description") or "")
            module = tool_module(name)
            profiles = tuple(profile for profile in VALID_PROFILES if name in profile_names[profile])
            semantic = _browser_semantics(name)
            schema = tool.get("inputSchema") or {}
            properties = schema.get("properties") or {}
            annotations = tool.get("annotations") or {}
            cost = tool.get("cost") or {}
            concurrency = cost.get("concurrency")
            if not isinstance(concurrency, dict):
                raise ValueError(f"tool {name} is missing concurrency metadata")
            network = str(cost.get("network", "offline"))
            if network not in VALID_NETWORKS:
                raise ValueError(f"tool {name} has unsupported network value: {network}")
            mutating = bool(cost.get("mutating", not annotations.get("readOnlyHint", True)))
            name_tokens = _tokens(name)
            search_tokens = frozenset(_tokens(
                " ".join((name, description, module, semantic.get("semanticName", "") if semantic else ""))
            ))
            required = tuple(schema.get("required") or ())
            confirmation_mode = _confirmation_mode(name, properties, required)
            entry = CatalogEntry(
                tool=tool,
                name=name,
                description=description,
                module=module,
                profiles=profiles,
                semantic=semantic,
                network=network,
                mutating=mutating,
                dry_run="dry_run" in properties,
                confirmation_exposed="confirm_mutation" in properties,
                confirmation_required=confirmation_mode in {"always", "non_dry_run", "runtime_required"},
                confirmation_schema_required="confirm_mutation" in required,
                confirmation_mode=confirmation_mode,
                side_effects=tuple(str(value) for value in cost.get("side_effects") or ()),
                concurrency=dict(concurrency),
                required=required,
                name_tokens=name_tokens,
                search_tokens=search_tokens,
            )
            entries.append(entry)
            for token in search_tokens:
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
        entry = self._by_name.get(name)
        if entry is None:
            raise ValueError("name must exactly match one registered tool; use action=search first")
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

