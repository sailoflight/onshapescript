# Lookup depth and entry count: a cost model (2026-09-21)

> Question from the owner: *"every extra index layer lowers the advertised tool
> count but costs one more round — so how many layers of search (expansion counts
> as a layer) and how many entry points are actually right?"*
>
> This page answers with measured artifacts and explicit arithmetic. The
> calculator is `dev/tools/lookup_depth.py`; the invariants are gated by
> `dev/tests/test_lookup_depth.py`; every number below is reproducible offline at
> zero Onshape REST quota.

## 1. Why "one more round" is the expensive thing

A round trip does not cost an answer — it costs **the whole prefix**: the model
re-reads the conversation to decide what to do with the answer. And an artifact is
not paid once either: in a stateless protocol it stays in the transcript and is
re-read on every later step. Both the advertised tool list and every lookup answer
are therefore **rent**:

```
input_tokens(session) ~= sum over steps of (P0 + step*g + S + sum of artifacts read so far)
```

* `P0` base prefix, `g` growth per step, `S` advertised surface, artifacts rent from
  the step they are read.
* Two currencies are never mixed: a **surface** is measured as the compact JSON
  that crosses the wire, an **artifact** as the pretty `content[].text` a model
  actually reads (the response also carries `structuredContent`, i.e. the same
  object again — the wire is roughly double the model-facing text).

Token counts are ESTIMATES (4 characters per token). There is no tokenizer on the
deployment host, so nothing here claims a tokenizer measurement.

## 2. Measured surfaces (wire)

| Surface | Tools | Chars | Est. tokens/step |
|---|---|---|---|
| `gateway` | 16 | 41,410 | 10,352 |
| `profile=browser` | 40 | 89,527 | 22,381 |
| `semantic` (default) | 77 | 159,099 | 39,774 |
| `static` (registry) | 111 | 215,683 | 53,920 |

Compressing `gateway` instead of `semantic` buys a **29,422 token/step budget**;
instead of `static`, 43,568.

## 3. Measured lookup artifacts (model-facing)

| Layer | Artifact | Est. tokens |
|---|---|---|
| L1 | `mcp_tool_catalog action=index` category map | 371 |
| L1 | the same map, one category page (browser, 40 lines) | 2,743 |
| L2 | catalog `search`, 1 / 3 / 8 results | 1,101 / 2,382 / 2,685 |
| L2 | catalog `describe` a modelling tool | 3,054 |
| L2 | catalog `describe docs_section` | 880 |
| L1 | `docs_list` (whole inventory, every section title) | **10,262** |
| L2 | `docs_search` (6 hits) / `docs_section` (one section) | 500 / 176 |
| L1 | `fs_quick_reference` | 2,325 |
| L2 | `fs_search` (8 hits) / `fs_get_function` (one name) | 623 / 2,354 |
| L1 | `onshape_api_list_tags` | 1,243 |
| L2 | `onshape_api_search` (8 hits) | 629 |

At the defaults used by the calculator (`30` steps, `P0=8k`, `g=600`) one extra
lookup round — prefix + map + one describe — costs **20,803 tokens**.

## 4. Findings

**F1. A round is an order of magnitude more expensive than a tool schema.**
Schemas measure 427–1,000 tokens/step (below); a round costs ~20.8k. So forcing a
round for a tool that will actually be used is a bad trade. But the asymmetry runs
the other way too: because the schema rents for the *whole remaining session*
while a round is paid once, an entry needs an expected use of **60%–139%** of
sessions to pay for itself (`dev/tools/lookup_depth.py` prints the break-even per
candidate). Conclusion: *list the tools used in nearly every session; look the rest
up per name.*

**F2. A prescribed chain must be listed completely or not at all — and today
three of four are half-listed.** The product prescribes `docs_search →
docs_section`, `fs_search → fs_get_function`, `onshape_api_search →
onshape_api_endpoint`. The gateway advertises the *first* element of each and not
the second, so every prescribed lookup is guaranteed to need a hidden-name round:
the caller pays the front half's rent **and** the round. This is strictly worse
than either listing both or listing neither.

