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
