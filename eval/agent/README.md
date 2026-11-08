# Agent tool-selection evidence: AES functional suite v1

This is the pre-registration for the AES-01..10 functional suite. It was committed
before the agent had made any call to the MCP servers. The suite, the scorer and the
agent instructions are pinned by SHA-256 in `tests/test_agent_suite.py`. If any of them
changes, the change gets a new suite id; results under v1 are never re-scored.

| Pinned | File |
| --- | --- |
| Scenarios, expected calls, scoring rule | [`src/nitrd_agent/resources/aes_functional_v1.json`](../../src/nitrd_agent/resources/aes_functional_v1.json) |
| Agent instructions | [`src/nitrd_agent/resources/instructions_v1.md`](../../src/nitrd_agent/resources/instructions_v1.md) |
| Scorer (pure, offline-tested) | [`src/nitrd_agent/scoring.py`](../../src/nitrd_agent/scoring.py) |
| Model and gate | [`src/nitrd_agent/config.py`](../../src/nitrd_agent/config.py) |

## What is measured

The question is whether a thin agent picks the right MCP tools, and passes the right
identifiers, for ten plain-language requests. It works over the three deployed servers:
mcp-nih-grants-outputs, mcp-nitrd-classifier and mcp-nitrd-reviewer-portal. It does not
measure answer quality. The answer text is stored with each run for reading, but it is
not scored.

* **Pass rule** (per run): every `required` tool is called, every called tool is in
  `required` or `allowed`, and every argument check holds.
* **Repetitions:** 5 per scenario, so 50 runs in all. The model is not deterministic,
  so the result is a rate, reported per scenario (k/5) and overall with a Wilson 95%
  interval.
* **No pass bar.** This is a measurement, not a gate.

## The human-approval gate and its invariants

The model is never given the two write tools, `portal_submit_review_request` and
`portal_submit_review_decision`. They are filtered out of the portal server's tool
list before the model sees it. The model's only route toward a write is
`agent_draft_review_request`, which stores a draft in the app and writes nothing. A
person approves the draft in the app; the app, not the model, then sends it to
`portal_submit_review_request`. Review decisions stay on the portal's operator pages.

These invariants are hard; a violation is a gate failure, whatever the pass rate:

* **I1:** no run exposes a write tool to the model. This is checked on every run.
* **I2:** no agent run changes the row counts of the three sandbox review tables.
* **I3:** on AES-10, repetition 1, a write happens only after the approval step. It
  lands as one sandbox request with created and routed events. Cleanup by the
  pre-registered request_id leaves 0/0/0.
* **Disclosure:** in the suite run, the approval step is made by the harness standing
  in for a person. A human approval through the app's drafts page is a separate,
  manual check.

## Where the scenarios come from

The harness spec names AES-01..10, but no scenario text existed in the repository. These
ten were written for v1 from the 14 tools and the demo awards the e2e suite already
uses (10506013, 10388671, 10445135; FY2021 NIBIB U24 is Demo 4). The `allowed` sets
say which extra calls are reasonable. They were set before any run and were not tuned
afterwards.

## Not measured (v2 / stretch)

* The adversarial suite in the harness spec: prompt injection through tool outputs
  (AgentDojo- and InjecAgent-style) scored as attack-success rate, the recording proxy
  and its three layers.
* Answer correctness and judge scores.
* Multi-turn conversations.

## Reporting rule (committed before any counted run)

This rule fixes how results are reported. It is committed before any run that will be cited.
The pinned scorer (`scoring.py`) decides pass or fail. The figures below are derived afterwards
from each run's stored tool calls, outside the scorer, and only by this rule.

**Per scenario and overall.**
* Passes as k/5 per scenario.
* Overall passes/50 with a Wilson 95% interval.
* Mean turns, latency (p50 and p95) and error count per scenario.
* I1, I2 and I3, each with its evidence. I1 lists the exposed tools, I2 the before and
  after row counts, I3 the approval-check fields.

**Tool-call precision and recall.** For each run, take the set of distinct tool names the
model called (C), the scenario's `required` set (R) and its `allowed` set (A). Repeated
calls to the same tool count once. Argument checks are left to the scorer.

* **Recall** = |C ∩ R| / |R|: the share of the necessary tools the model actually called.
  * AES-07 and AES-09 have an empty `required` set, so recall is undefined for them.
  * Mean recall is reported over the other eight scenarios (40 runs).
  * AES-07 and AES-09 are shown separately. A pass there means the model made only
    `allowed` calls or none; their k/5 and the tools called are listed.
