# Security and sandbox policy

This repository is a hackathon prototype (GSA MCP + AI Agent Hackathon) built
from the GSA MCP Hackathon template. It is not NIH, RCDC, or GSA production
software, has no Authority to Operate, and makes no production security claim.
This page describes the suite's actual data scope, write controls, identity
model, and known limitations.

## Data scope: public data only

The servers read public-source records staged once in Unity Catalog tables
(default `users.conroyri.nitrd_hackathon_v1_*`; see
[`src/shared/tables.py`](src/shared/tables.py)). Tools query those snapshots
and make no live upstream API calls per request.

| Source | Content used |
| --- | --- |
| NIH ExPORTER (RePORTER) | Project records, abstracts, public health relevance text, spending-category names, administering IC, activity code, public PI and program-officer names |
| iCite | Publication citation metrics |
| PubMed | Article metadata, MeSH terms, publication types |
| DataCite | Registered research outputs. **Table not loaded in the MVP:** `outputs_get_project_datacite` returns `not_available`, which is not evidence that no outputs exist. |

No restricted, pre-decisional, or personally sensitive data is used. Public
program-officer names are used only to match a routing persona; the persona
file stores SHA-256 hashes of normalized names rather than names. That keeps
names out of the repository but is not anonymization. Test fixtures use
fictional names.

## Write controls: sandbox only

Only `reviewer-portal` writes, and only to three sandbox tables:
`review_requests`, `review_events`, and `routing_events`.

- Every written row carries `sandbox = true` and the label
  **"Not RCDC / demonstration only"**. The values are fixed in
  [`src/reviewer_portal/config.py`](src/reviewer_portal/config.py), typed as
  literals in the response models, and enforced by table `CHECK` constraints
  ([`scripts/create_review_tables.sql`](scripts/create_review_tables.sql)).
- Submissions are idempotent: `request_id` is derived from an
  `idempotency_key` (default: a hash of the payload). Reusing a key with a
  different payload is rejected. Event rows have deterministic IDs.
- A request and its events are written in one transaction.
- Sandbox rows are demonstration records. They are not categorization
  decisions and do not change ExPORTER, RePORTER, RCDC, or any operational
  system.

The sandbox flag and label mark the scope of a record. They are not an
authorization boundary.

## Identity model

There are two different kinds of identity, and neither authenticates a
reviewer.

**Platform identity (who the server runs as).** Deployed on Databricks Apps,
each server runs as its own App service principal, created by the platform
with the App. Databricks injects its credentials (`DATABRICKS_CLIENT_ID`,
`DATABRICKS_CLIENT_SECRET`) at runtime. Table access is granted to that
principal, per App: `SELECT` on the read tables each server uses, and write
grants on the three sandbox tables for the `reviewer-portal` App only (see
[deploy/databricks/README.md](deploy/databricks/README.md)). Locally, the
servers run as whoever's Databricks credentials are in the environment. Callers
reach a deployed App through workspace OAuth; the App does not see or act with
the caller's own data permissions.

**Reviewer identity (who the tool says is acting).** There is **no end-user
authentication**. `reviewer_id` is an ordinary tool parameter. It must match
the persona ID pattern and the allow-list of nine **fictional** personas in
[`src/reviewer_portal/resources/personas.json`](src/reviewer_portal/resources/personas.json)
(`demo_po_*`, `demo_ic_rep_*`, `demo_sia`). That checks roster membership
only. Any caller who can reach the portal can submit or decide as any persona.
Persona IDs do not correspond to or authenticate real people.

Before any non-demonstration use, reviewer actions would need authenticated
identities, per-action authorization, and an audit trail bound to the
authenticated principal, not to a parameter.

## Known limitations

- **Mid-turn write persistence.** During development, a write started in a
  conversational turn persisted after the turn was interrupted. An interrupted
  turn is not a confirmed cancellation. The portal returns a durable
  `request_id`, supports an `idempotency_key`, and exposes
  `portal_get_review_history` so a client can check before retrying.
  Fault-injection testing of cancellation and lost responses has not been run.
- **Model misses on new projects.** The parent classifier is weaker on cores
  it has not seen before (FY2019 validation half: PR-AUC 0.862 overall, 0.720
  on new cores; [eval/classifier_evaluation.md](eval/classifier_evaluation.md)).
  It also learns RCDC's historical labels, including their errors. Suggestions
  for new projects need particular human scrutiny.
- **No PCA ground truth.** Public data does not record Program Component Area
  assignments, so PCA rankings have no measured accuracy. Output-intensity
  signals are exploratory and cover 7 of the 12 PCAs.
- **The scope engine ranks something for nearly any text.** PCA ranking
  scores matches against scope vocabulary and returns a ranked list even for
  projects that are not NITRD at all. A top-ranked PCA is not evidence that a
  project belongs in NITRD; read it only after the parent decision, and treat
  low match scores as "no meaningful match".
- **Untrusted content.** Abstracts and publication metadata are untrusted
  input and could contain instructions. Agents should treat them as data.
  Resistance to prompt injection, credential-disclosure resistance, and
  authorization isolation are **not measured**.
