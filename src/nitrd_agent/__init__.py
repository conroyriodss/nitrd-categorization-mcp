"""Thin agent over the three NITRD MCP servers, with a human approval gate.

config: the pinned model, the servers, the gate (which tools the model never gets).
scoring: the pre-committed AES functional suite scorer (pure; no SDK imports).
gate: drafts that a person approves before any write.
agent: builds the OpenAI Agents SDK agent (imported lazily; needs openai-agents).
aes: runs the suite against the deployed servers and records the result.
app: the Databricks App (chat, drafts, approval, suite runs).
"""