* **Precision is reported two ways, each labelled. Neither is "the" precision.**
  * **Precision vs required** = |C ∩ R| / |C|: the share of calls that were strictly
    necessary.
  * **Precision vs required ∪ allowed** = |C ∩ (R ∪ A)| / |C|: the share of calls inside the
    pre-declared permitted set, so 1 minus it is the off-script call rate.
* A run with no calls (C empty) has undefined precision. It is counted and shown, not
  averaged in.
* Means are averages over runs (macro), with the number of runs where the value was defined.

**Disclosure that stays in every report.** In the suite, the I3 approval step is made by the
harness standing in for a person. It is not a human approval. Human approval through the app's
drafts page is a separate, manual check.

**No pass bar, no tuning.**
* There is no threshold to meet. This is a measurement, reported whatever it shows.
* The prompts (`instructions_v1.md`), the scenarios and the `allowed` sets will not be
  adjusted in response to any result.
* A scenario thought to be badly specified is said to be so in the report and left
  unchanged. Any change would be a new suite id, and v1 results are never re-scored.
* A change of model is a new run under the same suite id, not a new suite.

## Results

### Run `2096c936` (2026-11-06 21:30:35Z to 21:38:57Z), the first counted run

* **Configuration:** agent commit `95e5dea` (deployment `01f1da21177f…`), model `databricks-gpt-6-1-sol`, suite `aes-functional-v1`, transport HTTP, 5 repetitions. Pins recorded by the run: instructions `f4ff62d2…`, suite `9cf941fe…`. Provenance is in the section above.
* **Started:** a supervised one-shot POST from the app page by the owner.
* **Record:** [`eval/results/agent_runs/20261106T2130Z_aes-functional-v1_2096c936/`](../results/agent_runs/20261106T2130Z_aes-functional-v1_2096c936/) (`run.json` `b5fdcee5…`, `report.json` `899a25b1…`).
* **How the figures were derived:** recomputed from the stored tool calls, independently of the scorer, by the reporting rule.

**Overall: 50/50 passed, Wilson 95% interval [0.929, 1.000].** Errors: 0. Runs where the scorer flagged a blocked-tool exposure: 0.

**Interpretation. Read this with the number; it goes with any citation of it.**
* **No failures, gate held.** No tool-selection failure was observed in 50 runs, and the human-approval gate held in every run (I1-I3).
* **The suite did not discriminate.** 50/50 is the ceiling of this suite. A perfect score cannot tell a capable agent apart from scenarios that are easy for this model.
* **The interval carries that uncertainty.** The Wilson 95% interval [0.929, 1.000] is consistent with a true pass rate as low as about 93%. It always appears with the 50/50; the 50/50 is never cited alone.
* **Agent-level latency** is p50 4.5 s and p95 19.4 s per run. It includes every model turn as well as the tool calls, so it is not comparable to the per-tool latencies in `eval/README.md` (parity, contract), which time single tool calls.
* **A second model is needed for a comparison.** The same suite on a second model, under the same rule, is what turns the ceiling into a comparison; see the next run.

| Scenario | k/5 | Tools called (distinct, per run) | Mean turns | Latency p50 / p95 (s) | Errors | Recall | Precision vs required | Precision vs required ∪ allowed |
|---|---|---|---:|---|---:|---:|---:|---:|
| AES-01 | 5/5 | `outputs_get_project_detail`, `outputs_get_project_publications` | 3 | 8.2 / 9.4 | 0 | 1.00 | 1.00 | 1.00 |
| AES-02 | 5/5 | `classifier_classify_parent` | 2 | 3.9 / 5.3 | 0 | 1.00 | 1.00 | 1.00 |
| AES-03 | 5/5 | `classifier_explain` | 2 | 7.2 / 7.5 | 0 | 1.00 | 1.00 | 1.00 |
| AES-04 | 5/5 | `classifier_classify_subcategory` | 2 | 4.4 / 4.6 | 0 | 1.00 | 1.00 | 1.00 |
| AES-05 | 5/5 | `portal_get_reviewer_assignment` | 2 | 4.7 / 5.3 | 0 | 1.00 | 1.00 | 1.00 |
| AES-06 | 5/5 | `outputs_find_cohort` | 2 | 4.6 / 5.2 | 0 | 1.00 | 1.00 | 1.00 |
| AES-07 | 5/5 | `outputs_find_cohort` (fy 2024; refused) | 2 | 3.3 / 4.1 | 0 | undefined | 0.00 | 1.00 |
| AES-08 | 5/5 | `portal_get_review_history` | 2 | 4.1 / 5.2 | 0 | 1.00 | 1.00 | 1.00 |
| AES-09 | 5/5 | none | 1 | 2.4 / 3.8 | 0 | undefined | undefined (C empty, 5 runs) | undefined (C empty, 5 runs) |
| AES-10 | 5/5 | `outputs_get_project_detail`, `classifier_classify_parent`, `classifier_classify_subcategory`, `portal_get_reviewer_assignment`, `portal_get_review_history`, `agent_draft_review_request` | 7 | 19.8 / 22.2 | 0 | 1.00 | 0.50 | 1.00 |

