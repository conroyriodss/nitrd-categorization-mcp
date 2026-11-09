# Draft: evaluation document, security section (fix (c))

Status: DRAFT. The owner approved paragraphs 1-2 on 2026-11-09 and asked for the positive-control addition. Paragraph 3 is that addition, and the owner has NOT yet reviewed its wording. Not yet in `submission/NITRD_Evaluation_2026-11-06.docx`. The bracketed sentence is filled in only after the post-(c) battery and the manual rows of `docs/PLAN_fix_c.md` step 2 are green. Until then, the stale-claims window in that plan applies: nothing here describes the shipped build.

## Paragraph

At the time of evaluation, the reviewer portal enforced ordering and single-decision semantics but not who decides. Lifecycle run d74756ca showed the portal's service principal moving a request from pending (Delta v298) to approved (v299) with no human action. Fix (c) adds an identity control. A decision is accepted only when the x-forwarded-email header, which the Databricks Apps proxy sets from the caller's authenticated identity, matches an entry on an explicit approver list (case-insensitive, whitespace-trimmed). An empty or missing list refuses every decision.

Before relying on the header, we tested its integrity. A request carrying x-forwarded-email set to a spoofed address reached the app with the signed-in user's real address, so the proxy overwrites client-supplied identity headers. That test ran on a human sign-in only; that the same holds for service principals is an inference, not a measurement. A pattern match on "@" would not work: x-forwarded-user is `<id>@<workspace>` for people and service principals alike, and for a service principal x-forwarded-email carries its application id.

The deployed MCP tool path has no human positive control, because no person can call the decision tool over /mcp in our test harness. What stands in for it is the refusal reason the portal logs: a service principal's refused decision must log `not_in_set` with that principal's id, which shows the header reached the tool. A refusal logged as `absent` would mean the control refuses everything without ever seeing an identity, and it would not count as a pass. A person deciding is shown on the deployed portal only through its review page, which runs the same check.

[After the fix: "Since commit <sha>, the portal refuses decisions from service-principal identities (run <id>; the portal log records not_in_set with the service principal's id), and the same kind of request is decided by a listed person on the review page (run <id>)."]

## Sources

* `eval/results/auth/20261109_header_integrity_whoami.json`: the /whoami bodies and the spoof test.
* `docs/PLAN_fix_c.md`, step 2: the design, the acceptance table (row 9 is the refusal-reason measurement) and the mutation checks.
* d74756ca: the before state. It is in the stale-claims window, so cite it only as the BEFORE.
