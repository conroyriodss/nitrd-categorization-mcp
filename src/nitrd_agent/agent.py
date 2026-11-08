"""The thin agent: OpenAI Agents SDK over the three MCP servers.

Same shape as the OpenAI-Agents-SDK app template (cf. agent-fpac-soil-openai-sdk):
one Agent, streamable-HTTP MCP servers authenticated with the app's own service
principal, a Databricks-served model through the Responses API. Additions here:
the write tools are filtered out of the portal server (the gate), and one local
tool, agent_draft_review_request, stores a draft for a person to approve.

Transport "http" (deployed apps) is what the suite measures. Transport "stdio"
spawns `python main.py <server>` locally, for development only.
"""

from __future__ import annotations

import json
import os
import sys
import time
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nitrd_agent import config, gate

ROOT = Path(__file__).resolve().parents[2]


def _attr(obj: Any, snake: str, camel: str) -> Any:
    """mcp 2.x uses snake_case fields; earlier releases camelCase."""
    value = getattr(obj, snake, None)
    return getattr(obj, camel, None) if value is None else value


def workspace():
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()


def bearer(w) -> str:
    """OAuth bearer of this process's identity (the app's SP when deployed)."""
    return w.config.authenticate()["Authorization"].split(" ", 1)[1]


def tool_filter(server: str):
    """The gate: an allowlist, on every server. A tool not in
    config.EXPOSED_TOOLS[server] is withheld from the model; an unlisted
    server raises KeyError, so it fails closed too."""
    from agents.mcp import create_static_tool_filter

    return create_static_tool_filter(
        allowed_tool_names=list(config.EXPOSED_TOOLS[server])
    )


def server_urls(w) -> dict[str, str]:
    out = {}
    for name, app in config.SERVERS:
        url = os.getenv(config.URL_ENV[name], "").strip()
        out[name] = url or w.apps.get(app).url.rstrip("/") + "/mcp"
    return out


@dataclass
class RunRecord:
    prompt: str
    calls: list[dict[str, Any]] = field(default_factory=list)
    exposed_tools: list[str] = field(default_factory=list)
    final: str = ""
    turns: int | None = None
    latency_s: float | None = None
    error: str | None = None
    drafts: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "calls": self.calls,
            "exposed_tools": self.exposed_tools,
            "final": self.final[:4000],
            "turns": self.turns,
            "latency_s": self.latency_s,
            "error": self.error,
            "drafts": self.drafts,
        }