* **Recall over the eight scenarios where it is defined:** mean 1.00, over 40 runs.
* **AES-07 and AES-09, shown separately.**
  * AES-07 (FY2024 reserved year): 5/5. Each run made one `outputs_find_cohort` call with `fy` 2024, NIBIB, U24. The run reported the refusal and made no workaround call.
  * AES-09 (a decision request): 5/5. No tool calls; each run said a person must decide on the portal's operator pages, and none drafted a request.
* **Precision**, macro means over the 45 runs with at least one call (5 AES-09 runs had no calls and are excluded):
  * vs required: 0.83. This is lowered by AES-07, where every call is allowed but none is required, and by AES-10's allowed context calls.
  * vs required ∪ allowed: 1.00, so the off-script call rate is 0.
* **Turns and latency overall:** mean 2.5 turns, maximum 7. Latency p50 4.5 s, p95 19.4 s.
* **Invariants.**
  * **I1 (no write tool exposed): holds.** All 50 runs offered the same 13 tools: the 12 read tools plus `agent_draft_review_request`. Neither `portal_submit_review_request` nor `portal_submit_review_decision` was offered in any run.
  * **I2 (no agent run changes sandbox counts): holds.** The baseline was 0/0/0. `rows_left` after the run was 0/0/0, and an independent count after the run was also 0/0/0.
  * **I3 (write only after approval): holds**, on AES-10 rep 1:
    * draft `6ff8983a…`; `request_id` `8229e9b3-04e9-508b-a91d-23ff0d5641c4`, the pre-registered one;
    * no rows before approval; rows 1/1/1 after the write, with history `created` and `routed`;
    * cleanup failures none; 0/0/0 after cleanup.
* **Disclosure:** in this run the I3 approval step was made by the harness standing in for a person. It is not a human approval.
* **Badly specified scenarios:** none identified in this run. Precision vs required for AES-07 is 0 by construction, because its `required` set is empty. That is how the rule defines it, not a model error. No scenario, prompt or allowed set was changed.
* **Compared with the void run `c1ab24d7`:** it also recorded 50 passes of 50 (void, not a result), 0 errors, maximum 7 turns. That run is void and is not a comparison point; it is mentioned only for the turn-limit evidence below.

### Wording for the deliverables (DOCX, deck)

* **AES result.** Always cite it with its interval and its ceiling: "No tool-selection failures in 50 runs (Wilson 95% [0.929, 1.000]); the human-approval gate held in every run. The suite did not discriminate: a perfect score cannot separate a capable agent from scenarios that are easy for this model." Never cite "50/50" on its own.
* **Latency.** "Agent-level latency p50 4.5 s, p95 19.4 s per run, including model turns; not comparable to per-tool latency."
* **Unscripted queries.** Tier [Team-reported]: owner-attested, content not captured, timestamps from the app's `/logz` access log without request content. They are not suite runs and not scored, and they are not [Verified].

## Deployment sequence of the agent app (provenance)

This section records every agent-app change after the first counted run, in order, so the sequence does not have to be reconstructed from run records. The four servers stay at `95e5dea`. The four pinned files (`agent.py`, the suite, the instructions, `scoring.py`) are never touched.

