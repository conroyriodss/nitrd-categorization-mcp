> **Superseded: see submission/README.md.** History only: a point-in-time audit of 2026-11-17, before the 11-18 finals.

# Submission readiness audit — 2026-11-17

Entry 2, Service: Write track. Due Friday 2026-11-20 23:59 EST.
Every fact below was read from state (Apps API, git, warehouse, disk) on 2026-11-17.
Nothing is reported from recall or from a previous note.

---

## 1. Deployed state

All five apps are **STOPPED / UNAVAILABLE** (compute stopped "due to workspace or account status", 2026-11-13). No app is running.

| App | Last deployment ID | Created | source_code_path | Git HEAD in folder | DEPLOY_COMMIT marker |
| --- | --- | --- | --- | --- | --- |
| mcp-nitrd-reviewer-portal | `01f1dc4ff3c6…` | 2026-11-09 15:12:17 Z | `apps/mcp-nitrd-reviewer-portal` | `d7bad89b9c70` | `d7bad89b9c70` |
| mcp-nitrd-e2e-runner | `01f1dc84085a…` | 2026-11-09 21:25:05 Z | `apps/mcp-nitrd-e2e-runner` | `6056f3767da5` | `6056f3767da5` |
| mcp-nitrd-agent | `01f1dc50977f…` | 2026-11-09 15:16:52 Z | `apps/mcp-nitrd-agent` | `d7bad89b9c70` | no marker file |
| mcp-nih-grants-outputs | `01f1da210f4a…` | 2026-11-06 20:31:35 Z | `apps/mcp-nih-grants-outputs` | `95e5dea1323e` | no marker file |
| mcp-nitrd-classifier | `01f1da210f79…` | 2026-11-06 20:31:35 Z | `apps/mcp-nitrd-classifier` | `95e5dea1323e` | no marker file |

Portal and agent confirmed at `d7bad89`; runner at `6056f37`; outputs and classifier at `95e5dea`.

**-next folders**: both still exist.
* `mcp-nitrd-reviewer-portal-next`: HEAD `9b222be`, DEPLOY_COMMIT `9b222be`
* `mcp-nitrd-e2e-runner-next`: HEAD `9b222be`, DEPLOY_COMMIT `9b222be`

The Wednesday 2026-11-11 deploy sitting did not happen. No deployment was created after 2026-11-09. The apps were stopped externally on 2026-11-13.

---

## 2. Repo state

* Local HEAD: `9b222be` ("Plan: deploy both portal and runner from -next folders")
* Remote HEAD (`git ls-remote`): `9b222be36e062a248e63a591cab1844802e7fb2b`
* Local = remote, no ahead/behind.
* Working tree: **clean** (no modified, staged, or untracked files).
* CI status on `9b222be`: **not verified** (cannot read GitHub Actions from here). Commit for the owner to check: `9b222be`.

---

## 3. Sandbox

All three tables are empty.

| Table | Row count |
| --- | --- |
| `users.conroyri.nitrd_hackathon_v1_review_requests` | 0 |
| `users.conroyri.nitrd_hackathon_v1_review_events` | 0 |
| `users.conroyri.nitrd_hackathon_v1_routing_events` | 0 |

**Last 5 Delta versions** (all three tables identical pattern): versions are DELETEs, all by `conroyri@nih.gov`, all on 2026-11-09 between 22:43:26 and 22:44:04 UTC. Each deletes one request_id. Nothing has touched any of the three tables since 2026-11-09.

---

## 4. Deliverable inventory

| Artifact | Exists | Location | SHA-256 (first 16) | Last modified | Routing targets it |
| --- | --- | --- | --- | --- | --- |
| Evaluation DOCX | YES | `submission/NITRD_Evaluation_2026-11-06b.docx` | `2b70c7bcff69a578` | 2026-11-09 17:03 Z | YES (sha256_prefix `2b70c7bc` in routing spec) |
| Deck PPTX | YES | `submission/NITRD_Hackathon_Presentation_2026-11-06b.pptx` | `c974508168cbc199` | 2026-11-09 17:03 Z | YES |
| Evaluation PDF | **NO** | does not exist | — | — | — |
| Code-link PDF | **NO** | does not exist | — | — | — |
| Video | **NO** | does not exist | — | — | — |
| Routing spec | YES | `submission/apply/routing_spec_11-06b.json` | `33c43e365dfcd7d4` | 2026-11-10 14:33 Z | (is the spec) |
| DOCX text extract | YES | `submission/NITRD_Evaluation_2026-11-06b.docx.txt` | `ccf8c7fce062c33f` | 2026-11-09 17:03 Z | — |
| PPTX text extract | YES | `submission/NITRD_Hackathon_Presentation_2026-11-06b.pptx.txt` | `307ef6d523973148` | 2026-11-09 17:03 Z | — |

