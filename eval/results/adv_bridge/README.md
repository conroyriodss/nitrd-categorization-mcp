# Adversarial bridge: tool definitions, counted run vs a later commit (2026-11-09)

## Question answered

The counted adversarial run 6ab39b17 ran at repo commit 021defd7. Between that commit and aed2590, did any definition the model reads change? A definition is the name, description, input schema, output schema and annotations, and the question covers the 12 MCP tools the agent is offered.

* `tests/test_agent_allowlist_identity.py` (committed) shows the same 12 tool NAMES are offered under the old gate and the new gate.
* It does not compare definitions. This record does.

## Scope

* This is a point-in-time comparison of two fixed commits, 021defd7 and aed2590. It is not an invariant, and it is deliberately not a CI test.
* aed2590's `src/` is identical to d7bad89, the commit deployed on 2026-11-09 (`git diff --quiet d7bad89 aed2590 -- src`).
* The definitions are rendered by one library for both trees: fastmcp 4.1.6, Python 3.11.17, from the adversarial venv rebuilt on 2026-11-09. So this compares what the SOURCE declares. It is not a record of what the counted run's own fastmcp rendered (its manifest does not record the fastmcp version), and not of what the deployed apps (fastmcp 4.0.11) serve.

## Method

`compare_tool_definitions.py` in this folder (sha256 `7b0e0471ffaa3f034ec68e74cf146c596a30b353da952d491e34c2d298ffdf7f`):

1. `git archive <commit> src` extracts each tree into a temp dir.
2. Each tree lists its three servers' tools in-process (fastmcp `Client`), in a separate interpreter with `PYTHONPATH` set to that tree only.
3. The module files actually imported are recorded. Both trees' `imports_resolved_to_extracted_tree` is `true`, so the old tree was not shadowed by the editable install.
4. Each definition is canonical JSON (sorted keys), hashed with SHA-256.

Command, from the repo root: `python eval/results/adv_bridge/compare_tool_definitions.py --old 021defd7928728f223e04f6af80826645ffa98cf --new aed2590 --out eval/results/adv_bridge/20261109_tool_definitions_021defd7_vs_aed2590.json`. The exit code is 0 only if all 12 are identical and both trees resolved to their own source.

Cross-check: an earlier ad hoc version of the same comparison, run the same day and not committed, gave the same 12 hashes (first 12 characters checked). After `ruff format`, the committed script was re-run and its output is byte-identical.

## Result: all 12 identical

Output: `20261109_tool_definitions_021defd7_vs_aed2590.json`.

| Tool | 021defd7 sha256 | aed2590 sha256 | |
| --- | --- | --- | --- |
| `classifier_classify_parent` | `c80ae9c334a019bac271039e860508950d7369436d739b4cf2d06b320848f754` | `c80ae9c334a019bac271039e860508950d7369436d739b4cf2d06b320848f754` | same |
| `classifier_classify_subcategory` | `56a929152ef71af844ffe957f03ed8347b20663b686c72da95ff530e835ab479` | `56a929152ef71af844ffe957f03ed8347b20663b686c72da95ff530e835ab479` | same |
| `classifier_explain` | `f054c2e222e692e0e22778b06da78739585c1a7fe0dc0e27387f6360324a78d8` | `f054c2e222e692e0e22778b06da78739585c1a7fe0dc0e27387f6360324a78d8` | same |
| `outputs_find_cohort` | `be4d429e5eb0c0db37a4eb4282b0d84e691171d485a9846aa0fc119618c8032a` | `be4d429e5eb0c0db37a4eb4282b0d84e691171d485a9846aa0fc119618c8032a` | same |
| `outputs_find_projects` | `bafa6c99bd47576ce058ba1fd8e2205be8ccc9055c1ffd416758c529e7d8eba4` | `bafa6c99bd47576ce058ba1fd8e2205be8ccc9055c1ffd416758c529e7d8eba4` | same |
| `outputs_get_project_datacite` | `d2e01280fa6c453232f31455f8c5e121b61962aea716c6a81a68dda180ad91df` | `d2e01280fa6c453232f31455f8c5e121b61962aea716c6a81a68dda180ad91df` | same |
| `outputs_get_project_detail` | `2ea0d1761a0743aace53f070cefec9b56eb603fe40299c33dcb758b5db01a50f` | `2ea0d1761a0743aace53f070cefec9b56eb603fe40299c33dcb758b5db01a50f` | same |
| `outputs_get_project_publications` | `49549d0313c230f1fa8ed61bb4e4eb522da575296fc4538082c3c6ae4da1a80a` | `49549d0313c230f1fa8ed61bb4e4eb522da575296fc4538082c3c6ae4da1a80a` | same |
| `outputs_score_project_intensity` | `0ffb0b1c6010c534171fea9546d78f669717720f8821c6d5140d83d62fbafc21` | `0ffb0b1c6010c534171fea9546d78f669717720f8821c6d5140d83d62fbafc21` | same |
| `portal_get_review_history` | `54d96fbc90d9ac7a7160b461c9559280f58387c1f64f0a251788f0c1691f3dd9` | `54d96fbc90d9ac7a7160b461c9559280f58387c1f64f0a251788f0c1691f3dd9` | same |
| `portal_get_reviewer_assignment` | `61986548a43e71d0efdc842b0e399eb4d0ef11bf804ce42ef5b70522e301ca1f` | `61986548a43e71d0efdc842b0e399eb4d0ef11bf804ce42ef5b70522e301ca1f` | same |
| `portal_list_pending_reviews` | `73fe476a5cc257f7c429521152525571e9f6aa9382645a891a17a894e2802a87` | `73fe476a5cc257f7c429521152525571e9f6aa9382645a891a17a894e2802a87` | same |

Full conclusion and context: `docs/PLAN_fix_c.md`, "Adversarial counted result vs the shipped agent".