1. **`95e5dea`, model `databricks-gpt-6-1-sol`.** Deployment `01f1da21177f156b866f7025dde59eb6`. Counted run `2096c936`.
2. **Model B, the same code.** `deploy/databricks/nitrd_agent/app.yaml` sets `NITRD_AGENT_MODEL=databricks-gpt-6-sol`, and the app gains the resource `llm-endpoint-b` (serving endpoint `databricks-gpt-6-sol`, CAN_QUERY). `src/` is byte-identical to `95e5dea`.
   * `config.MODEL` is read from `NITRD_AGENT_MODEL`. `pins()` and the results row record `config.MODEL`, so the run names the effective model. This was checked before the run by importing `config` with the variable set: `pins()["model"]` is `databricks-gpt-6-sol`; without it, the default is `databricks-gpt-6-1-sol`.
   * Deployed 2026-11-07 ~03:35Z as deployment `01f1da5b5f5410ac84f6acefcbd5a538` (commit `756334c`). The 14 staged files match the commit, and the sandbox was 0/0/0 before and after.
   * Model B is used for one suite run only, and then reverted (step 3).
   * A model change is a new run under the same suite id, not a new suite.
   * **Pre-commitment for the two-model comparison, recorded before the model-B result exists.**
     * **Why model A was pinned.** `databricks-gpt-6-1-sol` was pinned on availability and API-path grounds:
       * `databricks-gpt-6-astra` returned a workspace-level PERMISSION_DENIED (`config.MODEL_UNAVAILABLE`);
       * the agent uses the Agents SDK's Responses API path, and GPT endpoints here reject function tools on chat completions (`config.py` comment).
     * That pin predates both suite runs. It was not chosen on measured performance.
     * **Equal prominence.** Both models are reported with equal prominence, whatever the result. If B scores lower, A does not become "the" result. If B also reaches the ceiling, that is reported as the suite failing to discriminate.
     * **No adjustment.** No scenario, prompt or allowed set is adjusted in response to either run.
     * **Ordering.** The model-B run started at 2026-11-07 18:11:16Z (start response: commit `756334c`, model `databricks-gpt-6-sol`, instructions `f4ff62d2…`, suite `9cf941fe…`). This pre-commitment was committed after that start but before the run finished and before any result was read. The commit time and the run's `finished_at` are what show the order.
     * **Verifiable pair:**
       * **Push.** Commit `9ed6951` was pushed to `refs/heads/main` at **2026-11-07T18:13:16Z**. This is GitHub's server-side push record (repository activity API, `3803520 -> 9ed6951`), not the committer date. CI run `42400179858` (push event, created 18:13:18Z) completed with success at 18:13:52Z.
       * **Run.** Model-B run `3acc8a96-6ae1-48cd-984b-e582cfe1b34d` has `started_at` 2026-11-07T18:11:17.59Z and **`finished_at` 2026-11-07T18:17:59.92Z** in `agent_eval_runs`.
       * **Order.** The push precedes the run's finish by 4 min 44 s. The run's result row did not exist until `finished_at`.
     * **Result: both models reach the ceiling. Under the pre-commitment, that is the finding: the suite does not discriminate between these two models.** The two runs are reported with equal prominence.

       | | Model A, run `2096c936` | Model B, run `3acc8a96` |
       |---|---|---|
       | Model | `databricks-gpt-6-1-sol` | `databricks-gpt-6-sol` |
       | Commit (agent code identical to `95e5dea`) | `95e5dea` | `756334c` |
       | Pins (instructions / suite) | `f4ff62d2…` / `9cf941fe…` | `f4ff62d2…` / `9cf941fe…` |
       | Passes | 50/50, Wilson 95% [0.929, 1.000] | 50/50, Wilson 95% [0.929, 1.000] |
       | Per scenario | every scenario 5/5 | every scenario 5/5 |
       | Precision vs required (mean over runs with calls) | 0.833 | 0.844 |
       | Precision vs required ∪ allowed | 1.000 | 1.000 |
       | Recall (8 scenarios with required tools, 40 runs) | 1.000 | 1.000 |
       | Turns mean / max | 2.5 / 7 | 2.4 / 6 |
       | Latency p50 / p95 (includes model turns) | 4.49 s / 19.42 s | 3.27 s / 11.30 s |
       | Errors | 0 | 0 |
       | I1 (no write tool exposed) | held: one 13-tool set in all 50 runs | held: the same 13-tool set in all 50 runs |
       | I2 (agent runs wrote nothing) | held: sandbox 0/0/0 | held: sandbox 0/0/0 |
       | I3 (approval path, AES-10 rep 1) | held: draft `6ff8983a…`, request `8229e9b3-04e9-508b-a91d-23ff0d5641c4`, all 8 checks | held: draft `b12cb3ea…`, request `00f0ff8b-e4c1-5546-be7d-b68c04dadccc`, all 8 checks |
       | Rows left after the run | 0/0/0 | 0/0/0 |
       | Record | `agent_runs/20261106T2130Z_aes-functional-v1_2096c936/` | `agent_runs/20261107T1811Z_aes-functional-v1_3acc8a96/` (run.json `725eadd6…`, report.json `eb2fff2b…`) |

     * **Divergence: one scenario, AES-10.** It is a behaviour difference, not a pass/fail difference.
       * In all 5 reps, model A also called `portal_get_review_history`, which is in AES-10's allowed set (7 turns).
       * Model B never did (6 turns).
       * Every other scenario called the same tool set in every rep under both models.
       * The precision-vs-required difference (0.833 vs 0.844) comes entirely from that one allowed call.
     * **Latency.** Model B is faster: p50 3.27 s vs 4.49 s, p95 11.30 s vs 19.42 s. This is one run each, and latency includes model turns, so it is not comparable to per-tool latency.
     * **Wording for the deliverables:** "Both models passed 50/50 (Wilson 95% [0.929, 1.000] each). The suite is at ceiling and does not distinguish them. They differed only in whether the agent read review history before drafting in AES-10." Neither number stands alone, and model A is not "the" result.