- **Separate Apps are not separate authorization domains.** Splitting read,
  inference, and write into three Apps narrows which principal holds write
  grants, but it has not been tested as an isolation control.

## Handling secrets and errors

- No secrets are committed. `.env` files are git-ignored and hold settings
  only; Databricks authentication comes from the CLI login or environment
  locally, and from platform-injected credentials on Databricks Apps.
- SQL uses named parameters; user input is never interpolated into statement
  text.
- Tool errors are returned as a short message and hint, without credentials
  or stack traces. A failed warehouse statement's error message is passed
  through in the tool error; it can name tables or columns.

## Public-repository hygiene (checked 2026-11-03; updated 2026-11-04)

The three submission repositories (this one,
[uac-nitrd](https://github.com/conroyriodss/uac-nitrd) and
[uac-witness](https://github.com/conroyriodss/uac-witness)) are public. Before release they were
swept for:

- **Credentials:** Databricks PATs, GitHub/Slack tokens, AWS keys, JWTs and private keys, in the
  current files and in every blob reachable in the git history of all three (binaries included)
  plus all commit messages. None were found
  ([`eval/results/provenance/history_sweep.json`](eval/results/provenance/history_sweep.json)).
  The same sweep found one workspace hostname, an identifier and not a credential, in
  `scripts/agent_eval_offline.py` from `e078f2f` until its removal in `7a9953e` (2026-09-18).
  It is not in HEAD. History was not rewritten.
- **Model binary:** `parent_model.joblib` bytes and its 270,000-term vocabulary were scanned for
  the same patterns and for e-mail addresses. None were found
  ([`model_scan.json`](eval/results/provenance/model_scan.json)).
- **Exported run evidence** (`eval/results/`): the same credential patterns again, at export time
  (a hit aborts the export). The workspace host name, Apps service-principal IDs and warehouse ID
  are replaced by placeholders, and each replacement is counted in `eval/results/INDEX.json`.
- **People:** reviewer personas are fictional, and since personas v2 (2026-11-03) the
  persona-to-award assignment is fully synthetic. Each demo program officer lists the public core
  project numbers it stands in for, and routing reads no program-officer name. Personas v1
  (2026-10-27 to 2026-11-03) held SHA-256 hashes of two public PO names. They are removed from
  the current version and remain in git history; history was not rewritten.
  `outputs_get_project_detail` returns PI and PO names as published in public NIH ExPORTER data;
  the committed transcript replaces those values with `<person name omitted>`. Test
  fixtures use placeholder addresses.
- **FY2025 UAC fixture in `uac-nitrd` (2026-11-04):** its source's `PCC` column is not public
  data, so it was removed from every commit in one sanctioned history rewrite of `uac-nitrd`.
  This is the only history rewrite in the three repositories. Fixture sha256 `8c92c8af…`
  (superseded) became `73c87d5a…`. Every `uac-nitrd` commit SHA changed, and the tag
  `uac-nitrd-freeze-v1` was moved to the rewritten freeze commit. The full old→new map is in
  [uac-witness record 0003](https://github.com/conroyriodss/uac-witness/blob/main/records/0003-correction-pcc-history-rewrite.json)
  and in seal-log line 32. Old commits may stay reachable by SHA on GitHub until GitHub Support
  purges them. The engine never read `PCC`. The fixture's `PO Name` column is being removed from the
  current version with a forward commit, without a history rewrite. Program-officer names are
  public in RePORTER, but the engine does not need them.
- **Sealed-volume access during that correction:** while scoping the purge, the assistant ran one
  recursive filename-only text search for `PCC` values over the sealed held-out volume. It found
  no matches and displayed no content, but it did read the bytes of every file there, including
  key and membership files. Nothing from the sealed volume entered any build: no build read
  manifest cites a sealed path. The volume will not be searched again. To update the seal
  log's commit citations, the assistant then read only `SEAL_MANIFEST.json` and
  `SEAL_AMENDMENTS.jsonl`, by name, and opened no key or membership file. Both events are
  recorded in seal-log line 32.
- **Sealed evaluation data:** only hashes are published (the `uac-nitrd` seal manifest and the
  `uac-witness` records), never key contents. No FY2026 award-level NITRD membership is in any
  repository. The FY2026 file in `uac-nitrd` holds model predictions made before that membership
  was public.

## Reporting a vulnerability

Report suspected vulnerabilities privately by email to
[conroyri@nih.gov](mailto:conroyri@nih.gov), with "nitrd-categorization-mcp
security" in the subject. Do not open a public GitHub issue for a
vulnerability. (GitHub private vulnerability reporting is not enabled on this
repository.) Please do not test against the deployed hackathon Apps or the shared
workspace beyond what is needed to confirm an issue, and do not access,
modify, or delete other users' data.

The main branch is the only supported version. This is a time-limited
hackathon entry; fixes are best-effort.

Vulnerabilities in the upstream template itself should be reported under the
[GSA Vulnerability Disclosure Policy](https://www.gsa.gov/vulnerability-disclosure-policy).
