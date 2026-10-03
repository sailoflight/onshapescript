"""Geometry-leg interference checking for one STEP file (offline).

This module answers the one question a part count, an error-feature count, a
stable STEP sha256 and green FeatureScript assertions cannot answer: do two
solids actually overlap? Only the volume of the boolean intersection disproves
an interference, and this module gets it by running the pinned
``cadquery_interference.py`` converter through the configured geometry backend.
Nothing here touches the Onshape REST API or the browser.

Why the verdict vocabulary is larger than clean/interference
-----------------------------------------------------------
A check that never ran must not be able to read as a clean model, so the verdict
is deliberately explicit:

``clean``
    Boolean mode, the report parsed, and no pair had a positive intersection
    volume. Nothing else may claim this.
``interference``
    At least one pair overlaps with a volume above the contact floor. This is a
    positive finding, so it stays sound even when the pair list was truncated.
``candidates_only``
    Bounding-box mode. Boxes that overlap may be a designed interlock, so this
    mode can never decide; it reports the pairs worth measuring.
``indeterminate``
    The check was attempted and did not complete (missing STEP, converter
    failure, timeout, unreadable report, or a truncated candidate list with no
    finding). ``failures`` carries the reason.
``unavailable``
    No command could be assembled: the geometry backend is disabled, the
    configured template names no converter script, or the converter directory
    has no interference script. ``nextAction`` says how to enable it.

Reusing the configured backend
------------------------------
The interference converter runs the SAME interpreter the configured STEP
converter runs, with a different script: the derivation takes the configured
``argumentTemplate``, finds the element that ends in ``.py`` (the pinned STEP
converter), and replaces that one element with ``cadquery_interference.py`` in
the same directory. If the configured directory has no such script the result is
``unavailable`` rather than a guess, and an operator can always be explicit by
setting an ``interference.argumentTemplate`` block in the same configuration
file.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from fdm_analysis.configuration import load_command_geometry_config
from fdm_analysis.conversion.command import subprocess_platform_kwargs


CONFIG_PATH = Path(__file__).resolve().parent / "config" / "geometry-backend.json"
REPO_ROOT = Path(__file__).resolve().parents[1]
CONVERTER_NAME = "cadquery_interference.py"

MODES = ("aabb", "boolean")
DEFAULT_MAX_PAIRS = 4_000
MAX_PAIRS_CAP = 20_000
STEP_SUFFIXES = (".step", ".stp")

#: The converter prints its report to stdout for this output token, so a check
#: leaves nothing on disk and the tool stays genuinely read-only. A caller that
#: wants the report kept can run the converter itself with a real path.
OUTPUT_TOKEN = "-"

#: A report for a large assembly can carry thousands of candidate pairs. The
#: verdict never depends on this list (it comes from `counts`), so the returned
#: pairs are bounded and the omitted count is reported instead.
_MAX_REPORTED_PAIRS = 200

_ALLOWED_FIELDS = (
    "input",
    "output",
    "mode",
    "linear_tolerance_mm",
    "angular_tolerance_degrees",
    "max_pairs",
    "parts",
)

_ENABLE_HINT = (
    "onshape_geometry_status reports the candidate and "
    "onshape_configure_geometry_backend(backend='rest') writes the selection; "
    "the interference report then runs the same interpreter as the configured "
    "STEP converter. To point it at another command, add "
    '{"interference": {"argumentTemplate": [...]}} to '
    "onshape_rest_api_mode/config/geometry-backend.json."
)


def _step_path(value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("step_path is required")
    path = Path(value.strip())
    if not path.is_absolute():
        raise ValueError("step_path must be an absolute path")
    if path.suffix.lower() not in STEP_SUFFIXES:
        raise ValueError("step_path must name a .step or .stp file")
    return path


def _mode(value: Any) -> str:
    if value is None:
        return "boolean"
    if not isinstance(value, str) or value not in MODES:
        raise ValueError("mode must be 'aabb' or 'boolean'")
    return value


def _part_names(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("part_names must be a list of strings")
    names: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("part_names must contain non-empty strings")
        names.append(item.strip())
    return names


def _max_pairs(value: Any) -> int:
    if value is None:
        return DEFAULT_MAX_PAIRS
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_PAIRS_CAP:
        raise ValueError(f"max_pairs must be an integer from 1 through {MAX_PAIRS_CAP}")
    return value


def _tolerance(config: dict[str, Any], value: Any) -> float:
    if value is None:
        return float(config["linearToleranceMm"])
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        raise ValueError("tolerance_mm must be a positive number")
    return float(value)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _template_from_config(config: dict[str, Any]) -> dict[str, Any]:
    """Resolve the interference argv template, explicitly or by derivation."""

    explicit = config.get("interference")
    if isinstance(explicit, dict):
        template = explicit.get("argumentTemplate")
        if isinstance(template, list) and template and all(
            isinstance(item, str) for item in template
        ):
            return {
                "template": list(template),
                "source": "config",
                "reason": None,
                "converter": _template_converter(list(template)),
            }
        if explicit.get("enabled") is False:
            return {
                "template": None,
                "source": "config",
                "reason": "the interference block is disabled in the geometry backend configuration",
                "converter": None,
            }
    template = config.get("argumentTemplate")
    if not isinstance(template, list) or not template:
        return {
            "template": None,
            "source": None,
            "reason": "the geometry backend is disabled, so no converter command is configured",
            "converter": None,
        }
    index = next(
        (position for position, item in enumerate(template) if item.endswith(".py")),
        None,
    )
    if index is None:
        return {
            "template": None,
            "source": None,
            "reason": (
                "the configured argumentTemplate names no .py converter script, so the "
                "interference script cannot be derived from it"
            ),
            "converter": None,
        }
    script = template[index]
    separator = "\\" if "\\" in script else "/"
    directory = script.rsplit(separator, 1)[0] if separator in script else ""
    derived = f"{directory}{separator}{CONVERTER_NAME}" if directory else CONVERTER_NAME
    return {
        "template": [
            *(item for position, item in enumerate(template) if position < index),
            derived,
            "--input",
            "{input}",
            "--output",
            "{output}",
            "--mode",
            "{mode}",
            "--linear-tolerance-mm",
            "{linear_tolerance_mm}",
            "--parts",
            "{parts}",
            "--max-pairs",
            "{max_pairs}",
        ],
        "source": "derived",
        "reason": None,
        "converter": derived,
    }


def _template_converter(template: list[str]) -> str | None:
    return next((item for item in template if item.endswith(".py")), None)


def _location_available(converter: str | None) -> bool:
    """Whether the converter script exists on THIS side of the backend.

    The configured script usually lives in the WSL distribution while this
    process runs on Windows, so a POSIX path cannot be tested here. The check is
    therefore positive-only: an existing file on this side is proof, and a
    missing POSIX path is not evidence of absence -- the converter itself
    reports the truth, and a caller that gets a converter failure sees it.
    """

    if not converter:
        return False
    if converter.startswith("/"):
        return True
    return Path(converter).is_file()


def _command(template: list[str], *, values: dict[str, str]) -> list[str]:
    """Expand the template into argv, refusing an unsupported placeholder.

    One placeholder expands one argv element, so a repeatable flag cannot be
    expressed here; the converter therefore also accepts ``--parts`` as one
    comma-separated value and the derived template always uses that form.
    """

    command: list[str] = []
    for argument in template:
        residue = argument
        for field in _ALLOWED_FIELDS:
            residue = residue.replace("{" + field + "}", "")
        if "{" in residue or "}" in residue:
            raise ValueError("interference argumentTemplate contains an unsupported placeholder")
        command.append(argument.format(**values))
    if not {"{input}", "{output}"} <= set(template):
        raise ValueError("interference argumentTemplate must include {input} and {output}")
    return command



def plan_interference_check(
    *,
    step_path: Any,
    mode: Any = None,
    tolerance_mm: Any = None,
    part_names: Any = None,
    max_pairs: Any = None,
    config_path: Path = CONFIG_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Report exactly what a check would run, without running it."""

    del repo_root  # reserved for a caller that relocates the module-owned tree
    step = _step_path(step_path)
    resolved_mode = _mode(mode)
    config = load_command_geometry_config(config_path)
    resolved_tolerance = _tolerance(config, tolerance_mm)
    names = _part_names(part_names)
    cap = _max_pairs(max_pairs)

    template = _template_from_config(config)
    failures: list[str] = []
    backend: dict[str, Any] = {
        "name": config.get("name") or None,
        "version": config.get("version") or None,
        "executable": config.get("executable") or None,
        "configured": bool(config.get("enabled")),
        "templateSource": template["source"],
        "argumentTemplate": template["template"],
        "converter": template["converter"],
        "timeoutSeconds": config.get("timeoutSeconds"),
    }

    if not step.is_file():
        failures.append(f"the STEP file does not exist: {step}")
    if not config.get("enabled"):
        failures.append(
            str(template["reason"])
            or "the geometry backend is disabled, so no interference command can be assembled"
        )
    elif template["template"] is None:
        failures.append(str(template["reason"]))
    elif template["source"] == "derived" and not _location_available(template["converter"]):
        failures.append(
            f"the configured converter directory has no {CONVERTER_NAME}: {template['converter']}"
        )

    command: list[str] | None = None
    if config.get("enabled") and template["template"] is not None:
        # Building the argv is also the validation step: an unsupported
        # placeholder or a template without {input}/{output} is an operator
        # error and raises here instead of silently producing a wrong command.
        candidate = [
            str(config["executable"]),
            *_command(
                template["template"],
                values={
                    "input": str(step),
                    "output": OUTPUT_TOKEN,
                    "mode": resolved_mode,
                    "linear_tolerance_mm": str(resolved_tolerance),
                    "angular_tolerance_degrees": str(config["angularToleranceDegrees"]),
                    "max_pairs": str(cap),
                    "parts": ",".join(names),
                },
            ),
        ]
        if not failures:
            command = candidate

    available = not failures and command is not None
    return {
        "tool": "onshape_interference_check",
        "verdict": "planned" if available else "unavailable",
        "available": available,
        "mode": resolved_mode,
        "tolerance_mm": resolved_tolerance,
        "part_names": names,
        "max_pairs": cap,
        "stepPath": str(step),
        "stepSha256": _file_sha256(step) if step.is_file() else None,
        "report": "stdout",
        "command": command,
        "backend": backend,
        "network": "offline",
        "estimatedRequests": 0,
        "runs": available,
        "failures": failures,
        "nextAction": None if available else {"kind": "configure_existing", "hint": _ENABLE_HINT},
    }