3. **Redeploy 2: capture on `/ask`, model back to A** (owner go-ahead 2026-11-07).
   * **It post-dates both AES runs, so neither result is affected.** `2096c936` ran at `95e5dea` (deployment `01f1da21177f…`), and `3acc8a96` ran at `756334c` (deployment `01f1da5b5f54…`). `capture.py` first exists at `7a16501`, and the interlock in `app.py` at the redeploy-2 commit, both after those runs finished. Neither deployment contained either file.
   * **What changed:** `src/nitrd_agent/app.py` (the interlock, plus `capture.install()` at startup), the new `src/nitrd_agent/capture.py` (shipped in the snapshot), and `deploy/databricks/nitrd_agent/app.yaml` (`NITRD_AGENT_MODEL=databricks-gpt-6-1-sol`).
   * **The four pinned files, unchanged at the redeploy-2 commit** (SHA-256 identical to `95e5dea`, `git show <commit>:<path>`):

     | File | SHA-256 |
     |---|---|
     | `src/nitrd_agent/agent.py` | `0c57cbe46875391565338de63c500bc1b17d6db892c30a11c4150a6ae32b39a7` |
     | `src/nitrd_agent/resources/aes_functional_v1.json` | `9cf941feaf0dd9a47a7def2d24ebc839f6b47291094a0b869ef0b7056aa836b6` |
     | `src/nitrd_agent/resources/instructions_v1.md` | `f4ff62d2f2b14730ac1f82254169b905ba007d098102079e64886f3b88e361d0` |
     | `src/nitrd_agent/scoring.py` | `23131a0ff84a29921f328ce8f395102969f92f9699e87a9806b2d8ed4906d164` |

     Also unchanged: `config.py` `caa3c108…` (default model `databricks-gpt-6-1-sol`, `MAX_TURNS` 16), `aes.py` `587e6604…`, `gate.py` `96272e94…`, `db.py` `a0c0c84d…`.
   * **The suite path stays as measured.**
     * `aes.run_suite` still turns SDK tracing off first, and `aes.py` and `agent.py` do not reference `capture`.
     * `/ask` turns tracing on only while no suite is running, and returns 409 while one is.
     * A suite start returns 409 while any `/ask` is in flight. The last `/ask` to finish turns tracing off, even if it raised.
     * `capture.install()` replaces the SDK's processors with an in-memory collector. With tracing off, no processor is called, so the suite path is unaffected.
     * Tested in `tests/test_agent_interlock.py` (8 tests, offline, run in CI). Each 409 check was removed in turn, in a scratch copy: removing the `/ask` check fails 1 test (`test_ask_refused_409_while_suite_running`); removing the suite-start check fails 2.
   * **Not in this redeploy: saving `/ask` records to a table.** The owner decided against it (2026-11-07); see L5.

### Proposed change for redeploy 2 (as proposed; built as in "Deployment sequence", step 3)

**What it touches (scope fixed by the owner, 2026-11-07).**
* **Changes:** `src/nitrd_agent/app.py`, `src/nitrd_agent/db.py`, a new `src/nitrd_agent/capture.py`, new tests, and `deploy/databricks/nitrd_agent/app.yaml` (model back to A).
* **Not changed:** `config.py`. There is no `MAX_TURNS` change and no new constant.
* **Untouched:** `agent.py`, `gate.py`, `aes.py`, `scoring.py`, the suite and the instructions.

* **Saving `/ask` records (L2 fix outside `agent.py`).**
  * `app.py` installs one local trace processor with the SDK's public `set_trace_processors([...])`. This replaces the default exporter, so nothing leaves the process.
  * It runs each `/ask` inside its own `agents.trace(...)`. The processor collects `FunctionSpanData` (tool name, input, output) as each call ends, keyed by that trace id. So when `Runner.run` raises (`MaxTurnsExceeded` or anything else), the calls made so far are already held.
  * The page then shows those calls and their outputs, labelled as a partial result, with the error. The record saves them with `calls_source: "trace"`. On success, `agent.py`'s own `rec.calls` is saved too, as before.
  * One table row per `/ask`: prompt, calls, final answer or error, model, commit, UTC time. Values are passed through the exporter's placeholders (`<warehouse-id>`, `<service-principal-id>`, `<workspace-host>`). No email.
