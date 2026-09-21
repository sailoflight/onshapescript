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
| `gateway` (as shipped) | 25 | 63,467 | 15,866 |
| `profile=browser` | 40 | 89,527 | 22,381 |
| `semantic` (default) | 77 | 159,707 | 39,926 |
| `static` (registry) | 111 | 216,291 | 54,072 |

Compressing `gateway` instead of `semantic` buys a **24,060 token/step budget**;
instead of `static`, 38,206. (The pretty-printed audit in
`onshape_docs/verification/context-cost-surfaces-2026-09-21.json` reports slightly
larger figures for the same surfaces — 66,051 chars / 16,533 tokens for `gateway` —
because it indents the JSON; the wire that a client actually re-reads is the compact
form above.)

## 3. Measured lookup artifacts (model-facing)

| Layer | Artifact | Est. tokens |
|---|---|---|
| L1 | `mcp_tool_catalog action=index` category map | 371 |
| L1 | the same map, one category page (browser, 40 lines) | 2,743 |
| L2 | catalog `search`, 1 / 3 / 8 results | 1,101 / 2,382 / 2,685 |
| L2 | catalog `describe` a modelling tool | 3,054 |
| L2 | catalog `describe docs_section` | 880 |
| L1 | `docs_list` page list, section counts only (shipped default) | **1,811** |
| L1 | `docs_list` with every heading outline (`include_sections=true`) | **10,301** |
| L2 | `docs_search` (6 hits) / `docs_section` (one section) | 500 / 176 |
| L1 | `fs_quick_reference` | 2,325 |
| L2 | `fs_search` (8 hits) / `fs_get_function` (one name) | 623 / 2,354 |
| L1 | `onshape_api_list_tags` | 1,243 |
| L2 | `onshape_api_search` (8 hits) | 629 |

At the defaults used by the calculator (`30` steps, `P0=8k`, `g=600`) one extra
lookup round — prefix + map + one describe — costs **26,317 tokens**.

## 4. Findings

**F1. A round is an order of magnitude more expensive than a tool schema.**
Schemas measure **427–1,000 tokens/step** (measured per entry below); a round costs
~26.3k. So forcing a round for a tool that will actually be used is a bad trade. But
the asymmetry runs the other way too: because the schema rents for the *whole
remaining session* while a round is paid once, an entry needs an expected use of
**47%–110%** of sessions to pay for itself. The high end is
`browser_verify_feature_parameters` (1,000 tokens/step, break-even 1.10) and it is
still listed, because it is the *second leg of a round the caller has already paid*
— listing one leg and not the other converts a one-round edit into a two-round edit
(see F2). Conclusion: *list the tools used in nearly every session; look the rest up
per name.*

**F2. A prescribed chain must be listed completely or not at all.** The product
prescribes `docs_search → docs_section`, `fs_search → fs_get_function`,
`onshape_api_search → onshape_api_endpoint`. The 16-entry gateway measured on
2026-09-21 advertised the *first* element of each and not the second, so every
prescribed lookup was guaranteed to need a hidden-name round: the caller paid the
front half's rent **and** the round — strictly worse than listing both or neither.
The shipped set lists all six ends, and
`test_every_prescribed_lookup_chain_is_advertised_end_to_end` (plus the generic
`test_no_prescribed_chain_may_be_half_advertised` in `test_lookup_depth.py`) now
fails if a prescribed chain is cut in half again.

**F3. Artifact size × steps dominates layer depth.** The un-slimmed `docs_list` was
10,301 tokens — two thirds of the *entire* gateway surface — and read at step 2 it
rents 298,729 tokens over a 30-step tail, the equivalent of **~17.6 tools' worth of
surface**. Shipping the page-list default (1,811 tokens) cuts one read's rent to
52,519: **~246k tokens saved, more than fifteen tools would have saved**, with the
full outline still one `include_sections=true` away. `fs_get_function` got the same
treatment (prose bounded at 400 chars, `full=true` opt-in; its bulk is the field
list, so the entry stays ~2,354). Depth is not the lever; artifact size is.

**F4. Widening the surface is priced in per-name lookups.** Over a 30-step tail,
`gateway → semantic` costs as much as **26.5** single-name lookups,
`gateway → profile=browser` 7.2, `gateway → static` 42.1. So `mcp_tool_invoke`
(a per-name door, zero added rent) is the right general tool; expanding the surface
persistently is justified only in a session that will call many hidden names
(≳7 with the browser profile, ≳27 with the full semantic view).
*Expansion is a layer whose receipt is paid every step, not once.*