**F3. Artifact size × steps dominates layer depth.** `docs_list` is 10,262 tokens
— more than the entire gateway surface — and read at step 2 it rents ~297,600
tokens over a 30-step tail, the equivalent of **~17.6 tools' worth of surface**.
Slimming it to a page list (~600) saves ~280,000 tokens: more than removing
seventeen tools would. Depth is not the lever; artifact size is.

**F4. Widening the surface is priced in per-name lookups.** Over a 30-step tail,
`gateway → semantic` costs as much as **41.0** single-name lookups,
`gateway → profile=browser` 16.8, `gateway → static` 60.7. So `mcp_tool_invoke`
(a per-name door, zero added rent) is the right general tool; expanding the surface
persistently is justified only in a session that will call many hidden names
(≳17 with the browser profile, ≳41 with the full semantic view). *Expansion is a
layer whose receipt is paid every step, not once.*

**F5. Coverage of the recorded task vocabulary.** Against the 14 real task
families recorded in `dev/fixtures-capture/` step lists and the 2026-09-21
sessions, the current 16 entries finish **43% (6/14) with zero lookup rounds**.
Adding the nine entries that close the chains and the parameter/tab workflows takes
that to **86% (12/14)** for +5,514 tokens/step (10,352 → 15,866), still **2.5× under
`semantic`**. The two families that would still pay a round are document setup and
runner capability runs, both rarer than the nine.

## 5. Recommendation

1. **Layer cap: 2.** Layer 0 = the advertised set (no round). Layer 1 = one bounded
   discovery answer (the 371-token map, or an exact-entry read of 176–880 tokens).
   Layer 2 = one `describe` (691–3,054) only when the index line cannot identify
   the name. **Never 3+**, and the first layer must never be a full dump.
2. **Entry policy: coverage-driven, chain-complete, break-even-gated.** Add the
   nine entries in §4/F5 (16 → 25 entries, 86% zero-round coverage). Do not add an
   entry whose expected use is below its break-even; reach for it by
   `mcp_tool_invoke` instead.
3. **Prefer the per-name door over widening.** Keep `expand`/`mcp_tool_view` as an
   explicit decision, and quote its price (16.8–60.7 lookups) rather than treating
   it as free.
4. **Slim oversized L1 artifacts before shrinking the surface further.**
   `docs_list` first (`include_sections=false` default, page names + counts only),
   then `fs_get_function`/`fs_quick_reference` (best match + match list by default,
   `full=true` opt-in) — the same "compact by default, opt-in for the whole thing"
   rule already shipped for mutation row evidence.
5. **Tripwire the chain rule.** A test should fail when a prescribed chain is
   advertised half-way, so F2 cannot come back silently.

## 6. What this does not claim

* No tokenizer measurement; all token figures are the documented estimate.
* `P0` and `g` are parameters, not measurements: the prefix belongs to the client,
  and the MCP server cannot see it. The comparisons hold across the range because
  they are ratios of the same session shape; re-run with `--prefix-tokens` /
  `--growth-tokens` to test another shape.
* The task vocabulary is the 14 families recorded in this repository, not a
  survey of user behaviour. Adding a family changes the coverage percentages.
* Nothing here changes authority: entry count and layer depth are context
  routing. Every name stays callable, and every gate still answers.

## 7. Reproduce

```bash
python3 dev/tools/lookup_depth.py                      # the model, human-readable
python3 dev/tools/lookup_depth.py --json               # the same, machine-readable
python3 dev/tools/lookup_depth.py --steps 80 --prefix-tokens 40000 --growth-tokens 1500
PYTHONPATH=temp/browser-common-site python3 -m unittest discover -s dev/tests -p "test_lookup_depth.py"
```