**Three of five deliverables do not exist**: the evaluation PDF, the code-link PDF, and the video.

The explainability data for 10388671 exists (`eval/results/explain/weak_demo_awards_v1.json`) but the explainability **slide** has never been built.

---

## 5. Placeholder sweep

Searched the committed DOCX and PPTX text extracts for: `<sha>`, `<id>`, `<page>`, `NEEDS SOURCE`, `TBD`, `TODO`, angle-bracket templates (`<word>`), square-bracket templates, empty citations, and promises of evidence not present.

**No angle-bracket template placeholders found.** No `<sha>`, `<id>`, `<page>`, `TBD`, `TODO`, or `NEEDS SOURCE` in either file.

### Hits classified

| Marker | DOCX lines | PPTX lines | Classification |
| --- | --- | --- | --- |
| `[PENDING REVEAL]` | 4, 5, 110, 126, 229 | 14, 16, 169, 231, 239, 295 | **DELIBERATE** — pre-registered FY2026 forecast; stays until reveal |
| `[Planned]` | 5, 197, 287, 293, 305 | 16, 240, 289, 311 | **DELIBERATE** — evidence tier label for work not completed; defined in line 5 |
| "not yet measured" / "not yet implemented" | 293, 302 | — | **DELIBERATE** — disclosed limitations (sandbox principal separation; agent injection resistance) |

**No UNFILLED template slots found.** A judge opening the PDF will not encounter `<sha>`, `<id>`, or any template placeholder.

---

## 6. Open-items sweep

### Still live

| Location | Marker | What it waits on | Stale? |
| --- | --- | --- | --- |
| `docs/TESTING_LIMITATIONS.md` L-T3 | "NEVER EXECUTED" | Live-write submission test; was planned for Wednesday sitting | **Stale** — sitting didn't happen; L-T3 is still open but the sitting reference is outdated |
| `docs/TESTING_LIMITATIONS.md` L-T1/L-T2 | "Open: no committed record shows any of the four run after 2026-11-09" | Re-running agent tests in adversarial venv | Live — owner's call |
| `docs/PLAN_combined_portal_change.md` L140 | "HELD until after the gate" | Routing-spec apply held on deploy | **Stale** — deploy didn't happen; the "after the gate" condition is moot |
| `docs/PLAN_combined_portal_change.md` L142 | "Document apply: HELD" | D03, D04, P14, D06c, D13, D15b depend on what ships | **Stale** — nothing shipped |
| `submission/apply/routing_spec_11-06b.json` | 3 HELD rows (D03, D04, P14) | Deploy with new battery run IDs | **Stale** — deploy didn't happen; run IDs in D03/D04/P14 still cite d7bad89 battery |
| `submission/apply/routing_spec_11-06b.json` | D06c, D13, D15b conditional on view | View shipping | **Stale** — view never deployed |
| `submission/apply/routing_spec_11-06b.json` | D13 PENDING | Combined portal change | **Stale** |
| `submission/apply/HAND_EDITS_11-06b.md` | H1-H5 | Owner applies in Word/PowerPoint | Live — never applied |
| `docs/PLAN_combined_portal_change.md` L140 | Explainability slide for 10388671 | "queued since Sunday 2026-11-08" | Live — data exists, slide never built |
| `eval/explain/README.md` | Explainability analysis written | Slide not yet created from it | Live |

### Summary

The Wednesday deploy sitting never happened. All items held on it (D03, D04, P14, D06c, D13, D15b, the redeployment itself) are stale in their current form. The routing spec's HELD rows still reference the d7bad89 battery, not a new one. The hand-edit list (H1-H5) was never applied. L-T3 was never executed.

---

## 7. What remains — prioritised