**F5. Coverage of the recorded task vocabulary.** Against the 14 real task
families recorded in `dev/fixtures-capture/` step lists and the 2026-09-21 sessions,
the pre-addition 16 entries finished **43% (6/14) with zero lookup rounds**. The 25
entries shipped now finish **86% (12/14)** for +5,514 tokens/step (10,352 → 15,866),
still **2.5× under `semantic`**. The two families that still pay a round are document
setup and runner capability runs, both rarer than the nine added, and both reachable
by `mcp_tool_invoke` (reasons recorded in `REJECTED_ENTRIES`).

**F6. The bridge's collapse/expand is a cheaper compression shape than the MCP's.**
Collapsing the win-wsl bridge's child surface (`bridge_library action="collapse"`) and
re-expanding later pays **one receipt per connection** — measured pretty-JSON receipts
of 211 tokens (`collapse`), 195 (`expand`), 68 (`status`) — and restores the *whole*
child surface in that single round. `mcp_tool_invoke` instead charges **one round per
hidden name** (26,317 tokens each at the defaults). So the two doors are not rivals:
collapse is right whenever the first child call is not immediate, and the per-name
door is right when it is. Session cost (30 steps, gateway child): expanded from the
start 475,980 tokens; collapsed and expanded at step 2 470,109; never expanded 9,000.
Break-even is **expand at step 2**: `expand at step 1 = 485,075`, `step 2 = 470,109`,
`step 3 = 455,143`, `step 5 = 425,211`, `step 10 = 350,381`, `step 30 = 51,061`.
*One round for a whole surface beats one round per name, but only once the surface is
actually needed.*

## 5. Recommendation

1. **Layer cap: 2.** Layer 0 = the advertised set (no round). Layer 1 = one bounded
   discovery answer (the 371-token map, or an exact-entry read of 176–880 tokens).
   Layer 2 = one `describe` (691–3,054) only when the index line cannot identify
   the name. **Never 3+**, and the first layer must never be a full dump.
2. **Entry policy: coverage-driven, chain-complete, break-even-gated.** Ship the
   nine entries of §4/F5 (16 → 25 entries, 86% zero-round coverage). Do not add an
   entry whose expected use is below its break-even; reach for it by
   `mcp_tool_invoke` instead.
3. **Prefer the per-name door over widening.** Keep `mcp_tool_view set` as an
   explicit decision, and quote its price (7.2–42.1 lookups) rather than treating it
   as free.
4. **Slim oversized L1 artifacts before shrinking the surface further.**
   `docs_list` first (`include_sections=false` default, page names + counts only),
   then `fs_get_function`/`fs_quick_reference` (best match + match list by default,
   `full=true` opt-in) — the same "compact by default, opt-in for the whole thing"
   rule already shipped for mutation row evidence.
5. **Tripwire the chain rule.** A test should fail when a prescribed chain is
   advertised half-way, so F2 cannot come back silently.
6. **Bridge layer: start collapsed unless the child is needed at step 1** (F6). One
   `expand` round restores the whole child surface; break-even is expand at step 2,
   so a session that never touches the child pays only its ~68-token `status`
   receipt, and a session that touches it at step 1 is cheaper not collapsing.

## 5b. What shipped against this analysis (2026-09-21)

| Lever | Change | Effect |
|---|---|---|
| Chain completeness (F2) | +6 chain ends, +3 workflow entries | gateway 16 → 25 entries; 3/4 half-chains → 0 |
| Artifact slimming (F3) | `docs_list` outline behind `include_sections=true`; `fs_get_function` prose behind `full=true` | one `docs_list` read 10,301 → 1,811 tokens |
| Rent price tag (F1/F4) | per-entry break-even printed by `dev/tools/lookup_depth.py` | every addition justified at 0.47–1.10 expected use |
| Chain tripwire (F2) | `test_every_prescribed_lookup_chain_is_advertised_end_to_end` | silent half-listing is now a test failure |
| Per-name door (F4) | `mcp_tool_invoke`, advertised in every mode | 95 unlisted names stay reachable for one round each |
| Bridge layer (F6) | collapse/expand receipts measured and modelled | expand-at-step-2 policy justified |

The surface grew on purpose: 15,866 tokens/step for 86% zero-round coverage, versus
10,352 for 43%, and still 2.5× cheaper than the default `semantic` view.

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