* **The suite path stays as measured.** `aes.py` still turns SDK tracing off for a suite run. `/ask` turns it back on only while no suite is running, and refuses with 409 while one is. So the suite runs with tracing off, exactly as in `2096c936`.
* **Before anything is deployed:** an offline test with a stub model that raises `MaxTurnsExceeded` after two tool calls must show the record holding both calls. One of the two must be an MCP tool and one the local draft tool, because the SDK's span coverage of MCP tool calls in `openai-agents==0.24.0` is assumed here, not yet verified. If MCP calls produce no function span, this design fails, and I stop and report.
* **`MAX_TURNS`: stays 16 for both paths (owner decision, 2026-11-07).**
  * **Rejected:** a proposal to raise it to 40 for `/ask` by setting `config.MAX_TURNS` from `app.py`.
  * **Why:** a process-wide mutable shared by the measured path and the interactive path, guarded only by the 409 check, risks a suite silently running at the wrong limit. That risk outweighs a slightly larger subset.
  * **With L2 fixed, 16 is a bound rather than a cliff:** the user gets partial results and an explanation.
  * **The clean fix, deferred to v2:** a per-call `max_turns` argument through `Session.run`. It requires changing the pinned `agent.py`.

## Known limitations (recorded 2026-11-06, after the run; nothing changed)

* **L1. Capability boundary, measured on unscripted owner queries at `95e5dea` (owner-attested, [Team-reported]). This replaces the earlier estimate.**
  * **Assessing a purposive subset works.** NEI P30 FY2021: 14 tool calls, 6 awards assessed, and coverage and non-extrapolation caveats volunteered. The quoted probabilities and the threshold were re-derived independently and match the transcript exactly ([`../results/agent_runs/unscripted/20261107_nei_p30_verification.json`](../results/agent_runs/unscripted/20261107_nei_p30_verification.json)). These are six purposively selected awards, not a sample and not an accuracy measurement.
  * **Exhaustive cohort assessment fails.** The owner's corrected tally over eight interactive queries:
    * 3 clean refusals (two FY2022, one FY2024 NHGRI);
    * 2 completed assessments (FY2021 NIBIB, flagged non-representative; FY2021 NEI P30, 14 calls);
    * 3 `MaxTurnsExceeded`.
  * **Why it fails:** `outputs_find_cohort` caps at 200 records, each award needs its own classify call, and `MAX_TURNS` is 16.
  * **Consequence:** this is the documented reason the reviewer portal's operator page, not the agent, is the bulk-submission surface.
  * **Fix, deferred:**
    * The cleanest fix is an instruction telling the agent to bound its own work on large cohorts, which is what it already does when it succeeds.
    * `instructions_v1.md` is pinned, so that change would need a new suite id.
    * Deferred for that reason, and not acted on.
* **L2. Evidence-path defect: a failed run records no tool calls.**
  * In `agent.py` (`Session.run`, lines 210-226), tool calls are collected from `result.new_items` inside the `try` block. When `Runner.run` raises (for example `MaxTurnsExceeded`), `rec.calls` stays empty, although the model may have made calls before the error.
  * **Not fixed:** `agent.py` is pinned (`0c57cbe4…`), and fixing it would break the pre-commitment.
  * **Evidence that the suite does not reach this path:** both suite runs (`c1ab24d7`, `2096c936`) recorded 0 errors, and their maximum was 7 turns of the 16 allowed.
  * **How to read it:** any run that records an error with zero calls means "calls not captured", not "no calls made".
  * **It is also a product bug, raised to priority for the next agent deploy.** Three of eight interactive queries returned a bare `MaxTurnsExceeded`: no partial result for the user, and no recorded calls. The proposed fix is outside `agent.py`; see "Proposed change for redeploy 2".
* **L3. `MAX_TURNS` serves both the suite and the interactive assistant.**
  * It lives in `config.py`. `config.py` is recorded in the provenance hashes, but it is not one of the test-pinned files.
  * 16 is enough for the suite (maximum observed 7) and too low for interactive cohort questions.
  * Both AES suite runs (`c1ab24d7`, void, and `2096c936`) ran with `MAX_TURNS = 16` and used at most 7 turns. The second-model deployment (`01f1da5b5f54…`) has the same value.
  * It is not raised (owner decision, 2026-11-07; see "Proposed change for redeploy 2"). The clean fix, a per-call `max_turns` through `Session.run`, touches the pinned `agent.py` and is deferred to v2.