The deploy sitting did not happen. The apps are stopped externally. The owner must first decide: (A) deploy from -next folders if apps can be restarted, run the battery, then apply routing with new IDs; or (B) submit with the d7bad89 battery evidence (already committed and verified) and apply routing rows against that build. Option B avoids the deploy entirely. Three days remain, one spent filming.

| # | Item | Owner's list | Must / Should / Drop | Time est. | Notes |
| --- | --- | --- | --- | --- | --- |
| 0 | **DECISION: deploy or not** | not listed | **MUST** | 15 min | Determines whether D03/D04/P14/D06c/D13/D15b are applied with new or existing IDs, and whether L-T3 can run |
| a | Routing-batch programmatic apply | (a) | **MUST** | 1.5 h | `scripts/apply_routing_batch.py` exists. Dry-run first. 49 rows (15 AGREED, 20 PROPOSED, 3 HELD, 9 RETIRE, 1 PENDING). If no deploy: D03/D04/P14 use d7bad89 run IDs; D06c/D13/D15b drop or stay as-is; H1 text uses existing battery |
| b | Hand-edit list: H1, H2, H3, H4, H5 | (b) partially — D03 is H1, D09 is H2, D14 is H3, D16e is H4, slide 9 chart is H5 | **MUST** | 1 h owner time | Owner applies in Word/PowerPoint. Five items. H1 depends on deploy decision (run IDs). H5 (chart relabel) is a chart XML edit |
| c | Overview and Objectives section | (c) | **SHOULD** | 30 min | DOCX line 334 already says "The sample includes a separate Overview and Objectives section ... The draft's section order and numbering are retained." This is a disclosed structural difference, not a missing section. Adding one is optional |
| d | Explainability slide for 10388671 | (d) | **SHOULD** | 1.5 h | Data exists in `eval/results/explain/weak_demo_awards_v1.json` and `eval/explain/README.md`. Need to build an actual PowerPoint slide from it. Queued since 2026-11-08 |
| e | DOCX → PDF conversion with verification | (e) | **MUST** | 30 min | No PDF exists. Need Word → PDF, then verify page count, figures, formatting |
| f | Code-link PDF | (f) | **MUST** | 30 min | Confirm all three GitHub repos are public (`nitrd-categorization-mcp`, `uac-nitrd`, `uac-witness`). Then create a PDF with repo URLs, commit hashes, and relationship. Cannot verify repo visibility from here |
| g | Video | (g) | **MUST** | Half day (owner, Wednesday) | Does not exist. Owner films |
| h | -next folder cleanup | not listed | **DROP** | 5 min | Two folders at 9b222be. Harmless; clean up if desired |
| i | Stale plan references | not listed | **SHOULD** | 30 min | PLAN_combined_portal_change.md references a Wednesday sitting and Thursday document day that didn't happen. Update or add a "Post-mortem" note |
| j | PROPOSED routing rows (20) | not listed | **MUST** | included in (a) | 20 PROPOSED rows need routing to AGREED before the apply script writes them. Owner decides each |

### Critical path (3 days, 1 filming)

**Day 1 (Tuesday)**: Item 0 (deploy decision), then (j) route the 20 PROPOSED rows, then (a) programmatic apply + (b) hand edits. Owner in Word/PowerPoint for H1-H5.

**Day 2 (Wednesday)**: Owner films (g). In parallel: (d) explainability slide, (e) PDF conversion + verification, (f) code-link PDF.

**Day 3 (Thursday)**: Buffer. (c) Overview section if time. (i) plan cleanup. Final read-through of the PDF.

---

## Audit method

Apps API: `GET /api/2.0/apps/<name>` and `GET /api/2.0/apps/<name>/deployments` for all five apps.
Git: `git rev-parse HEAD`, `git ls-remote origin refs/heads/main`, `git status --porcelain`, `cat DEPLOY_COMMIT.py` in each folder.
Warehouse: `SELECT count(*)` on the three review tables; `DESCRIBE HISTORY` (5 most recent versions) on each.
Disk: `sha256sum`, `stat --printf`, `find`, `grep` across `submission/`, `docs/`, `eval/`.
Placeholder sweep: `grep -n` for each pattern against both `.docx.txt` and `.pptx.txt` extracts.
Routing spec: parsed `routing_spec_11-06b.json` with Python `json` module, counted by routing status.
