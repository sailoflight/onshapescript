#!/usr/bin/env python3
"""How many lookup layers, and how many entry points? A cost model, not an opinion.

The question this answers
-------------------------
Compressing `tools/list` is never free: every layer that hides a name must be
re-opened with a round trip before the name can be called. So there is a real
trade-off between

* the **surface** (`tools/list`: what the client is handed), and
* the **rounds** (each lookup call, plus the artifact it returns).

Both are paid the same way in a stateless protocol: the tool list sits in the
prefix and is re-sent on EVERY step, and an artifact read at step *i* stays in
the transcript and is re-read on every later step. An artifact is therefore not
paid once -- it is **rent**: `chars x remaining_steps`. That single fact decides
the question, and it is why this tool measures artifact sizes instead of counting
tools.

The model
---------
For a session of ``n`` steps with base prefix ``P0`` tokens, prefix growth ``g``
per step, surface ``S`` tokens and a list of artifacts read at steps ``i``:

    input_tokens ~= sum over steps of (P0 + i*g + S + sum of artifacts read so far)

Two consequences fall straight out:

1. A compression is worth its extra rounds only while the **accumulated artifact
   rent** stays below the surface tokens it removed. With `gateway` vs `semantic`
   that budget is ~29.4k tokens; one `docs_list` answer alone (17.5k) eats more
   than half of it.
2. Layer depth is the wrong lever; **artifact size x steps** is the right one. A
   layer whose first answer is a full dump costs more than the tools it hid.

Measured constants
------------------
Sizes below are measured offline from the real code paths (no browser, no REST,
zero quota); the surface numbers come from the same measurement as
`onshape_docs/verification/context-cost-surfaces-2026-09-21.json`. Token counts
are ESTIMATES (4 characters per token; a CJK character counts as one token) --
there is no tokenizer on the deployment host, so nothing here claims a tokenizer
measurement.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "temp" / "browser-common-site"))

CHARS_PER_TOKEN = 4


def est_tokens(chars: int) -> int:
    """Documented ESTIMATE, kept in one place so no table drifts from the others."""
    return chars // CHARS_PER_TOKEN


def _rendered_size(payload: object) -> int:
    """Wire size: compact JSON, which is how `tools/list` crosses the bridge."""
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def _model_size(payload: object) -> int:
    """Model-facing size: the PRETTY text a model actually reads.

    A tool answer is sent twice -- once as `content[].text` (pretty JSON) and once
    as `structuredContent` (the same object) -- so the wire is roughly double the
    model-facing text. Rent is charged on what the model READS, so that is the
    number the model uses, and the duplicate is reported separately.
    """
    return len(json.dumps(payload, indent=2, ensure_ascii=False))


def measure_layers() -> dict[str, dict[str, object]]:
    """Measure every artifact a lookup layer can hand back, offline."""
    from mcp_main.win.mcp import server
    from mcp_main.win.mcp.tool_views import ToolViewState

    catalog = server.TOOL_CATALOG
    layers: dict[str, dict[str, object]] = {}

    def record(key: str, what: str, payload: object, *, layer: int, provenance: str,
               measure: str = "model") -> None:
        """Record one artifact.

        `measure` says which size is the currency for this row, because the two
        are not the same thing:

        * `model` (default): the pretty `content[].text` a model reads and that
          then stays in the transcript -- this is what rent is charged on;
        * `wire`: the compact JSON that crosses the bridge. Used for surfaces,
          because a tool list is not a tool ANSWER: the client receives the
          array and renders it its own way, so the compact array is the honest
          size of what was handed over.
        """
        chars = _model_size(payload) if measure == "model" else _rendered_size(payload)
        layers[key] = {
            "what": what,
            "chars": chars,
            "measured": measure,
            "modelChars": _model_size(payload),
            "wireChars": _rendered_size(payload),
            "estimatedTokens": est_tokens(chars),
            "layer": layer,
            "provenance": provenance,
        }

    previous_exposure = os.environ.get("ONSHAPE_MCP_TOOL_EXPOSURE")
    previous_profile = os.environ.pop("ONSHAPE_MCP_TOOL_PROFILE", None)
    try:
        for mode, profile, key in (
            ("gateway", None, "surface:gateway"),
            ("semantic", None, "surface:semantic"),
            ("static", None, "surface:static"),
            ("dynamic", "browser", "surface:profile=browser"),
        ):
            os.environ["ONSHAPE_MCP_TOOL_EXPOSURE"] = mode
            if profile:
                os.environ["ONSHAPE_MCP_TOOL_PROFILE"] = profile
            else:
                os.environ.pop("ONSHAPE_MCP_TOOL_PROFILE", None)
            listed = ToolViewState.from_environment(server.TOOLS).listed_tools()
            record(
                key,
                f"{len(listed)} tools advertised",
                {"tools": listed},
                layer=0,
                provenance="ToolViewState.listed_tools()",
                measure="wire",
            )
    finally:
        if previous_exposure is None:
            os.environ.pop("ONSHAPE_MCP_TOOL_EXPOSURE", None)
        else:
            os.environ["ONSHAPE_MCP_TOOL_EXPOSURE"] = previous_exposure
        if previous_profile is not None:
            os.environ["ONSHAPE_MCP_TOOL_PROFILE"] = previous_profile

    record("layer:catalog-index", "category map, 1 line per category",
           catalog.apply({"action": "index"}, visible_names=set()),
           layer=1, provenance="mcp_tool_catalog action=index")
    record("layer:catalog-page", "browser category, 40 lines",
           catalog.apply({"action": "index", "category": "browser"}, visible_names=set()),
           layer=1, provenance="mcp_tool_catalog action=index category=browser")
    for limit in (1, 3, 8):
        record(f"layer:catalog-search-{limit}", f"catalog search, {limit} results",
               catalog.apply(
                   {"action": "search", "query": "insert custom feature", "limit": limit},
                   visible_names=set()),
               layer=2, provenance=f"mcp_tool_catalog action=search limit={limit}")
    for name in ("browser_insert_custom_feature", "docs_section"):
        record(f"layer:describe-{name}", f"catalog describe {name}",
               catalog.apply({"action": "describe", "name": name}, visible_names=set()),
               layer=2, provenance=f"mcp_tool_catalog action=describe name={name}")

    def handler_payload(name: str, arguments: dict) -> object:
        return server.tool_result(name, arguments).get("structuredContent", {})

    for key, what, name, arguments in (
        ("layer:docs-list", "whole docs inventory, every section title", "docs_list", {}),
        ("layer:docs-search", "docs keyword search, 6 hits", "docs_search",
         {"query": "feature tree", "limit": 6}),
        ("layer:docs-section", "one exact docs section", "docs_section",
         {"page": "mcp-consumer", "section": "Required lookup order"}),
        ("layer:fs-quick-reference", "FS orientation digest", "fs_quick_reference", {}),
        ("layer:fs-search", "FS keyword search, 8 hits", "fs_search",
         {"query": "extrude", "limit": 8}),
        ("layer:fs-get-function", "one FS function entry", "fs_get_function",
         {"name": "extrude"}),
        ("layer:api-list-tags", "REST tag map, 42 tags", "onshape_api_list_tags", {}),
        ("layer:api-search", "REST keyword search, 8 hits", "onshape_api_search",
         {"query": "feature list", "limit": 8}),
    ):
        record(key, what, handler_payload(name, arguments),
               layer=1 if "list" in key or "quick" in key else 2,
               provenance=f"{name}{arguments if arguments else ''}")
    return layers


#: The documented lookup chains the product itself prescribes. A chain whose
#: SECOND element is not advertised turns its own prescribed workflow into a
#: guaranteed hidden-name round.
DOCUMENTED_CHAINS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("project docs", ("docs_search", "docs_section")),
    ("FeatureScript reference", ("fs_search", "fs_get_function")),
    ("REST reference", ("onshape_api_search", "onshape_api_endpoint")),
    ("MCP capability registry", ("mcp_tool_catalog", "mcp_tool_catalog")),
)

#: Tools the real recorded sessions actually drove, from the fixture step lists
#: under `dev/fixtures-capture/` (92 `browser_insert_custom_feature` steps across
#: six fixtures, plus the runner capabilities) and from the 2026-09-21 sessions.
#: Kept as data so the coverage arithmetic below is inspectable.
REAL_TASK_TOOLS: dict[str, tuple[str, ...]] = {
    "gridfinity / 4U bin build": (
        "browser_session", "browser_deploy_featurescript", "browser_insert_custom_feature",
        "browser_get_partstudio_features", "browser_export_step",
    ),
    "thin-feature rebuild + B-rep check": (
        "browser_deploy_featurescript", "browser_insert_custom_feature",
        "browser_read_feature_parameters", "browser_verify_feature_parameters",
        "browser_export_step",
    ),
    "parameter edit round": (
        "browser_edit_feature_parameters", "browser_verify_feature_parameters",
        "browser_read_feature_parameters",
    ),
    "row cleanup after a refused insert": ("browser_delete_feature",),
    "document/tab setup": (
        "browser_create_tab", "browser_activate_tab", "browser_rename_tab",
        "browser_get_page_tabs",
    ),
    "capability run (runner fixtures)": (
        "browser_run_project", "browser_create_document",
        "browser_deploy_and_apply_featurescript",
    ),
    "STEP export": ("browser_export_step",),
    "project docs lookup": ("docs_search", "docs_section"),
    "FeatureScript reference lookup": ("fs_search", "fs_get_function"),
    "REST reference lookup": ("onshape_api_search", "onshape_api_endpoint"),
    "quota check before a live call": ("onshape_api_quota",),
    "geometry readiness check": ("onshape_geometry_status",),
    "idle-session health probe": ("browser_session",),
    "feature-tree read (completeness signal)": ("browser_get_partstudio_features",),
}


#: Entries that close a documented chain or a workflow the recorded sessions
#: actually drove. Each is judged by `entry_analysis`, not by taste.
CANDIDATE_ENTRIES: dict[str, str] = {
    "docs_section": "second step of the prescribed docs chain (docs_search -> docs_section)",
    "fs_get_function": "second step of the prescribed FS chain (fs_search -> fs_get_function)",
    "onshape_api_endpoint": "second step of the prescribed REST chain (search -> endpoint)",
    "browser_edit_feature_parameters": "first leg of the parameter edit round",
    "browser_verify_feature_parameters": "second leg of the parameter edit round",
    "browser_read_feature_parameters": "the only write-free read of a feature's current values",
    "browser_delete_feature": "cleanup for a refused or timed-out insert",
    "browser_create_tab": "document/tab setup",
    "browser_activate_tab": "document/tab setup",
}


def tool_schema_chars() -> dict[str, int]:
    from mcp_main.win.mcp.server import TOOLS

    return {tool["name"]: _rendered_size({"tools": [tool]}) for tool in TOOLS}


def round_cost_tokens(*, prefix_tokens: int, step: int, growth_tokens: int,
                      surface_tokens: int, artifact_tokens: int) -> int:
    """What ONE extra round costs: the whole prefix is re-read, plus the artifact.

    This is the number that decides the question, because it is an order of
    magnitude above any single tool's schema rent.
    """
    prefix = prefix_tokens + step * growth_tokens + surface_tokens
    return prefix + artifact_tokens


def entry_analysis(*, n_steps: int, prefix_tokens: int, growth_tokens: int,
                   surface_tokens: int, rounds: int = 1) -> dict[str, dict[str, object]]:
    """Per candidate entry: rent, the round it removes, and the break-even use rate."""
    schemas = tool_schema_chars()
    listed = advertised("gateway")
    lookup_artifacts = 371 + 880  # category map + one describe: the two-step discovery
    result: dict[str, dict[str, object]] = {}
    for name, why in CANDIDATE_ENTRIES.items():
        if name not in schemas:
            continue
        schema_tokens = est_tokens(schemas[name])
        remaining = max(n_steps - 1, 1)
        rent = schema_tokens * remaining
        avoided = 0
        for index in range(rounds):
            step = 2 + index
            avoided += round_cost_tokens(
                prefix_tokens=prefix_tokens, step=step, growth_tokens=growth_tokens,
                surface_tokens=surface_tokens, artifact_tokens=lookup_artifacts,
            )
        result[name] = {
            "alreadyListed": name in listed,
            "why": why,
            "schemaTokensPerStep": schema_tokens,
            "rentTokensOverSession": rent,
            "avoidedRoundTokens": avoided,
            "breakEvenUseProbability": round(rent / avoided, 2) if avoided else None,
            "netTokensIfUsedOnce": avoided - rent,
        }
    return result


def widening_analysis(*, n_steps: int, prefix_tokens: int, growth_tokens: int,
                      layers: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    """Is widening the surface worth it, versus paying per-name rounds instead?"""
    gateway = int(layers["surface:gateway"]["estimatedTokens"])  # type: ignore[arg-type]
    remaining = max(n_steps - 1, 1)
    single = round_cost_tokens(prefix_tokens=prefix_tokens, step=2, growth_tokens=growth_tokens,
                               surface_tokens=gateway, artifact_tokens=371 + 880)
    result: dict[str, dict[str, object]] = {}
    for key in ("surface:semantic", "surface:profile=browser", "surface:static"):
        widened = int(layers[key]["estimatedTokens"])  # type: ignore[arg-type]
        extra_rent = (widened - gateway) * remaining
        result[key] = {
            "surfaceTokensPerStep": widened,
            "extraRentTokens": extra_rent,
            "equivalentSingleNameLookups": round(extra_rent / single, 1),
            "oneRoundCostTokens": single,
        }
    return result


#: A first-layer answer should be a map, not a dump. Above this many model tokens
#: the artifact costs more rent than the tools it took out of the surface.
SLIM_ARTIFACT_TOKENS = 2_000


def slim_potential(layers: dict[str, dict[str, object]], *, n_steps: int,
                   target_tokens: int = 600) -> dict[str, dict[str, object]]:
    """What an oversized lookup artifact costs, and what slimming it would save.

    An artifact read at step 2 rents for every later step, so a 10k-token first
    answer is paid ~`n-1` times. This is the same principle as the row-evidence
    compaction (`include_row_evidence`), applied to the reference layers.
    """
    result: dict[str, dict[str, object]] = {}
    remaining = max(n_steps - 1, 1)
    for key, layer in sorted(layers.items()):
        if not key.startswith("layer:") or layer["layer"] == 0:
            continue
        tokens = int(layer["estimatedTokens"])  # type: ignore[arg-type]
        if tokens <= SLIM_ARTIFACT_TOKENS:
            continue
        result[key] = {
            "what": layer["what"],
            "tokens": tokens,
            "rentIfReadEarly": tokens * remaining,
            "savingIfSlimmed": (tokens - target_tokens) * remaining,
            "equivalentToolsRemoved": round((tokens - target_tokens) / 550, 1),
        }
    return result


#: The set the model recommends, as the current gateway plus the entries that
#: close a prescribed chain or a workflow the recorded sessions drove. Kept
#: separate from CANDIDATE_ENTRIES so the recommendation is one inspectable list.
RECOMMENDED_ADDITIONS: tuple[str, ...] = (
    "docs_section",
    "fs_get_function",
    "onshape_api_endpoint",
    "browser_edit_feature_parameters",
    "browser_verify_feature_parameters",
    "browser_read_feature_parameters",
    "browser_delete_feature",
    "browser_create_tab",
    "browser_activate_tab",
)


def recommended_surface() -> dict[str, object]:
    """What the recommended entry set costs and what coverage it buys."""
    from mcp_main.win.mcp.server import TOOLS

    by_name = {tool["name"]: tool for tool in TOOLS}
    listed = advertised("gateway")
    added = [name for name in RECOMMENDED_ADDITIONS if name in by_name and name not in listed]
    current = _rendered_size({"tools": [by_name[name] for name in sorted(listed)]})
    widened = _rendered_size(
        {"tools": [by_name[name] for name in sorted(set(listed) | set(added))]}
    )
    covered = sorted(
        task for task, tools in REAL_TASK_TOOLS.items() if not (set(tools) - (set(listed) | set(added)))
    )
    remaining = sorted(
        task for task, tools in REAL_TASK_TOOLS.items() if set(tools) - (set(listed) | set(added))
    )
    return {
        "addedEntries": added,
        "currentToolCount": len(listed),
        "recommendedToolCount": len(set(listed) | set(added)),
        "currentSurfaceChars": current,
        "recommendedSurfaceChars": widened,
        "currentTokensPerStep": est_tokens(current),
        "recommendedTokensPerStep": est_tokens(widened),
        "addedTokensPerStep": est_tokens(widened) - est_tokens(current),
        "zeroRoundTasks": covered,
        "tasksStillNeedingALookup": remaining,
        "zeroRoundShare": round(len(covered) / len(REAL_TASK_TOOLS), 3),
    }


def advertised(mode: str = "gateway") -> set[str]:
    from mcp_main.win.mcp.server import TOOLS
    from mcp_main.win.mcp.tool_views import ToolViewState

    previous = os.environ.get("ONSHAPE_MCP_TOOL_EXPOSURE")
    os.environ["ONSHAPE_MCP_TOOL_EXPOSURE"] = mode
    try:
        return {tool["name"] for tool in ToolViewState.from_environment(TOOLS).listed_tools()}
    finally:
        if previous is None:
            os.environ.pop("ONSHAPE_MCP_TOOL_EXPOSURE", None)
        else:
            os.environ["ONSHAPE_MCP_TOOL_EXPOSURE"] = previous


def entry_rent_chars(mode: str) -> dict[str, int]:
    """What each advertised entry costs in the prefix, per step."""
    from mcp_main.win.mcp.server import TOOLS

    by_name = {tool["name"]: tool for tool in TOOLS}
    return {
        name: _rendered_size({"tools": [by_name[name]]})
        for name in sorted(advertised(mode))
    }


def coverage(mode: str = "gateway") -> dict[str, object]:
    """How many real tasks the advertised set can finish with ZERO lookup rounds."""
    listed = advertised(mode)
    zero_round: list[str] = []
    needs_lookup: dict[str, list[str]] = {}
    for task, tools in REAL_TASK_TOOLS.items():
        missing = sorted(set(tools) - listed)
        if missing:
            needs_lookup[task] = missing
        else:
            zero_round.append(task)
    return {
        "mode": mode,
        "advertised": sorted(listed),
        "tasks": len(REAL_TASK_TOOLS),
        "zeroRoundTasks": zero_round,
        "tasksNeedingALookup": needs_lookup,
        "zeroRoundShare": round(len(zero_round) / len(REAL_TASK_TOOLS), 3),
    }


def session_rent(n_steps: int, *, prefix_tokens: int, growth_tokens: int,
                 surface_tokens: int, artifacts: list[tuple[int, int]]) -> int:
    """Estimated input tokens over a session, under the prefix-rent model.

    ``artifacts`` is a list of ``(step_index_1_based, tokens)``: an artifact read
    at step *i* is re-read on steps *i..n*, which is exactly the rent that makes
    a small first answer worth more than a small tool list.
    """
    total = 0
    for step in range(1, n_steps + 1):
        carried = sum(tokens for index, tokens in artifacts if index <= step)
        total += prefix_tokens + step * growth_tokens + surface_tokens + carried
    return total


def compression_budget(layers: dict[str, dict[str, object]], *, narrower: str, wider: str) -> dict[str, int]:
    """Per-step budget a narrower surface buys, and what each artifact costs of it."""
    narrow = int(layers[narrower]["estimatedTokens"])  # type: ignore[arg-type]
    wide = int(layers[wider]["estimatedTokens"])  # type: ignore[arg-type]
    return {
        "narrowSurfaceTokens": narrow,
        "widerSurfaceTokens": wide,
        "budgetTokensPerStep": wide - narrow,
    }


def affordable_lookups(budget_tokens: int, artifact_tokens: int) -> float:
    """How many artifacts of this size the budget can carry at once (rent, per step)."""
    if artifact_tokens <= 0:
        return float("inf")
    return round(budget_tokens / artifact_tokens, 2)


def report(*, n_steps: int = 30, prefix_tokens: int = 8000, growth_tokens: int = 600) -> dict[str, object]:
    layers = measure_layers()
    budget = compression_budget(layers, narrower="surface:gateway", wider="surface:semantic")
    budget_static = compression_budget(layers, narrower="surface:gateway", wider="surface:static")
    affordability = {
        key: affordable_lookups(budget["budgetTokensPerStep"], int(layer["estimatedTokens"]))  # type: ignore[arg-type]
        for key, layer in sorted(layers.items())
        if key.startswith("layer:")
    }
    rent = {
        mode: session_rent(
            n_steps,
            prefix_tokens=prefix_tokens,
            growth_tokens=growth_tokens,
            surface_tokens=int(layers[f"surface:{mode}"]["estimatedTokens"]),  # type: ignore[arg-type]
            artifacts=[],
        )
        for mode in ("gateway", "semantic", "static")
    }
    return {
        "estimate": {
            "charsPerToken": CHARS_PER_TOKEN,
            "kind": "estimate, not a tokenizer measurement",
        },
        "session": {"steps": n_steps, "prefixTokens": prefix_tokens, "growthTokens": growth_tokens},
        "surfaces": {key: value for key, value in layers.items() if key.startswith("surface:")},
        "layers": {key: value for key, value in layers.items() if key.startswith("layer:")},
        "budgetVsSemantic": budget,
        "budgetVsStatic": budget_static,
        "affordableLookupsInBudget": affordability,
        "noLookupSessionRentTokens": rent,
        "documentedChains": [
            {"chain": name, "steps": list(tools), "secondStepAdvertised": tools[1] in advertised()}
            for name, tools in DOCUMENTED_CHAINS
        ],
        "coverage": coverage(),
        "entryRentChars": entry_rent_chars("gateway"),
        "entries": entry_analysis(
            n_steps=n_steps, prefix_tokens=prefix_tokens, growth_tokens=growth_tokens,
            surface_tokens=int(layers["surface:gateway"]["estimatedTokens"]),  # type: ignore[arg-type]
        ),
        "slimPotential": slim_potential(layers, n_steps=n_steps),
        "recommendedSurface": recommended_surface(),
        "widening": widening_analysis(
            n_steps=n_steps, prefix_tokens=prefix_tokens, growth_tokens=growth_tokens,
            layers=layers,
        ),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--steps", type=int, default=30, help="session length in model steps")
    parser.add_argument("--prefix-tokens", type=int, default=8000)
    parser.add_argument("--growth-tokens", type=int, default=600)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = report(n_steps=args.steps, prefix_tokens=args.prefix_tokens,
                    growth_tokens=args.growth_tokens)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    print("surfaces (chars / estimated tokens)")
    for key, value in result["surfaces"].items():  # type: ignore[union-attr]
        print(f"  {key:26} {value['chars']:>8} {value['estimatedTokens']:>8}  {value['what']}")
    print("\nlookup artifacts, and how many the gateway budget can carry at once")
    budget = result["budgetVsSemantic"]["budgetTokensPerStep"]  # type: ignore[index]
    print(f"  gateway vs semantic budget: {budget} tokens/step")
    for key, value in result["layers"].items():  # type: ignore[union-attr]
        afford = result["affordableLookupsInBudget"][key]  # type: ignore[index]
        print(f"  L{value['layer']} {key:28} {value['estimatedTokens']:>7} tokens  x{afford:<6} {value['what']}")
    print("\ndocumented lookup chains (does the prescribed 2nd step survive the cut?)")
    for chain in result["documentedChains"]:  # type: ignore[union-attr]
        mark = "ok" if chain["secondStepAdvertised"] else "NEEDS A HIDDEN-NAME ROUND"
        print(f"  {chain['chain']:26} {' -> '.join(chain['steps']):52} {mark}")
    cover = result["coverage"]  # type: ignore[assignment]
    print(f"\nzero-lookup coverage of recorded real tasks: {cover['zeroRoundShare']:.0%} "
          f"({len(cover['zeroRoundTasks'])}/{cover['tasks']})")
    for task, missing in cover["tasksNeedingALookup"].items():  # type: ignore[union-attr]
        print(f"  lookup needed: {task:44} missing {missing}")
    print("\ncandidate entries: rent vs the round it removes")
    for name, item in sorted(result["entries"].items(), key=lambda kv: kv[1]["breakEvenUseProbability"] or 0):
        if item["alreadyListed"]:
            continue
        print(f"  {name:34} +{item['schemaTokensPerStep']:>5} tok/step  "
              f"rent {item['rentTokensOverSession']:>7}  avoids {item['avoidedRoundTokens']:>6}  "
              f"break-even use {item['breakEvenUseProbability']:.0%}  ({item['why'][:44]})")
    print("\nwidening the surface vs paying per-name rounds")
    for key, item in result["widening"].items():
        print(f"  {key:26} +{item['extraRentTokens']:>9} tok over the tail  "
              f"= {item['equivalentSingleNameLookups']:>5} single-name lookups "
              f"(one round = {item['oneRoundCostTokens']} tok)")
    rec = result["recommendedSurface"]  # type: ignore[assignment]
    print(f"\nrecommended set: {rec['currentToolCount']} -> {rec['recommendedToolCount']} entries, "
          f"{rec['currentTokensPerStep']} -> {rec['recommendedTokensPerStep']} tokens/step "
          f"(+{rec['addedTokensPerStep']}), zero-lookup coverage "
          f"{result['coverage']['zeroRoundShare']:.0%} -> {rec['zeroRoundShare']:.0%}")
    for name in rec["addedEntries"]:  # type: ignore[union-attr]
        print(f"  + {name}")
    for task in rec["tasksStillNeedingALookup"]:  # type: ignore[union-attr]
        print(f"  still needs a lookup: {task}")
    print("\noversized lookup artifacts (rent at step 2, and what slimming saves)")
    for key, item in result["slimPotential"].items():
        print(f"  {key:26} {item['tokens']:>6} tok  rent {item['rentIfReadEarly']:>9}  "
              f"saving {item['savingIfSlimmed']:>9}  ~{item['equivalentToolsRemoved']} tools' rent")
    print(f"\nno-lookup session rent at {args.steps} steps: {result['noLookupSessionRentTokens']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
