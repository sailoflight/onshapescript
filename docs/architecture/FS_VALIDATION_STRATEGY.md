# FeatureScript validation strategy

Authority: this page owns **how a FeatureScript source is checked before it
reaches Onshape**, and whether an existing external checker should be reused
instead of the in-repository one. It answers owner decision D4 in
`roadmap/FS_FIRST_CONTROLLING_ROUTE.md` and gap G3.

It does not own: deploy mechanics (`onshape_docs/experience/browser-modeling.md`
§13 for the capability contract), quota policy (`CLAUDE.md`), or the exact rule
set and its false-positive measurements (`onshape_docs/query/fs_check.py`
docstring, `onshape_docs/experience/featurescript.md`).

## 1. The authority ladder

Every layer below can say something about a source. Only the last two can say a
source is *correct*, and they are the only ones that cost anything.

| Layer | Cost | What it may claim | Owner |
|---|---|---|---|
| Local structural check | 0, offline, no login | Structure is broken; a deferred-failure shape will probably fail later; a symbol is absent from the vendored mirror | `onshape_docs/query/fs_check.py` (API), `onshape_docs/scripts/fs_local_check.py` (CLI), `fs_check_script` (tool) |
| Local source preview + symbol gate | 0 | A generated capability references only symbols the vendored reference contains; a card carries no implementation | `onshape_browser_mode/capabilities.py`, `dev/tests/test_capabilities.py` |
| Browser notice read | 0 REST, needs a session | The compiler's own messages, per paragraph, normalized to a stable code, with the offending source line | `onshape_browser_mode/diagnostics.py`, `browser_get_fs_compile_status`, `browser_fs_capture_diagnostic` |
| `featurespecs` on upload | ~3 REST | Signature and precondition only; the body is **not** compiled at save | `onshape_rest_api_mode`, guarded |
| `eval` / instantiate | 1–2 REST | Body semantics; instantiation is the only layer that executes the body | guarded, fixture-backed |

Two rules follow, and both are current behaviour:

- **All local findings are advisory.** Nothing local blocks an upload, because
  the vendored reference can lag the live server. An error-level finding does buy
  one deliberate second confirmation: the first call returns an
  `acknowledgementRequired` result listing the findings and writes nothing, and
  the caller re-issues the same call with `acknowledge_local_findings: true`.
  Warning-level findings never ask. The rule and the argument name are defined
  once in `onshape_docs/query/fs_check.py` (`acknowledgement_request`,
  `acknowledgement_missing`) and used by every path that writes a checked source:
  `browser_deploy_featurescript`, `browser_deploy_and_apply_featurescript`,
  `onshape_upload_feature_studio`, and the upload step of
  `onshape_run_validation_pipeline` (which aborts at that step having spent zero
  calls). `dev/tests/test_local_check_gate.py` pins the shared contract.
- **The browser compiler is the authority for body semantics.** It is free in
  REST quota, so the loop is: check locally, deploy, read the notice pane,
  normalize, summarize, retain. `onshape_browser_mode/diagnostics.py` implements
  the last three steps behind `browser_fs_capture_diagnostic`.

## 2. Why the local checker stays structural

`fs_check.py` is a scanner, not a parser, type checker, or lowering proof. It
reports structural errors and two deferred-failure rules plus symbol presence as
warnings. The two rules that shipped had **zero** false positives on the real
standard library; an argument-count rule produced 30 and a field-name rule 73,
so neither shipped (`onshape_docs/experience/featurescript.md`).

Two consequences:

1. The rule set grows only through the corpus gate
   (`dev/tools/fs_corpus_check.py`: 4/4 target samples flagged, 6/6 valid
   samples clean). A rule that cannot be measured against that corpus is not a
   rule, it is noise.
2. Anything needing scope, type, unit, query, control-flow, or import-graph
   analysis is **out of reach offline** from the vendored mirror alone. That is
   not a backlog item for the scanner; it is the browser compiler's job.
3. A false positive that is *found* is fixed, not tolerated. The symbol scan used
   to read the raw text, so a lowercase word followed by `(` inside an annotation
   string reported an unknown call; it now reads the masked text, with
   `test_static_guards` pinning both the silence and the still-reported genuine
   finding. That is the standard for every later rule.

## 3. External reuse survey (2026-09-19, search-level evidence)

The owner's instruction was: if an existing FeatureScript checker from GitHub or
the VS Code ecosystem can be reused, reuse it rather than building another one.

