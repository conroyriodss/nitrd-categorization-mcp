# Conformance with the GSA MCP hackathon template

This repository is a fork of the GSA-TTS template
([GSA-TTS/mcp-hackathon-template](https://github.com/GSA-TTS/mcp-hackathon-template)).
It is compared here with the template's latest commit, `f39249f` (2026-10-26),
which is in this repository's history. Checked 2026-11-10.

**Owner ruling (2026-11-10): this entry is not restructured to match the
template.** Each difference is listed below with what the template says about it
and why this entry differs.

## Does the template make anything mandatory?

No, not in its own words. The template shows a layout and a workflow but does
not require any of it. Checked by searching every README, QUICKSTART, SECURITY,
`docs/`, `eval/`, `deploy/`, `.github`, `pyproject.toml`, `server.json` and
`manifest.yaml` file in `f39249f` for *must, required, require, requirement,
mandatory, shall, should, suggested, optional, recommended, need(s)*:

* `README.md` contains none of them about the repository's structure or files.
  It presents the layout as what the template provides: "This template gives you
  a working server with one example of each, so you can replace the examples with
  your own service and deploy." The layout is captioned "## Repo structure"
  with `example_server/` marked "← rename to your service". Its one *must* is
  conditional engineering advice: "A server that must fetch caller-supplied URLs
  needs connection-time IP validation on every hop ..."
* `QUICKSTART.md`: "You need [uv]" and "Test HTTP mode (optional)".
* `SECURITY.md`: "Security researchers shall:". This is the vulnerability
  disclosure policy, addressed to researchers, not participants. Its other
  *require* is conditional security advice: "If a tool must fetch arbitrary
  URLs, require exact destination allowlists ..."
* `docs/README.md`: "Vendor partners should submit additions and updates through
  pull requests". Addressed to IBM and Databricks, not participants.
* `deploy/` and `eval/databricks/`: the *must*s and *need*s describe platform facts ("Port
  your server must listen on", "Databricks Apps must be enabled on your
  workspace", "`eval_auth.py` must go inside `agent_server/`"). They are
  conditions for those kits to work, not rules for the repository.

So the differences below are deviations from an example, not violations of a
stated requirement. Limit: this checks the template only. Hackathon rules or
judging criteria published elsewhere are not in this repository and were not
checked here.

## Differences

| # | Template | This entry | Does the template require it? | Why this entry differs |
| --- | --- | --- | --- | --- |
| 1 | One server package, `src/example_server/` ("← rename to your service") | Three MCP server packages, `src/nih_grants_outputs`, `src/nitrd_classifier`, `src/reviewer_portal`, plus `src/nitrd_agent` (the demo agent) and `src/shared` | No | See below. This is the main difference, and it is deliberate. |
| 2 | Top-level `server.json` (MCP registry metadata), `manifest.yaml` (cloud.gov), `requirements.txt` (buildpack hosts) | None at top level. One each per server under `deploy/databricks/<server>/` (`server.json`, `manifest.yaml`, `requirements.txt`, `app.yaml`); the agent and e2e runner have `app.yaml` and `requirements.txt` | No | Each file describes one server; with three servers there are three of each. Dependencies are declared once in `pyproject.toml` / `uv.lock`; the per-server `requirements.txt` files are what each Databricks App installs. |
| 3 | `main.py` starts the one server: `uv run python main.py` | `main.py <server-name>` starts one of the three. `uv run python main.py` with no name lists the three servers and how to start each, then exits 0 (it does not default to one: a stdio server waits silently, which would look like a hang). Pinned by `tests/test_main_entry.py` | No | Three servers. The template's first command still gives a useful answer. |
| 4 | `Dockerfile` for the one server | Kept, adapted: `SERVER_MODULE` selects the server (default `nih_grants_outputs`) | No | Three servers. Not used by the deployed build (Databricks Apps), and not built or run as part of this entry's verification. |
| 5 | `docs/`: "Partner Reference Materials", vendor-contributed material with a GSA non-endorsement notice | `docs/` holds this project's plans, runbooks and decision records. Its `README.md` is still the template's partner-materials text, and the top-level README's "Partner reference materials" section still describes `docs/` that way | No | The directory was used for project documentation. Known inaccuracy, not fixed by this file: those two texts describe `docs/` as vendor material, which it is not. |
| 6 | Smoke tests for `example_server` (`tests/test_server.py`, `tests/test_http_security.py`) | Replaced by this entry's suite (48 files under `tests/`) | No | They test the example server, which is not here. |
| 7 | `eval/`: README stub ("This template intentionally does **not** ship an eval harness") plus the Databricks eval kit | A full evaluation tree (`eval/`), plus top-level `ARCHITECTURE.md`, `DEMO.md`, `DEMOS.md`, `scripts/`, `submission/` | No | Additions, not removals. |

Same as the template (an earlier internal audit listed some of these as missing;
they are present): `.python-version` (3.11), `.env.example` (extended),
`.dockerignore`, `.github/workflows/ci.yml` (one-line change), `LICENSE` (MIT),
`QUICKSTART.md` and `SECURITY.md` (rewritten for three servers), and
`.agents/skills/` (identical to `f39249f`).

## Why three servers (difference 1)

The entry's central claim is a separation of **read**, **inference** and
**sandbox write**: an MCP host can grant `nih-grants-outputs` (reads public NIH
evidence) and `nitrd-classifier` (suggests a NITRD yes/no and PCAs) freely, and
gate `reviewer-portal`, the only server that writes, on user confirmation
([ARCHITECTURE.md](ARCHITECTURE.md)). Hosts make that trust decision per
server.

One MCP server cannot express it. A deployed server runs as one identity with
one set of grants, and a host's connection and trust decision is made per
server (some hosts can also approve individual tools, but that does not change
the identity behind them). Each of the three is deployed as its own Databricks
App with its own service principal and its own Unity Catalog grants, so the
separation is enforced by the hosting, not only described in tool
descriptions. Folding them into one package would put the read tools and the
write tools behind one identity with write grants, which removes the property
the entry is about.

Limits, stated in ARCHITECTURE.md and not changed by this file: the portal's
service principal holds `MODIFY` on the sandbox tables, so "no delete" is a
property of its tool surface, not of its grants.
