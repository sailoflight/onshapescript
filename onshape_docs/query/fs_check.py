"""Zero-cost static check for FeatureScript sources before uploading to Onshape.

This is the analysis half; ``onshape_docs/scripts/fs_local_check.py`` is the
command-line wrapper and ``onshape_docs.query.fs_check`` is what the MCP runtime
imports, so a tool can check a script without a sys.path trick.

Onshape has no local compiler (compilation happens only on the server), and a
syntactically bad upload still costs quota with no diagnostics returned
(featurespecs comes back empty). This checker intercepts the failure classes
that actually burned quota during live verification:

- defineFeature closed early — body outside the `defineFeature(...)` call
  (the #1 silent failure: `precondition {...}) { ... };` compiles to 0 specs)
- a dangling `annotation { "Feature Type Name" : ... }` with no defineFeature
- unbalanced brackets, unreplaced {{PLACEHOLDER}}s
- symbol/type references absent from the vendored std index (warning level:
  the mirror may lag the live server, and local defs are fine)
- a definition-map call whose third argument cannot be a map, e.g.
  `opExtrude(context, id, 5)` — the server accepts this at save time and only
  reports `featureStatus=ERROR` at instantiation, so it must be caught locally
- arithmetic that mixes a dimensioned value with a plain number, e.g.
  `5 * millimeter + 2` — same deferred-failure shape
- an `onshape/std/...` import the vendored library does not contain (warning
  level: measured zero false positives over the 1717 imports in the library and
  this repository's own FeatureScript; only the `onshape/std/` prefix is checked,
  because a document-relative import is outside the mirror by design)

Why field-name and argument-count checks are deliberately absent: the vendored
reference's docblock extraction is incomplete. It records 6 fields for
`opBoolean` and 1 for `opDeleteBodies`, while the real definitions accept many
more, and it marks optional parameters inconsistently. Measured against the real
standard library (`onshape_docs/reference/raw/std-library/`), a field-name check
produced 73 false positives and an arity check 30 — on correct production code.
Both are therefore omitted rather than shipped noisy; they become viable only
once the reference's field extraction is complete.

Findings are advisory: nothing here blocks an upload, because the vendored index
can lag the live server. Structural findings are reported as errors and the rest
as warnings so a caller can weight them without re-deriving severity.

Called in-process by the MCP server (`fs_check_script`) and on files by
``onshape_docs/scripts/fs_local_check.py``, whose exit code is 0 when no
structural error is found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "reference" / "index" / "fsdoc" / "index.json"
# The vendored standard library itself, as opposed to the documented module index
# (`index.json` lists 210 modules while 271 files are vendored). Import checking
# must use what is actually on disk, or every undocumented module is a false
# positive: measured, the index-based set produced 99.
LIBRARY_PATH = ROOT / "reference" / "raw" / "std-library"

# Keywords that are not function calls.
_KEYWORDS = {
    "annotation", "as", "const", "defineFeature", "export", "false", "for",
    "function", "if", "import", "is", "new", "precondition", "predicate",
    "return", "throw", "true", "var", "while",
}
_CALL_PREFIXES = ("q", "op", "ev", "to", "is", "f")  # naming-is-the-grammar

# FeatureScript imports. `version` is optional in the language, so the path is
# scanned on its own and the version only when it is present.
_IMPORT_PATH = re.compile(r'import\(\s*path\s*:\s*"([^"]*)"')
_IMPORT_VERSION = re.compile(r'import\(\s*path\s*:\s*"([^"]*)"\s*,\s*version\s*:\s*"([^"]*)"')
_STD_PATH_PREFIX = "onshape/std/"

# FeatureScript unit constants. The vendored index carries most of these, but a
# fixed vocabulary keeps the unit check correct even when the index is missing.
# Only whole-number arithmetic directly joined to a unit is inspected, so a
# variable named like a unit cannot be mistaken for one.
_KNOWN_UNITS = frozenset({
    "millimeter", "centimeter", "meter", "kilometer", "inch", "foot", "yard",
    "thou", "mil", "mile", "radian", "degree", "revolution", "gram", "kilogram",
    "pound", "ounce", "tonne", "second", "minute", "hour", "ampere", "mole",
    "candela", "kelvin", "newton", "pascal", "joule", "watt", "volt", "ohm",
    "coulomb", "farad", "henry", "tesla", "weber", "hertz", "liter",
})

# A third positional argument that is definitely NOT a definition map. Anything
# else -- a variable, a call, a parenthesised expression -- may legitimately hold
# a map, so it is left alone. The check must never guess.
_MAP_INCAPABLE = re.compile(r'^(?:[+-]?\d|\[|true\b|false\b|"|\')')


class FsFile:
    """One FeatureScript source plus the findings collected for it."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.text = path.read_text(encoding="utf-8")
        self.errors: list[str] = []
        self.warnings: list[str] = []

    @classmethod
    def from_text(cls, text: str, name: str = "<script>") -> "FsFile":
        """Build from in-memory source so a tool can check without a temp file."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        instance = cls.__new__(cls)
        instance.path = Path(name)
        instance.text = text
        instance.errors = []
        instance.warnings = []
        return instance

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def as_result(self) -> dict[str, Any]:
        """JSON-friendly verdict for a tool result (advisory, never a gate)."""
        return {
            "name": str(self.path),
            "checked": True,
            "clear": not self.errors,
            "errorCount": len(self.errors),
            "warningCount": len(self.warnings),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def strip_strings_and_comments(text: str) -> str:
    """Mask string literals and comments so bracket scanning ignores them."""
    # Mask single-line comments and strings with spaces of equal length.
    masked = list(text)
    i, n = 0, len(text)
    while i < n:
        if text[i] == '"':
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == "\\":
                    j += 2
                else:
                    j += 1
            for k in range(i, min(j + 1, n)):
                masked[k] = " "
            i = j + 1
        elif text[i : i + 2] == "//":
            j = text.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):
                masked[k] = " "
            i = j
        elif text[i : i + 2] == "/*":
            j = text.find("*/", i)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                masked[k] = " "
            i = j
        else:
            i += 1
    return "".join(masked)


def strip_comments_only(text: str) -> str:
    """Mask comments but keep string literals, for annotation scanning.

    `strip_strings_and_comments` blanks string literals too, which hides the
    `"Feature Type Name"` marker that `check_dangling_annotations` must see.
    This variant blanks only comments (still skipping string literals so a `//`
    inside a string is not mistaken for a comment) and preserves positions, so
    indices line up with the fully-masked text used for bracket matching.
    """
    masked = list(text)
    i, n = 0, len(text)
    while i < n:
        if text[i] == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            i = j + 1
        elif text[i : i + 2] == "//":
            j = text.find("\n", i)
            j = n if j == -1 else j
            for k in range(i, j):
                masked[k] = " "
            i = j
        elif text[i : i + 2] == "/*":
            j = text.find("*/", i)
            j = n if j == -1 else j + 2
            for k in range(i, j):
                masked[k] = " "
            i = j
        else:
            i += 1
    return "".join(masked)


def check_brackets(fs: FsFile, masked: str) -> None:
    stack: list[tuple[str, int]] = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for i, ch in enumerate(masked):
        if ch in "([{":
            stack.append((ch, i))
        elif ch in ")]}":
            if not stack or stack[-1][0] != pairs[ch]:
                line = fs.text.count("\n", 0, i) + 1
                fs.error(f"unbalanced '{ch}' at line {line} (no matching opener)")
                return
            stack.pop()
    if stack:
        ch, i = stack[-1]
        line = fs.text.count("\n", 0, i) + 1
        fs.error(f"unbalanced '{ch}' at line {line} (never closed)")


def check_header(fs: FsFile) -> None:
    head = fs.text[:200]
    if not re.search(r"^FeatureScript (?:{{\w+}}|\d+);", head, re.MULTILINE):
        fs.error("missing 'FeatureScript <version>;' header")
    if not re.search(r'import\(path\s*:\s*"[^"]+",\s*version\s*:\s*"[^"]+"\)\s*;', head):
        fs.error("missing or malformed 'import(path : ..., version : ...);'")
    if re.search(r"\{\{\w+\}\}", fs.text):
        fs.error("unreplaced {{PLACEHOLDER}} in source (runner substitutes at upload)")


def find_matching(text: str, open_at: int) -> int | None:
    """Return index of the bracket matching text[open_at], or None if unbalanced."""
    opener = text[open_at]
    closer = {"(": ")", "[": "]", "{": "}"}[opener]
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == opener:
            depth += 1
        elif text[i] == closer:
            depth -= 1
            if depth == 0:
                return i
    return None


def check_define_feature(fs: FsFile, masked: str) -> None:
    """Verify every defineFeature(...) call ends ');' with its body inside."""
    for match in re.finditer(r"\bdefineFeature\s*\(", masked):
        open_at = masked.find("(", match.start())
        close_at = find_matching(masked, open_at)
        if close_at is None:
            fs.error("defineFeature(... never closed")
            continue
        between = masked[open_at : close_at + 1]
        tail = masked[close_at + 1 : close_at + 4].strip()
        if not tail.startswith(";"):
            line = fs.text.count("\n", 0, open_at) + 1
            fs.error(
                f"defineFeature at line {line}: ')' closes before the body block — "
                "body must be INSIDE the defineFeature(...) call, ending '});' "
                "(the pattern 'precondition {...}) { ... };' is a syntax error)"
            )
        if "precondition" not in between:
            fs.warn("defineFeature has no precondition block (valid but unusual)")


def check_dangling_annotations(fs: FsFile, text: str, masked: str) -> None:
    """A 'Feature Type Name' annotation must be followed by its defineFeature.

    `text` is the comments-masked source (string literals preserved, so the
    `"Feature Type Name"` marker is visible); `masked` is the fully-masked
    source used for bracket matching, so braces inside string literals cannot
    confuse the scan.
    """
    for match in re.finditer(r'annotation\s*\{\s*"Feature Type Name"\s*:', text):
        brace = text.find("{", match.start())
        close = find_matching(masked, brace) if brace != -1 else None
        if close is None:
            continue  # unbalanced braces are reported separately by check_brackets
        # After the annotation's closing brace must come `export const ...`
        # (the value string and any whitespace sit between the colon and here).
        if not re.match(r"\s*export\s+const\b", masked[close + 1 :]):
            line = fs.text.count("\n", 0, match.start()) + 1
            fs.error(
                f"dangling 'Feature Type Name' annotation at line {line}: must be "
                "followed by 'export const NAME = defineFeature(...)'"
            )


def _load_index(fs: FsFile) -> dict[str, set[str]] | None:
    if not INDEX_PATH.is_file():
        fs.warn(f"index not found at {INDEX_PATH}; skipping symbol check")
        return None
    import json

    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        fs.warn(f"index unreadable ({error}); skipping symbol check")
        return None
    return {
        "functions": {item["name"] for item in data.get("functions", [])},
        "predicates": {item["name"] for item in data.get("predicates", [])},
        "types": {item["name"] for item in data.get("types", [])},
        "constants": {item["name"] for item in data.get("constants", [])},
        "map_calls": _build_map_call_table(data),
        "modules": {
            path.name.lower() for path in LIBRARY_PATH.glob("*.fs")
        } if LIBRARY_PATH.is_dir() else set(),
        "type_values": {
            item["name"]: {
                v if isinstance(v, str) else v.get("name")
                for v in (item.get("values") or [])
            }
            for item in data.get("types", [])
        },
    }


def check_imports(fs: FsFile, comments_only: str, index: dict[str, Any] | None) -> None:
    """Warn about an `onshape/std/...` import the vendored mirror does not have.

    Measured false-positive rate: **zero**. Every one of the 1707
    `import(path : ...)` statements in the vendored standard library resolves to a
    vendored module, so an unknown std path is a real mistake (a typo there fails
    at save, after the upload has already cost quota), not mirror lag. Only the
    `onshape/std/` prefix is checked: a document- or Feature-Studio-relative import
    is outside the mirror by design and is never warned about.

    A *version* comparison is deliberately absent: the mirror ships a placeholder
    version string, so it cannot supply the comparison. `fs_check_version` compares
    cached observed live versions for free, which is the right place for it.
    """
    if index is None:
        return
    vendored = index.get("modules") or set()
    if not vendored:
        return
    for match in _IMPORT_VERSION.finditer(comments_only):
        path, version = match.group(1), match.group(2)
        if not version:
            fs.warn(f"import '{path}' has an empty version string")
    for match in _IMPORT_PATH.finditer(comments_only):
        path = match.group(1)
        if not path.startswith(_STD_PATH_PREFIX):
            continue
        name = path.rsplit("/", 1)[-1].lower()
        if name not in vendored:
            fs.warn(f"import '{path}' is not in the vendored standard library "
                    "(a typo here fails at save; the mirror may lag)")


def check_symbols(fs: FsFile, index: dict[str, set[str]] | None, code: str | None = None) -> None:
    if index is None:
        return
    # Scan the masked text. A call-shaped word inside a string or a comment is
    # not a call: the annotation `"Planar face (drill direction)"` must not
    # report `face(` as an unknown symbol, and a commented-out example must not
    # report its types either.
    code = strip_strings_and_comments(fs.text) if code is None else code
    defined = set(re.findall(r"\bfunction\s+(\w+)", code))
    local_calls = defined | {"defineFeature", "println", "print", "size"}
    known = index["functions"] | index["predicates"]

    for match in re.finditer(r"\b([a-z][A-Za-z0-9_]*)\s*\(", code):
        name = match.group(1)
        if name in _KEYWORDS or name in local_calls:
            continue
        if name.startswith(_CALL_PREFIXES) and name not in known:
            fs.warn(f"call '{name}(' not in vendored std index (mirror may lag; "
                    "verify against the live Feature Studio)")

    # Type references: 'is X', 'as X', ': X', 'var x : X', 'X.VALUE'.
    type_hits = set(re.findall(r"\b(?:is|as)\s+([A-Z]\w*)", code))
    type_hits |= set(re.findall(r"\bvar\s+\w+\s*:\s*([A-Z]\w*)", code))
    for name in sorted(type_hits - index["types"]):
        if name in index["constants"] or name in index["predicates"]:
            continue
        fs.warn(f"type '{name}' not in vendored std index")

    for match in re.finditer(r"\b([A-Z]\w*)\.([A-Za-z0-9_]+)\b", code):
        type_name, member = match.group(1), match.group(2)
        values = index["type_values"].get(type_name)
        if values is not None and member not in values:
            fs.warn(f"'{type_name}.{member}' is not a documented value of {type_name}")


def _build_map_call_table(data: dict) -> dict[str, str]:
    """Map every call whose third positional argument is a definition map.

    The reference documents this shape for every ``op*`` call and for the
    sketch/primitive builders (``newSketch``, ``skPoint``, ``cube``, ...). The
    value is the map parameter's documented name, used in the warning text.

    Only the shape is indexed. Field names and required-argument counts are
    intentionally not used -- see the module docstring for the measured reason.
    """
    table: dict[str, str] = {}
    for item in data.get("functions", []):
        if not isinstance(item, dict):
            continue
        match = re.search(r"\(([^)]*)\)", item.get("signature") or "")
        if not match:
            continue
        params = [part.strip() for part in match.group(1).split(",")]
        if len(params) < 3 or not params[2].endswith("is map"):
            continue
        table[item["name"]] = params[2].split(" is ")[0].strip()
    return table


def _call_argument_spans(
    masked: str, readable: str, open_at: int
) -> list[tuple[int, int]] | None:
    """Split one call's arguments at the top level, returning source spans.

    Structure comes from `masked`; `readable` (comments masked, string literals
    intact) decides whether a trailing argument is really absent. Testing that on
    the fully masked text would discard a string-literal argument, whose
    characters are blanks there.
    """
    close = find_matching(masked, open_at)
    if close is None:
        return None
    spans: list[tuple[int, int]] = []
    depth = 0
    start = open_at + 1
    for index in range(open_at + 1, close):
        char = masked[index]
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            spans.append((start, index))
            start = index + 1
    spans.append((start, close))
    if len(spans) > 1 and not readable[spans[-1][0]:spans[-1][1]].strip():
        spans.pop()
    return spans


def check_op_definitions(
    fs: FsFile, comments_only: str, masked: str, index: dict[str, Any] | None
) -> None:
    """Warn when a definition-map call passes something that cannot be a map.

    Warnings only: the vendored reference may lag the live server, and a wrong
    blocking decision costs more than a noisy warning. A third argument that is a
    variable or a call is never second-guessed -- only a literal that is
    definitely not a map is reported.
    """
    table = (index or {}).get("map_calls") or {}
    if not table:
        return
    for match in re.finditer(r"\b([A-Za-z_]\w*)\s*\(", masked):
        name = match.group(1)
        map_param = table.get(name)
        if map_param is None:
            continue
        open_at = masked.find("(", match.start())
        spans = _call_argument_spans(masked, comments_only, open_at)
        if spans is None or len(spans) < 3:
            continue
        third = comments_only[spans[2][0]:spans[2][1]].strip()
        if _MAP_INCAPABLE.match(third):
            fs.warn(
                f"{name}(...): the third argument is the '{map_param}' map, "
                f"but {third.splitlines()[0][:24]!r} is not a map literal"
            )


_UNIT_ALTERNATION = "|".join(sorted(_KNOWN_UNITS, key=len, reverse=True))
# value-with-units (+|-) plain number
_UNIT_SUM = re.compile(
    rf"\b\d+(?:\.\d+)?\s*\*\s*(?:{_UNIT_ALTERNATION})\b\s*[+\-]\s*\d+(?:\.\d+)?(?!\s*[*/])"
)
# plain number (+|-) value-with-units
_UNIT_SUM_REVERSED = re.compile(
    rf"\b\d+(?:\.\d+)?\s*[+\-]\s*\d+(?:\.\d+)?\s*\*\s*(?:{_UNIT_ALTERNATION})\b"
)


def check_unit_mixing(fs: FsFile, comments_only: str) -> None:
    """Warn on arithmetic that adds a dimensioned value to a plain number.

    ``5 * millimeter + 2`` mixes a length with a dimensionless number. FeatureScript
    defers that to instantiation, so it is invisible at save time. Heuristic, and
    therefore a warning: only literal ``number * unit`` joined to a literal number
    is reported, and a following ``*`` excludes genuine unit arithmetic such as
    ``5 * millimeter + 2 * centimeter``.
    """
    for pattern in (_UNIT_SUM, _UNIT_SUM_REVERSED):
        for match in pattern.finditer(comments_only):
            fs.warn(
                "mixed dimensions: "
                f"{match.group(0).strip()!r} combines a value with units and a "
                "plain number"
            )


def check_file(path: Path) -> FsFile:
    """Check one FeatureScript file on disk."""
    return check_source(FsFile(path))


def check_source(fs: FsFile) -> FsFile:
    """Run every check against one loaded FsFile, filling its findings."""
    masked = strip_strings_and_comments(fs.text)
    comments_only = strip_comments_only(fs.text)
    index = _load_index(fs)
    check_header(fs)
    check_brackets(fs, masked)
    check_dangling_annotations(fs, comments_only, masked)
    check_define_feature(fs, masked)
    check_symbols(fs, index, masked)
    check_imports(fs, comments_only, index)
    check_op_definitions(fs, comments_only, masked, index)
    check_unit_mixing(fs, comments_only)
    return fs


def main(argv: list[str]) -> int:
    targets: list[Path] = []
    for arg in argv[1:]:
        p = Path(arg).resolve()
        if p.is_dir():
            targets.extend(sorted(p.rglob("*.fs")))
        else:
            targets.append(p)
    if not targets:
        print(f"usage: {argv[0]} FILE...|DIR...", file=sys.stderr)
        return 2

    structural_failures = 0
    for path in targets:
        fs = check_file(path)
        tag = "PASS" if not fs.errors else "FAIL"
        if fs.errors:
            structural_failures += 1
        print(f"[{tag}] {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
        for error in fs.errors:
            print(f"    ERROR  {error}")
        for warn in fs.warnings:
            print(f"    WARN   {warn}")
    print(f"\n{len(targets)} file(s), {structural_failures} structural error(s); "
          "structural errors MUST be fixed before upload (they waste quota).",
          file=sys.stderr)
    return 1 if structural_failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
