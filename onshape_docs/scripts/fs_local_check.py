#!/usr/bin/env python3
"""Zero-cost static check for FeatureScript files before uploading to Onshape.

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

Usage:
    python3 onshape_docs/scripts/fs_local_check.py [FILE...]     # files or directories
Exit code: 0 all pass, 1 any structural error.

Structural errors are hard stops; unknown symbols are warnings. Check output is
written to stderr; stdout stays clean for the MCP protocol stream.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX_PATH = ROOT / "reference" / "index" / "fsdoc" / "index.json"

# Keywords that are not function calls.
_KEYWORDS = {
    "annotation", "as", "const", "defineFeature", "export", "false", "for",
    "function", "if", "import", "is", "new", "precondition", "predicate",
    "return", "throw", "true", "var", "while",
}
_CALL_PREFIXES = ("q", "op", "ev", "to", "is", "f")  # naming-is-the-grammar


class FsFile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.text = path.read_text(encoding="utf-8")
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


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
        fs.warn("unreplaced {{PLACEHOLDER}} in source (runner substitutes at upload)")


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


def check_dangling_annotations(fs: FsFile, masked: str) -> None:
    """A 'Feature Type Name' annotation must be followed by its defineFeature."""
    for match in re.finditer(r'annotation\s*\{\s*"Feature Type Name"\s*:', masked):
        rest = masked[match.end() :]
        if not re.match(r"\s*export\s+const\b", rest):
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
        "type_values": {
            item["name"]: {
                v if isinstance(v, str) else v.get("name")
                for v in (item.get("values") or [])
            }
            for item in data.get("types", [])
        },
    }


def check_symbols(fs: FsFile, index: dict[str, set[str]] | None) -> None:
    if index is None:
        return
    defined = set(re.findall(r"\bfunction\s+(\w+)", fs.text))
    local_calls = defined | {"defineFeature", "println", "print", "size"}
    known = index["functions"] | index["predicates"]

    for match in re.finditer(r"\b([a-z][A-Za-z0-9_]*)\s*\(", fs.text):
        name = match.group(1)
        if name in _KEYWORDS or name in local_calls:
            continue
        if name.startswith(_CALL_PREFIXES) and name not in known:
            fs.warn(f"call '{name}(' not in vendored std index (mirror may lag; "
                    "verify against the live Feature Studio)")

    # Type references: 'is X', 'as X', ': X', 'var x : X', 'X.VALUE'.
    type_hits = set(re.findall(r"\b(?:is|as)\s+([A-Z]\w*)", fs.text))
    type_hits |= set(re.findall(r"\bvar\s+\w+\s*:\s*([A-Z]\w*)", fs.text))
    for name in sorted(type_hits - index["types"]):
        if name in index["constants"] or name in index["predicates"]:
            continue
        fs.warn(f"type '{name}' not in vendored std index")

    for match in re.finditer(r"\b([A-Z]\w*)\.([A-Za-z0-9_]+)\b", fs.text):
        type_name, member = match.group(1), match.group(2)
        values = index["type_values"].get(type_name)
        if values is not None and member not in values:
            fs.warn(f"'{type_name}.{member}' is not a documented value of {type_name}")


def check_file(path: Path) -> FsFile:
    fs = FsFile(path)
    masked = strip_strings_and_comments(fs.text)
    check_header(fs)
    check_brackets(fs, masked)
    check_dangling_annotations(fs, masked)
    check_define_feature(fs, masked)
    check_symbols(fs, _load_index(fs))
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