def run_interference_check(
    *,
    step_path: Any,
    mode: Any = None,
    tolerance_mm: Any = None,
    part_names: Any = None,
    max_pairs: Any = None,
    config_path: Path = CONFIG_PATH,
    repo_root: Path = REPO_ROOT,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    """Run one interference report and map it to an explicit verdict."""

    plan = plan_interference_check(
        step_path=step_path,
        mode=mode,
        tolerance_mm=tolerance_mm,
        part_names=part_names,
        max_pairs=max_pairs,
        config_path=config_path,
        repo_root=repo_root,
    )
    base: dict[str, Any] = {
        "tool": "onshape_interference_check",
        "mode": plan["mode"],
        "tolerance_mm": plan["tolerance_mm"],
        "part_names": plan["part_names"],
        "max_pairs": plan["max_pairs"],
        "stepPath": plan["stepPath"],
        "stepSha256": plan["stepSha256"],
        "backend": plan["backend"],
        "command": plan["command"],
        "report": "stdout",
        "network": "offline",
        "estimatedRequests": 0,
    }
    if not plan["available"]:
        return {
            **base,
            "verdict": "unavailable",
            "parts": [],
            "pairs": [],
            "counts": {},
            "checkedPairs": 0,
            "exitCode": None,
            "reportSha256": None,
            "evidence": {"reason": "no interference command could be assembled"},
            "failures": plan["failures"],
            "nextAction": plan["nextAction"],
        }

    try:
        process = runner(
            plan["command"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=int(plan["backend"]["timeoutSeconds"] or 300),
            **subprocess_platform_kwargs(),
        )
    except subprocess.TimeoutExpired:
        return {
            **base,
            "verdict": "indeterminate",
            "failureClass": "converter_timeout",
            "parts": [],
            "pairs": [],
            "counts": {},
            "checkedPairs": 0,
            "exitCode": None,
            "reportSha256": None,
            "evidence": {"timeoutSeconds": plan["backend"]["timeoutSeconds"]},
            "failures": ["the interference converter exceeded its configured timeout"],
            "nextAction": {"kind": "raise_timeout_or_split", "hint": _ENABLE_HINT},
        }
    except OSError as error:
        # A configured executable that cannot be started (a missing wsl.exe, a
        # deleted interpreter) is a real state, not an exception for the caller:
        # report it as an explicit non-clean verdict.
        return {
            **base,
            "verdict": "unavailable",
            "failureClass": "converter_unavailable",
            "parts": [],
            "pairs": [],
            "counts": {},
            "checkedPairs": 0,
            "exitCode": None,
            "reportSha256": None,
            "evidence": {"executable": plan["backend"]["executable"]},
            "failures": [f"the interference converter could not be started: {error}"],
            "nextAction": {"kind": "fix_backend", "hint": _ENABLE_HINT},
        }

    stderr_tail = (process.stderr or "")[-1000:]
    if process.returncode != 0:
        return {
            **base,
            "verdict": "indeterminate",
            "failureClass": "converter_failed",
            "parts": [],
            "pairs": [],
            "counts": {},
            "checkedPairs": 0,
            "exitCode": process.returncode,
            "reportSha256": None,
            "evidence": {"stderrTail": stderr_tail},
            "failures": [f"the interference converter exited {process.returncode}: {stderr_tail}"],
            "nextAction": {"kind": "fix_backend", "hint": _ENABLE_HINT},
        }

    body = process.stdout or ""
    if not body.strip():
        return {
            **base,
            "verdict": "indeterminate",
            "failureClass": "report_missing",
            "parts": [],
            "pairs": [],
            "counts": {},
            "checkedPairs": 0,
            "exitCode": process.returncode,
            "reportSha256": None,
            "evidence": {"stderrTail": stderr_tail},
            "failures": ["the interference converter exited 0 but printed no report"],
            "nextAction": {"kind": "fix_backend", "hint": _ENABLE_HINT},
        }

    try:
        payload = json.loads(body)
        counts = payload["counts"]
        pairs = payload["pairs"]
        parts = payload["parts"]
    except (json.JSONDecodeError, KeyError, TypeError) as error:
        return {
            **base,
            "verdict": "indeterminate",
            "failureClass": "report_unreadable",
            "parts": [],
            "pairs": [],
            "counts": {},
            "checkedPairs": 0,
            "exitCode": process.returncode,
            "reportSha256": None,
            "evidence": {"stderrTail": stderr_tail},
            "failures": [f"the interference report could not be read: {error}"],
            "nextAction": {"kind": "fix_backend", "hint": _ENABLE_HINT},
        }

    interfering = int(counts.get("interfering", 0))
    truncated = bool(counts.get("pairs_truncated", False))
    if plan["mode"] == "aabb":
        verdict = "candidates_only"
    elif interfering > 0:
        verdict = "interference"
    elif truncated:
        verdict = "indeterminate"
    else:
        verdict = "clean"

    failures: list[str] = []
    if verdict == "indeterminate" and truncated:
        failures.append(
            "the candidate list was truncated at max_pairs, so this run cannot claim the model is clean"
        )

    return {
        **base,
        "verdict": verdict,
        "failureClass": "pairs_truncated" if failures else None,
        "parts": parts,
        "pairs": pairs[:_MAX_REPORTED_PAIRS],
        "pairsOmitted": max(0, len(pairs) - _MAX_REPORTED_PAIRS),
        "counts": counts,
        "checkedPairs": int(counts.get("checked_pairs", 0)),
        "candidates": int(counts.get("candidate_pairs", 0)),
        "exitCode": process.returncode,
        "reportSha256": hashlib.sha256(body.encode("utf-8")).hexdigest(),
        "reportBytes": len(body.encode("utf-8")),
        "evidence": {
            "converter": plan["backend"]["converter"],
            "templateSource": plan["backend"]["templateSource"],
            "stepSha256": plan["stepSha256"],
            "reportSchema": payload.get("schema"),
            "reportToleranceMm": payload.get("tolerance_mm"),
            "reportMode": payload.get("mode"),
            "stderrTail": stderr_tail,
        },
        "failures": failures,
        "nextAction": None,
    }