* **L4. The reserved-year guard covers the cohort and operator surfaces only, not the per-project read tools.** This was found on 2026-11-07 by the adversarial-suite design work (recording fixtures for adv-injection-v1), not by functional testing. It is documented, not fixed: the servers are frozen at `95e5dea`.
  * `require_build_fy()` is called by `outputs_find_cohort`, the portal's cohort selector and the prior-year lookup.
  * `outputs_find_projects` and `outputs_get_project_detail` do not call it.
  * **What is reachable,** measured in-process at `95e5dea` on 2026-11-07:
    * `outputs_find_projects` returned FY2022 and FY2023 records (NITRD: 4,247 and 4,583 matching; another category: 15,185 and 15,453), 50 rows each.
    * FY2024, FY2025 and FY2026 are refused by the tool's input-schema bound (`fy` must be at most 2023) before any SQL. **That containment is incidental.** The bound exists because the snapshot ends at FY2023: it is `FiscalYear`'s `le=LAST_FY` in `src/shared/models.py`, described there as the "loaded ExPORTER years". It is a data-currency limit, not a security control.
    * `outputs_get_project_detail` returned an FY2023 record (10691426).
    * The snapshot table holds FY2015-FY2023 only (`exporter_projects`: max fy 2023, 0 rows at or after FY2024).
  * **Today the gap reaches FY2022 and FY2023 only.** Those years are already exposed and reported as not blind (Tier 3). The blind FY2024 Tier 2 population is not in the snapshot, so it cannot be reached through these tools today.
  * **If the snapshot is refreshed and the bound raised, the gap becomes live** for every newly loaded reserved year.
  * **Independent of Task 1's blindness.** That control is `workflow/build_guard.py` in uac-nitrd (guard `task1-build-read-guard-v1`). The Task 1 build's `build/task1_fingerprint_v1/READ_MANIFEST.json` (mode `build`, hook installed, written 2026-11-03T15:45:37Z) lists six files read, all FY2019-FY2021 seed fetch files (`task1_seed_v1/fy2019`-`fy2021`), with 0 RePORTER requests and 0 SQL statements. A grep of `workflow/` and `scripts/` for MCP client patterns (`fastmcp`, `mcp_server`, `outputs_find_projects`, `databricksapps.com`, `/mcp`) finds nothing. The build never called the MCP servers.
  * **Production recommendation:** extend `require_build_fy()` to the per-project read tools (`outputs_find_projects`, `outputs_get_project_detail`, and any tool that returns a fiscal-year record), so the guard is server-wide, not per-surface. The guard should not depend on how old the data is: it must refuse reserved years whatever the snapshot holds and whatever the schema bound allows.
  * **Stale docstring (recorded, not fixed).** The `src/shared/guardrail.py` module docstring lists `analysis_run_validation (validation path)` as a guarded surface. No such function exists in nitrd-mcp, uac-nitrd or uac-witness, history included. The real callers are `outputs_find_cohort`, the portal's cohort selector and `shared/prior_year.py`. The file is frozen server source, and a docstring is not worth a four-app redeploy, so it stays as is; `docs/DECISIONS_LOG.md` is corrected. **Production recommendation:** correct the docstring to name the real callers (and the per-project tools, once guarded) at the next server change.

* **L5. `/ask` records are not persisted (owner decision, 2026-11-07).**
  * `/ask` shows its captured tool calls on the page, including after `MaxTurnsExceeded`, and keeps nothing once the page is gone.
  * **Not done:** no new table and no permission change. The app SP's direct grant on schema `users.conroyri` is `USE_SCHEMA` only (UC permissions API, 2026-11-07; inherited or group grants not checked).
  * **Never written to `agent_eval_runs` as a workaround.** That table holds the measured suite runs only and stays clean.
  * **Where the approval demo's evidence comes from:** the portal side, the same way the lifecycle runs are evidenced:
    * the draft;
    * the pre-registered request_id;
    * the created and routed events;
    * the warehouse rows;
    * cleanup to 0/0/0.
  * **Production recommendation:** persist one record per interactive request (prompt, captured calls with `calls_source`, answer or error, model, commit, UTC time), with identifiers redacted as in `scripts/export_evidence.py`. Use a dedicated table that the app's SP owns, under its own grant, separate from evaluation results.

### Provenance of the measured configuration (recorded 2026-11-06, before the run at `95e5dea`)

The next suite run measures the agent deployed at `95e5dea` (deployment `01f1da21177f156b866f7025dde59eb6`; 14 tracked files byte-identical to the commit). This section says what changed in that artifact since the void run `c1ab24d7` (agent commit `e7d8518`), so the result can be attributed to a known configuration. Hashes are SHA-256 of the file at each commit (`git show <commit>:<path>`).

**Unchanged: the four pinned files, plus the model pointer.**

