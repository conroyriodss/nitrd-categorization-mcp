# Mutation table: portal change series a-e (review artifact for the 2026-11-12 deploy gate)

All rows re-run fresh on 2026-11-10 by Genie Code, in `/tmp` copies made with `git archive`, `PYTHONPATH=<copy>/src`, never in the workspace. Interpreter: `/tmp/nitrd-dev` (uv.lock install).

Two kinds of mutation:
* **Revert**: the step's commit with its `src/` files put back to the parent commit; tests as of that commit; only the test files the commit touched are run. Shows the step's tests fail without the step.
* **Variant**: one targeted edit to `src/reviewer_portal/pages.py` at HEAD `2b8f6a8` (code identical to `64e7f8a`); run against `test_portal_review.py`, `test_portal_card_terms.py`, `test_portal_request_view.py`, `test_portal_submission.py`. Shows a specific plausible regression is caught.

"Caught by" lists the failing tests; a parametrised test is counted once per failing case.

| Step | Change | Mutation | Caught by | Result |
| --- | --- | --- | --- | --- |
| a F3 | not-NITRD card: "outweighed" relabel; no "Against: none" | revert `fc6dfd5` | `test_portal_review::test_not_nitrd_and_new_core_cards` | 1 failed, 38 passed |
| a F3 | | variant: not-NITRD branch removed (`if True:` on the NITRD wording) | `test_portal_card_terms::test_near_threshold_not_nitrd_keeps_f3_wording` | 1 failed, 102 passed |
| b F4 | prior-year history above the rationale | revert `278e08b` | `test_portal_review::test_prior_year_history_sits_above_the_rationale` | 1 failed, 39 passed |
| b F4 | | variant: history block moved back below the rationale | `test_portal_review::test_prior_year_history_sits_above_the_rationale` | 1 failed, 102 passed |
| c F1 | PCA list: rank and matched terms, no raw score | revert `8a708a8` | `test_portal_review::test_nitrd_card_shows_call_pcas_rationale_prior_year` | 1 failed, 39 passed |
| c F1 | | variant: score shown beside the rank | `test_portal_review::test_nitrd_card_shows_call_pcas_rationale_prior_year` | 1 failed, 102 passed |
| d F2 | function-word terms hidden with a count; terms only near the threshold | revert `5128cdb` | `test_portal_card_terms`: `test_function_term_rule` (11), `test_hidden_count_on_the_real_session_cards` (6), `test_terms_gated_outside_near_threshold` (2), `test_term_bands_are_the_two_near_threshold_bands`, `test_near_threshold_nitrd_hides_function_words_with_count`, `test_all_hidden_is_said_not_shown_as_none`, `test_near_threshold_not_nitrd_keeps_f3_wording`, `test_card_help_discloses_the_rule_and_the_list`; `test_portal_review`: `test_nitrd_card_shows_call_pcas_rationale_prior_year`, `test_not_nitrd_and_new_core_cards` | 26 failed, 38 passed |
| d F2 | | variant: band gate off (`if False:`) | `test_terms_gated_outside_near_threshold` (2), `test_portal_review::test_nitrd_card_shows_call_pcas_rationale_prior_year`, `test_portal_review::test_not_nitrd_and_new_core_cards` | 4 failed, 99 passed |
| d F2 | | variant: predicate off (`is_function_term` returns False) | `test_function_term_rule` (7 hidden cases), `test_hidden_count_on_the_real_session_cards` (4), `test_near_threshold_nitrd_hides_function_words_with_count`, `test_all_hidden_is_said_not_shown_as_none`, `test_near_threshold_not_nitrd_keeps_f3_wording` | 14 failed, 65 passed (3 files; submission not run) |
| d F2 | | variant: filter off in `_shown` only (predicate intact) | `test_hidden_count_on_the_real_session_cards` (4), `test_near_threshold_nitrd_hides_function_words_with_count`, `test_all_hidden_is_said_not_shown_as_none`, `test_near_threshold_not_nitrd_keeps_f3_wording` | 7 failed, 96 passed |
| d F2 scope | PCA matched terms NOT filtered (owner decision) | revert `82953e4` | `test_portal_card_terms::test_pca_matched_terms_are_not_filtered` | 1 failed, 24 passed |
| d F2 scope | | variant: function words filtered out of the PCA matched terms | `test_portal_card_terms::test_pca_matched_terms_are_not_filtered` | 1 failed, 102 passed |
| e view | `GET /operator/request/{request_id}` | revert `eccd736` | all of `test_portal_request_view` except `test_request_id_derivation_unchanged` (13) | 13 failed, 1 passed |
| e view | | variant: view shows cohort requests only | `test_portal_request_view::test_agent_draft_request_appears_pending` | 1 failed, 102 passed |
| e view | | variant: reserved-FY check removed | `test_portal_request_view::test_reserved_fy_refused_before_the_card` | 1 failed, 102 passed |
| e view | | variant: `back_request_id` dropped from the rendered form | `test_portal_request_view::test_rendered_form_returns_to_the_view` | 1 failed, 102 passed |
| e F5 | review page renders no decision form; decide-links | revert `64e7f8a` | `test_portal_review::test_persona_view_enables_controls_only_for_assignee`, `test_portal_review::test_retry_success_then_decide` | 2 failed, 62 passed, 1 skipped |
| e F5 | | variant: forms back on the review page (`if False:` on the F5 branch) | same two tests | 2 failed, 101 passed, 1 skipped |

Every mutation was caught. The 1 skip in the 4-file runs is the live-write test (L-T3 in `docs/TESTING_LIMITATIONS.md`), so no row above is evidence for it.

**Reconciliation with the commit messages.**
* Matches: F3 1/38, F4 1/39 (revert and order swap), F1 1/39, F2 revert 26 failed, F2 band gate 4, F2 F3-branch 1, PCA 1/24, view revert 13 and the three view variants, F5 2.
* The F2 commit message says "no function filter 14 failed". Re-run today, turning off the filter in `_shown` alone fails 7; turning off the predicate `is_function_term` fails 14 (the extra 7 are the hidden cases of `test_function_term_rule`). So the recorded 14 was most likely the predicate mutation, under a looser name (the exact edit used then was not recorded). Both rows are in the table.
* Not re-run: the F1 variant "score appended after the terms" (only "score beside the rank" was re-run today).
* View revert: 13 failed, as in the `eccd736` message (an earlier run, before `test_rendered_form_returns_to_the_view` existed, was 12 of 13).

**Observation.** Both F5 runs took about 6.5 minutes where the other 4-file runs took about 8 seconds. Not investigated; it does not change a result. Raw results: `/tmp/mut_results.json` (not committed; the table is the record).

**Practice note (owner, 2026-11-10).** Before running any tool that rewrites files in place (for example `ruff format`), copy the before state first (to `/tmp`, or commit), so a whitespace-only claim can be shown by a diff and does not need indirect evidence. Origin: 2026-11-10, `ruff format` rewrote `tests/test_portal_request_view.py` before commit `eccd736`. The before state was not kept; the evidence that the change was layout only was indirect (one change identified, mutation results unchanged on the formatted file).
