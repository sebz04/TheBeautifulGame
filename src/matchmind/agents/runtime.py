"""Agent runtime: the Foundry chat client, a fake client for tests, MCP tools, and tracing.

Every agent is an Agent Framework ``Agent`` over a ``FoundryChatClient`` (keyless, via
``DefaultAzureCredential``), with its instructions read from a versioned prompt file and
its output parsed into a pydantic model. Tests use ``FakeChatClient`` and never call a
live model (Constitution IV).

Smoke test against the real deployment: ``uv run python -m matchmind.agents.runtime --ping``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_framework import (
    Agent,
    AgentResponse,
    BaseChatClient,
    ChatResponse,
    FunctionInvocationLayer,
    MCPStreamableHTTPTool,
    Message,
    SupportsChatGetResponse,
)
from agent_framework.observability import configure_otel_providers
from mcp import ClientSession
from opentelemetry import trace
from pydantic import BaseModel

from matchmind.config import Settings, get_settings
from matchmind.mcp_server.server import TOOL_NAMES

PROMPT_DIR = Path(__file__).parent / "prompts"
TRACER_NAME = "matchmind.agents"

_tracing_on = False
log = logging.getLogger(__name__)


def make_chat_client(settings: Settings, credential: Any = None) -> SupportsChatGetResponse[Any]:
    """The Foundry chat client for ``settings``' project and model deployment.

    Keyless: ``credential`` defaults to ``DefaultAzureCredential`` (``az login`` locally,
    managed identity in Azure). Pass your own to close it when done.
    """
    if not settings.foundry_project_endpoint:
        raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT is not set (copy .env.example to .env)")
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    return FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint,
        model=settings.foundry_model_deployment,
        credential=credential or DefaultAzureCredential(),
    )


@dataclass(frozen=True)
class FakeCall:
    """One request the fake client received."""

    instructions: str
    text: str
    messages: Sequence[Message]
    options: Mapping[str, Any]


FakeReplies = Mapping[str, str] | Callable[[FakeCall], str]


class FakeChatClient(FunctionInvocationLayer[Any], BaseChatClient[Any]):
    """A chat client that answers from canned replies, for tests.

    ``responses`` is either a callable ``(FakeCall) -> str`` or a mapping from a
    substring to the reply: the first key found in the instructions or messages wins,
    and ``"*"`` is the fallback. Every request is kept in ``calls``.
    """

    def __init__(self, responses: FakeReplies) -> None:
        super().__init__()
        self.responses = responses
        self.calls: list[FakeCall] = []

    def _reply(self, call: FakeCall) -> str:
        if callable(self.responses):
            return self.responses(call)
        haystack = f"{call.instructions}\n{call.text}"
        for key, reply in self.responses.items():
            if key != "*" and key in haystack:
                return reply
        if "*" in self.responses:
            return self.responses["*"]
        raise KeyError(f"no fake reply for {call.text[:80]!r}")

    async def _respond(
        self, messages: Sequence[Message], options: Mapping[str, Any]
    ) -> ChatResponse:
        await self._validate_options(options)
        call = FakeCall(
            instructions=str(options.get("instructions") or ""),
            text="\n".join(m.text for m in messages),
            messages=list(messages),
            options=dict(options),
        )
        self.calls.append(call)
        return ChatResponse(
            messages=[Message("assistant", [self._reply(call)])],
            response_format=options.get("response_format"),
        )

    def _inner_get_response(
        self, *, messages: Sequence[Message], stream: bool, options: Mapping[str, Any], **_: Any
    ) -> Any:
        if stream:
            raise NotImplementedError("FakeChatClient does not stream")
        return self._respond(messages, options)


def _prompt_path(prompt_file: str) -> Path:
    path = Path(prompt_file)
    return path if path.is_absolute() else PROMPT_DIR / path


def make_agent(
    name: str,
    prompt_file: str,
    output_model: type[BaseModel] | None,
    tools: Any,
    *,
    client: SupportsChatGetResponse[Any],
) -> Agent[Any]:
    """An agent whose instructions come from ``prompt_file`` (in ``PROMPT_DIR`` unless
    absolute) and whose replies parse into ``output_model`` (``response.value``)."""
    instructions = _prompt_path(prompt_file).read_text(encoding="utf-8")
    options = {"response_format": output_model} if output_model else None
    return Agent(client, instructions, name=name, tools=tools, default_options=options)


async def run_agent(
    agent: Agent[Any],
    message: str,
    *,
    moment_id: str | None,
    attempt: int,
    tracer: trace.Tracer | None = None,
) -> AgentResponse[Any]:
    """Run ``agent`` once inside a span carrying the agent, ``moment_id``, and ``attempt``.

    A failure is recorded on the span (status ERROR) and re-raised for the caller's
    retry policy.
    """
    tracer = tracer or trace.get_tracer(TRACER_NAME)
    attributes: dict[str, str | int] = {
        "matchmind.agent": agent.name or "agent",
        "matchmind.moment_id": moment_id or "",
        "matchmind.attempt": attempt,
    }
    with tracer.start_as_current_span(f"agent_run {agent.name}", attributes=attributes):
        return await agent.run(message)


def stats_tools(
    settings: Settings, *, session: ClientSession | None = None
) -> MCPStreamableHTTPTool:
    """The MCP stats server's tools, over streamable HTTP at ``settings.mcp_url``.

    Pass ``session`` (an open MCP client session) to use a server in the same process
    instead, as tests do. Use it as an async context manager to connect.
    """
    common: dict[str, Any] = {
        "description": "Read-only, event-exact match statistics with refs",
        "allowed_tools": TOOL_NAMES,
        "load_prompts": False,
    }
    if session is not None:
        return MCPStreamableHTTPTool("matchmind-stats", session=session, **common)
    return MCPStreamableHTTPTool("matchmind-stats", settings.mcp_url, **common)


def configure_tracing(settings: Settings) -> bool:
    """Send traces to Application Insights. Off (returns False) without a valid connection
    string: tracing never stops the app from running.

    Agent Framework's own chat and tool spans are enabled too. Safe to call more than once.
    """
    global _tracing_on
    if not settings.appinsights_connection_string:
        return False
    if not _tracing_on:
        from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter

        try:
            exporter = AzureMonitorTraceExporter(
                connection_string=settings.appinsights_connection_string
            )
        except ValueError:
            log.warning(
                "Tracing off: MATCHMIND_APPINSIGHTS_CONNECTION_STRING is not a valid connection "
                "string (it starts with 'InstrumentationKey=')"
            )
            return False
        configure_otel_providers(service_name="matchmind", exporters=[exporter])
        _tracing_on = True
    return True


async def _ping(settings: Settings) -> None:
    from azure.identity.aio import DefaultAzureCredential

    async with DefaultAzureCredential() as credential:
        client = make_chat_client(settings, credential)
        agent = Agent(client, "Reply with the single word: pong", name="ping")
        start = time.perf_counter()
        response = await agent.run("ping")
    ms = (time.perf_counter() - start) * 1000
    print(f"{settings.foundry_model_deployment}: {response.text!r} in {ms:.0f} ms")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m matchmind.agents.runtime")
    parser.add_argument("--ping", action="store_true", help="call the Foundry deployment once")
    args = parser.parse_args(argv)
    if args.ping:
        settings = get_settings()
        configure_tracing(settings)
        asyncio.run(_ping(settings))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