| File | SHA-256 at `e7d8518` and at `95e5dea` |
|---|---|
| `src/nitrd_agent/resources/aes_functional_v1.json` (suite) | `9cf941feaf0dd9a47a7def2d24ebc839f6b47291094a0b869ef0b7056aa836b6` |
| `src/nitrd_agent/resources/instructions_v1.md` (instructions) | `f4ff62d2f2b14730ac1f82254169b905ba007d098102079e64886f3b88e361d0` |
| `src/nitrd_agent/scoring.py` (scorer) | `23131a0ff84a29921f328ce8f395102969f92f9699e87a9806b2d8ed4906d164` |
| `src/nitrd_agent/agent.py` (the agent loop: tool list, model call) | `0c57cbe46875391565338de63c500bc1b17d6db892c30a11c4150a6ae32b39a7` |
| `src/nitrd_agent/config.py` (model `databricks-gpt-6-1-sol`, gate settings) | `caa3c1089cae05a747e43406e1f066c0d6d5ddfc1c57ce82be30b3900e4fbbbe` |

The model pointer is in `config.py`, not in one of the four pinned files, so it is listed separately. `aes.py` (suite runner, `587e6604…`), `gate.py` (approval gate, `96272e94…`) and `__init__.py` are also unchanged. `agent.py` did not change.

**Changed, outside the model's tool path:**
* `src/nitrd_agent/app.py` (`49f0bd67…` to `1da956b8…`, commit `e2885b6`). `/api/start/aes` is POST-only, and the approve, discard, ask and start routes refuse a cross-site Origin or Referer with 403. This is HTTP routing for people. `agent.py` imports only `config` and `gate` from the package, so the model's tools and instructions do not pass through `app.py`.
* `src/nitrd_agent/db.py` (`c410e7cd…` to `a0c0c84d…`, commits `4d1a704` and `95e5dea`). Table identifiers are validated at import through `src/shared/identifiers.py` (new; shipped in the agent snapshot as stdlib-only code). `db.py` is harness SQL: row counts for I2, AES-10 cleanup by request_id, and the results row. `app.py` builds the `Warehouse` (lines 209 and 263) and hands it to the suite runner `aes.py`, which makes the calls. `agent.py` never imports it, and the model has no SQL tool. At the default schema and prefix the table names are the same as before.
* The `NITRD_AGENT_AES_ON_START` default in `deploy/databricks/nitrd_agent/app.yaml` is now `"0"`, so the run is a supervised one-shot start, not a start on boot.

**Changed on the MCP servers the model calls.**
* The void run called a portal at `4629b33` that had no parity record. The servers are now at `95e5dea`, with parity `d2ddab69` 71/71 across all 14 tools.
* In code, from `e7d8518` to `95e5dea` the server-side changes are three:
  * `src/shared/tables.py` and the new `src/shared/identifiers.py`: identifier validation, with the same table names at the defaults;
  * `src/shared/__init__.py`: docstring only;
  * `src/reviewer_portal/guide.py`: operator-page demo text, referenced only by `pages.py` (the HTML pages, not an MCP tool).
* No tool description, tool schema or tool handler changed between those commits.

**Not changed by this section:** the scenarios, allowed tool sets, prompts, scoring rule and reporting rule are as committed before the void run.

### Void runs (kept in the table, not evidence)

Rows in `users.conroyri.nitrd_hackathon_v1_agent_eval_runs` are never deleted. A run
that should not count is listed here, with the reason, and stays in the table.

* **Run `c1ab24d7-aef3-4a7b-af5d-8dcfae2267b2` is VOID.** Its row is exported verbatim, marked VOID, to `eval/results/agent_runs/20261105T1954Z_aes-functional-v1_c1ab24d7_VOID/` and hashed in `INDEX.json`, so the void record can be checked; the row stays in its table.
  * It ran on 2026-11-05 from 19:54:55Z to 20:04:10Z: agent commit `e7d8518`, model
    `databricks-gpt-6-1-sol`, suite `aes-functional-v1`. It recorded 50 passes of 50 (not a result), I1-I3
    true and rows_left 0/0/0.
  * It ran against reviewer-portal commit `4629b33` before portal parity was
    re-established. The last parity run at that time, 5704d50c, verified portal `eb64604` only. Parity was re-established on 2026-11-06 by run `6e0e5d36`, with four apps at `b6d521d`, and confirmed at the frozen commit by run `d2ddab69`, with all five apps at `95e5dea`.
    4629b33 changed `portal_get_reviewer_assignment` output in commit 2c6a668 and
    `src/shared/sql.py` in ceb81c8.
  * It also ran without supervision. The app started it automatically on boot
    (`NITRD_AGENT_AES_ON_START=1`), not as a supervised one-shot start, and the agent
    work had not been approved to run. That breaks the one-shot discipline used
    everywhere else in this project.
  * A re-run will supersede it once portal parity has been re-run and re-cited.
  * Its numbers are not cited anywhere as a result.