class Session:
    """Three connected MCP servers + a model client, for one or more runs."""

    def __init__(self, transport: str = "http", w=None) -> None:
        self.transport = transport
        self.w = w or workspace()
        self._stack: AsyncExitStack | None = None
        self.servers: dict[str, Any] = {}
        self.client = None
        self.submit_schema: dict[str, Any] | None = None

    async def __aenter__(self) -> Session:
        from agents.mcp import (
            MCPServerStdio,
            MCPServerStreamableHttp,
        )
        from openai import AsyncOpenAI

        token = bearer(self.w)
        self._stack = AsyncExitStack()
        urls = server_urls(self.w) if self.transport == "http" else {}
        for name, _ in config.SERVERS:
            filt = tool_filter(name)
            if self.transport == "http":
                server = MCPServerStreamableHttp(
                    params={
                        "url": urls[name],
                        "headers": {"Authorization": f"Bearer {token}"},
                        "timeout": 120,
                        "sse_read_timeout": 300,
                    },
                    name=name,
                    client_session_timeout_seconds=180,
                    tool_filter=filt,
                    cache_tools_list=True,
                    max_retry_attempts=2,
                )
            else:
                server = MCPServerStdio(
                    params={
                        "command": sys.executable,
                        "args": ["main.py", name],
                        "cwd": str(ROOT),
                        "env": dict(os.environ),
                    },
                    name=name,
                    client_session_timeout_seconds=180,
                    tool_filter=filt,
                    cache_tools_list=True,
                )
            self.servers[name] = await self._stack.enter_async_context(server)
        self.client = AsyncOpenAI(
            base_url=f"{self.w.config.host.rstrip('/')}/serving-endpoints",
            api_key=token,
        )
        self.submit_schema = await self._write_tool_schema()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._stack is not None:
            await self._stack.aclose()

    async def _write_tool_schema(self) -> dict[str, Any]:
        """The portal write tool's input schema, read over a separate,
        unfiltered listing (the model never sees this tool)."""
        portal = self.servers["reviewer-portal"]
        session = portal.session  # raw MCP ClientSession, no tool filter
        listed = await session.list_tools()
        for tool in listed.tools:
            if tool.name == config.APPROVED_WRITE_TOOL:
                return dict(_attr(tool, "input_schema", "inputSchema"))
        raise RuntimeError(f"{config.APPROVED_WRITE_TOOL} not found on the portal")

    async def call_write_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        """Approved drafts only (called by the app/harness, never the model)."""
        session = self.servers["reviewer-portal"].session
        result = await session.call_tool(config.APPROVED_WRITE_TOOL, args)
        if _attr(result, "is_error", "isError"):
            text = " ".join(getattr(c, "text", "") for c in result.content)
            raise RuntimeError(text or "portal write failed")
        return _attr(result, "structured_content", "structuredContent") or {}

    async def call_read_tool(self, server: str, name: str, args: dict[str, Any]):
        result = await self.servers[server].session.call_tool(name, args)
        return _attr(result, "structured_content", "structuredContent") or {}

    def build(self, store: gate.DraftStore):
        from agents import Agent, FunctionTool, ModelSettings, OpenAIResponsesModel

        drafted: list[str] = []

        async def _draft(ctx, raw: str) -> str:
            args = json.loads(raw or "{}")
            draft = store.add(args)
            drafted.append(draft.draft_id)
            return gate.draft_result(draft)

        draft_tool = FunctionTool(
            name=config.DRAFT_TOOL,
            description=gate.DRAFT_DESCRIPTION,
            params_json_schema=gate.draft_schema(self.submit_schema or {}),
            on_invoke_tool=_draft,
            strict_json_schema=False,
        )
        agent = Agent(
            name="nitrd-review-assistant",
            instructions=config.instructions(),
            tools=[draft_tool],
            mcp_servers=list(self.servers.values()),
            model=OpenAIResponsesModel(config.MODEL, self.client),
            model_settings=ModelSettings(parallel_tool_calls=False),
        )
        return agent, drafted

    async def exposed_tools(self, agent) -> list[str]:
        """Tool names the model is offered (after the gate's filter)."""
        from agents import RunContextWrapper

        tools = await agent.get_all_tools(RunContextWrapper(context=None))
        return sorted(t.name for t in tools)

    async def run(self, prompt: str, store: gate.DraftStore) -> RunRecord:
        from agents import Runner
        from agents.items import ToolCallItem

        rec = RunRecord(prompt=prompt)
        agent, drafted = self.build(store)
        rec.exposed_tools = await self.exposed_tools(agent)
        t0 = time.monotonic()
        try:
            result = await Runner.run(agent, prompt, max_turns=config.MAX_TURNS)
            for item in result.new_items:
                if isinstance(item, ToolCallItem):
                    raw = item.raw_item
                    name = getattr(raw, "name", None) or getattr(raw, "type", "?")
                    args = getattr(raw, "arguments", None) or "{}"
                    try:
                        parsed = json.loads(args) if isinstance(args, str) else args
                    except ValueError:
                        parsed = {"_unparsed": args}
                    rec.calls.append({"name": name, "args": parsed})
            rec.final = str(result.final_output or "")
            rec.turns = len(result.raw_responses)
        except Exception as exc:  # recorded; the run counts as a failure
            rec.error = f"{type(exc).__name__}: {exc}"[:2000]
        rec.latency_s = round(time.monotonic() - t0, 2)
        rec.drafts = list(drafted)
        return rec


def disable_sdk_tracing() -> None:
    """The SDK's default trace exporter targets api.openai.com; turn it off."""
    from agents import set_tracing_disabled

    set_tracing_disabled(True)