| Candidate | What the public material shows | What it would buy | Status |
|---|---|---|---|
| `reframe-systems.onshape-featurescript` — VS Marketplace | A third-party editor extension listed for VS Code ([marketplace](https://marketplace.visualstudio.com/items?itemName=reframe-systems.onshape-featurescript)) | Editor-side highlighting and whatever diagnostics it ships | Not wired. Needs a VS Code host, and its diagnostic set is undocumented in the public listing |
| "Adding FeatureScript Syntax Support to VSCode" | A community forum thread about syntax support ([forum](https://forum.onshape.com/discussion/30899/adding-featurescript-syntax-support-to-vscode)) | Grammar/TextMate material, not an analyzer | Not wired. Syntax only |
| "LSP support for FeatureScript?" | A community request thread ([forum](https://forum.onshape.com/discussion/comment/108358#Comment_108358)); the thread reads as a request precisely because no language server is published | An incremental analyzer with real diagnostics | None found. Nothing to reuse |
| `arjungandhi/featurescript` | A Go package and CLI named `featurescript` ([pkg.go.dev](https://pkg.go.dev/github.com/arjungandhi/featurescript)) | Unknown until its own source is read | Not wired. Purpose unverified; would need a Go toolchain and its own correctness evidence |
| Onshape Labs FeatureScript MCP Server | An official Onshape Labs server for text-to-code-to-CAD ([blog](https://www.onshape.com/en/blog/featurescript-mcp-server-enables-text-code-cad), [getting started](https://www.onshape.com/en/blog/get-started-featurescript-mcp-server)) | An adjacent official surface; possibly compile/diagnostic feedback | Not wired. It is a network/service path, which is the opposite of the 0-quota local pass this page is about |
| `hedless/onshape-mcp` | A third-party Onshape MCP server ([GitHub](https://github.com/hedless/onshape-mcp)) | Related work, not a checker | Not wired |

What was **not** done: nothing was downloaded, installed, or executed; no
account, key or quota was used. The evidence is public pages read as search
results, so every "what it would buy" cell above is unverified by execution and
is labelled as such. A future reader must treat the survey as a starting point,
not as a measurement.

Finding: **no offline, reusable FeatureScript type checker was found.** The
public ecosystem offers editor grammars and a community request for an LSP; the
official direction is a service. Neither gives this repository a zero-cost
pre-upload check that the vendored mirror cannot already give.

## 4. Decision

1. **Keep `fs_check.py` as the offline pass.** Do not vendor a third-party
   grammar to perform structural checks the scanner already performs with
   measured false-positive rates.
2. **Reuse on detection, never on installation.** If a real FeatureScript
   analyzer ever exists on this machine, it is a *candidate*, discovered the way
   the geometry backend discovers a converter: the caller selects by opaque
   candidate id, and the tool never installs one
   (`fdm_analysis/dependency_probe.py`,
   `browser_configure_geometry_backend`). This is the mechanism for the owner's
   "reuse it if it is there" instruction; it stays unwired until a candidate is
   actually present.
3. **A reused analyzer's findings are advisory too**, and must clear the same
   corpus gate before it can contribute an error rather than a warning.
4. **The locality invariant is enforced, not assumed**: the offline checker and
   the diagnostic normalizer import no network, process, or third-party runtime
   module (`dev/tests/test_fs_validation_strategy.py`).

## 5. Backlog for the "big checker" (ordered)

Each item names the gate it must pass before it may be reported.

| # | Item | Reachable offline? | Gate |
|---|---|---|---|
| 1 | More labeled corpus samples, including the version-drift cases excluded in P1c | **No** — needs real-machine apply runs | `dev/tools/fs_corpus_check.py` stays at 4/4 target and 6/6 valid |
| 2 | Unresolved `import(path : ...)` module check against the vendored library | **Delivered**: measured zero false positives over 1717 imports in 271 files, then the corpus gate | Keep the rate at zero; the version half stays unimplemented because the mirror ships a placeholder version |
| 3 | Duplicate-export check | **Rejected by measurement**: 34 of the 271 vendored files declare the same `export` name twice, because FeatureScript overloads by parameter types (`vector(x, y)` and `vector(x, y, z)`). Not a rule | n/a |
| 3b | Import-graph checks (unused imports, cycles) | Yes, but no measurable gate exists yet | Needs a corpus of labeled unused-import samples before it may report |
| 4 | Scope, type, unit, query, and effect analysis | **No** — this is the browser compiler's job | Would require the browser loop, not the scanner |
| 5 | Wire a detected external analyzer as candidate reports | Yes, but no candidate exists | Zero false positives on the corpus before it may report errors |

## 6. Verification mapping

| Claim | Evidence |
|---|---|
| The offline checker still catches the recorded failure classes | `test_static_guards.py`, `dev/tools/fs_corpus_check.py` |
| Deploy runs the local check, reports it as advisory, and asks once before writing error-level findings (never a gate, never silent) | `test_local_check_gate.py`, `test_quota_guards.py` (`LocalCheckRefusalTest`), `test_browser_mode.py` (`BrowserDeployTest`) |
| The browser loop normalizes codes, source lines, and groups, and retains a corpus | `test_fs_diagnostics.py`, `test_fs_notice_collector.py` |
| The scanner and normalizer stay local (no network, no process, no vendored runtime) | `test_fs_validation_strategy.py` |
| This page's survey claims carry links and stay labelled as unexecuted | `test_fs_validation_strategy.py` |

## Related documents

- `onshape_docs/experience/featurescript.md` — the verification ladder, rule
  history, and the live-verified lessons this page summarizes.
- `roadmap/FS_HYBRID_COMPILER_INTEGRATION.md` — "the existing local checker is
  structural"; the compiler cycle that would replace the scanner's limits.
- `roadmap/FS_FIRST_CONTROLLING_ROUTE.md` — D4 and G3.
- `architecture/OVERVIEW.md` — module boundaries for the owners named above.
