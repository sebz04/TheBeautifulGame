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
import contextlib
import contextvars
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_framework import (
    Agent,
    AgentResponse,
    BaseChatClient,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    MCPStreamableHTTPTool,
    Message,
    SupportsChatGetResponse,
    UsageDetails,
)
from agent_framework.exceptions import ChatClientException
from agent_framework.observability import configure_otel_providers
from mcp import ClientSession
from opentelemetry import trace
from pydantic import BaseModel, ValidationError

from matchmind.config import Settings, get_settings
from matchmind.mcp_server.server import TOOL_NAMES
from matchmind.schemas import AgentRun

PROMPT_DIR = Path(__file__).parent / "prompts"
TRACER_NAME = "matchmind.agents"

_tracing_on = False
log = logging.getLogger(__name__)


def make_chat_client(
    settings: Settings, credential: Any = None, middleware: Sequence[Any] | None = None
) -> SupportsChatGetResponse[Any]:
    """The Foundry chat client for ``settings``' project and model deployment.

    Keyless: ``credential`` defaults to ``DefaultAzureCredential`` (``az login`` locally,
    managed identity in Azure). Pass your own to close it when done. ``middleware`` is
    chat middleware for every call (the fixture recorder uses it).
    """
    if not settings.foundry_project_endpoint:
        raise RuntimeError("FOUNDRY_PROJECT_ENDPOINT is not set (copy .env.example to .env)")
    from agent_framework.foundry import FoundryChatClient
    from azure.identity.aio import DefaultAzureCredential

    return FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint,
        model=settings.foundry_model_deployment,
        credential=credential or DefaultAzureCredential(),
        middleware=middleware,
    )


@dataclass(frozen=True)
class FakeCall:
    """One request the fake client received."""

    instructions: str
    text: str
    messages: Sequence[Message]
    options: Mapping[str, Any]

    @property
    def tool_results(self) -> list[str]:
        """Results of the tool calls made so far in this run, as text, in order."""
        return [
            str(c.result) for m in self.messages for c in m.contents if c.type == "function_result"
        ]


FakeReply = str | Sequence[Content]
FakeReplies = Mapping[str, FakeReply] | Callable[[FakeCall], FakeReply]


def tool_call(tool_name: str, /, **arguments: Any) -> Content:
    """A tool call for a ``FakeChatClient`` reply; the agent runs the tool and asks again.
    (Positional-only, since ``get_metric`` has an argument called ``name``.)"""
    return Content.from_function_call(
        call_id=f"call_{tool_name}_{len(arguments)}_{abs(hash(str(arguments)))}",
        name=tool_name,
        arguments=arguments,
    )


class FakeChatClient(FunctionInvocationLayer[Any], BaseChatClient[Any]):
    """A chat client that answers from canned replies, for tests.

    ``responses`` is either a callable ``(FakeCall) -> reply`` or a mapping from a
    substring to the reply: the first key found in the instructions or messages wins,
    and ``"*"`` is the fallback. A reply is text, or a list of ``tool_call(...)``
    contents: the agent runs those tools and calls the client again with the results.
    Every request is kept in ``calls``.
    """

    def __init__(self, responses: FakeReplies) -> None:
        super().__init__()
        self.responses = responses
        self.calls: list[FakeCall] = []

    def _reply(self, call: FakeCall) -> FakeReply:
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
        reply = self._reply(call)
        model = options.get("response_format")
        if isinstance(reply, str) and isinstance(model, type) and issubclass(model, BaseModel):
            try:  # the real client parses inside the request, so a bad reply fails the call
                model.model_validate_json(reply)
            except ValidationError as exc:
                raise ChatClientException(
                    f"{type(self)} service failed to complete the prompt: {exc}",
                    inner_exception=exc,
                ) from exc
        contents = [reply] if isinstance(reply, str) else list(reply)
        text_out = reply if isinstance(reply, str) else str(reply)
        return ChatResponse(
            messages=[Message("assistant", contents)],
            response_format=options.get("response_format"),
            usage_details=UsageDetails(  # an estimate: about 4 characters a token
                input_token_count=(len(call.instructions) + len(call.text)) // 4,
                output_token_count=max(1, len(text_out) // 4),
            ),
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
    options: Mapping[str, Any] | None = None,
) -> Agent[Any]:
    """An agent whose instructions come from ``prompt_file`` (in ``PROMPT_DIR`` unless
    absolute) and whose replies parse into ``output_model`` (``response.value``).
    ``options`` are extra chat options for every run, such as ``temperature``."""
    instructions = _prompt_path(prompt_file).read_text(encoding="utf-8")
    merged: dict[str, Any] = dict(options or {})
    if output_model:
        merged["response_format"] = output_model
    return Agent(client, instructions, name=name, tools=tools, default_options=merged or None)


# ---- retries, run logging, throttling ----------------------------------------------------

BACKOFF_S = (1.0, 2.0, 4.0)  # then give up: the pipeline shows a template
_TRANSIENT_TEXT = ("429", "too many requests", "rate limit", "timed out", "timeout",
                   "temporarily unavailable", "503", "502", "connection error")  # fmt: skip


def is_transient(exc: BaseException) -> bool:
    """A timeout, a 429, or a server or connection error: worth retrying after a pause."""
    seen: set[int] = set()
    stack: list[BaseException] = [exc]
    while stack:
        e = stack.pop()
        if id(e) in seen:
            continue
        seen.add(id(e))
        name = type(e).__name__
        if name in ("RateLimitError", "APITimeoutError", "APIConnectionError",
                    "InternalServerError", "TimeoutError"):  # fmt: skip
            return True
        if getattr(e, "status_code", None) in (429, 500, 502, 503, 504):
            return True
        if any(t in str(e).lower() for t in _TRANSIENT_TEXT) and not isinstance(e, ValidationError):
            return True
        stack += [a for a in e.args if isinstance(a, BaseException)]
        stack += [x for x in (e.__cause__, e.__context__) if x is not None]
    return False


@dataclass
class RunLog:
    """Every agent call in a pipeline run, as ``AgentRun`` rows (for the stats store)."""

    runs: list[AgentRun] = field(default_factory=list)

    def tokens(self) -> tuple[int, int]:
        return sum(r.tokens_in for r in self.runs), sum(r.tokens_out for r in self.runs)


class TokenBucket:
    """Throttle to a tokens-per-minute quota: ``acquire`` waits until the estimate fits,
    ``settle`` corrects it with what the call really used."""

    def __init__(
        self,
        tpm: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.capacity, self.rate = float(tpm), tpm / 60.0
        self.clock, self.sleep = clock, sleep
        self.level, self.at = float(tpm), clock()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = self.clock()
        self.level = min(self.capacity, self.level + (now - self.at) * self.rate)
        self.at = now

    async def acquire(self, tokens: int) -> None:
        need = min(float(tokens), self.capacity)
        async with self._lock:
            self._refill()
            while self.level < need:
                await self.sleep((need - self.level) / self.rate)
                self._refill()
            self.level -= need

    def settle(self, estimated: int, actual: int) -> None:
        self.level += estimated - actual


@dataclass
class _Scope:
    log: RunLog | None = None
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    limiter: TokenBucket | None = None
    backoff: tuple[float, ...] = BACKOFF_S


_SCOPE: contextvars.ContextVar[_Scope | None] = contextvars.ContextVar(
    "matchmind_scope", default=None
)


@contextlib.contextmanager
def pipeline_scope(
    *,
    log: RunLog | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    limiter: TokenBucket | None = None,
    backoff: tuple[float, ...] = BACKOFF_S,
) -> Iterator[None]:
    """Within this block every ``run_agent`` call is logged to ``log``, throttled by
    ``limiter``, and retried on transient errors with ``backoff`` pauses (via ``sleep``)."""
    token = _SCOPE.set(_Scope(log, sleep or asyncio.sleep, limiter, backoff))
    try:
        yield
    finally:
        _SCOPE.reset(token)


async def run_agent(
    agent: Agent[Any],
    message: str,
    *,
    moment_id: str | None,
    attempt: int,
    tracer: trace.Tracer | None = None,
) -> AgentResponse[Any]:
    """Run ``agent`` once inside a span carrying the agent, ``moment_id``, and ``attempt``.

    Timeouts and 429s are retried after 1 s, 2 s, and 4 s pauses, then raised. Any other
    failure is raised at once (status ERROR on the span) for the caller to handle. With a
    ``pipeline_scope``, the call is throttled and logged as an ``AgentRun``.
    """
    scope = _SCOPE.get() or _Scope()
    tracer = tracer or trace.get_tracer(TRACER_NAME)
    name = agent.name or "agent"
    attributes: dict[str, str | int] = {
        "matchmind.agent": name,
        "matchmind.moment_id": moment_id or "",
        "matchmind.attempt": attempt,
    }
    estimate = (len(message) + len(str(getattr(agent, "instructions", "") or ""))) // 4 + 500
    start, tries = time.perf_counter(), 0
    with tracer.start_as_current_span(f"agent_run {name}", attributes=attributes) as span:
        context = span.get_span_context()
        trace_hex = format(context.trace_id, "032x") if context.is_valid else None
        while True:
            tries += 1
            if scope.limiter is not None:
                await scope.limiter.acquire(estimate)
            try:
                response = await agent.run(message)
            except Exception as exc:
                if scope.limiter is not None:
                    scope.limiter.settle(estimate, estimate // 4)
                if is_transient(exc) and tries <= len(scope.backoff):
                    await scope.sleep(scope.backoff[tries - 1])
                    continue
                _log(scope, name, moment_id, "failed", tries, start, trace_hex, str(exc)[:500])
                raise
            usage = response.usage_details or {}
            t_in = int(usage.get("input_token_count") or 0)
            t_out = int(usage.get("output_token_count") or 0)
            if scope.limiter is not None:
                scope.limiter.settle(estimate, t_in + t_out)
            status = "retry" if tries > 1 else "ok"
            _log(scope, name, moment_id, status, tries, start, trace_hex, None, t_in, t_out)
            if trace_hex:
                response.additional_properties["trace_id"] = trace_hex
            return response


def _log(scope: _Scope, agent: str, moment_id: str | None, status: str, attempts: int,
         start: float, trace_hex: str | None, error: str | None, t_in: int = 0,
         t_out: int = 0) -> None:  # fmt: skip
    if scope.log is not None:
        scope.log.runs.append(AgentRun(
            run_id=uuid.uuid4().hex, agent=agent, moment_id=moment_id, status=status,
            attempts=attempts, latency_ms=round((time.perf_counter() - start) * 1000),
            trace_id=trace_hex, error=error, tokens_in=t_in, tokens_out=t_out,
        ))  # fmt: skip


def trace_id(response: AgentResponse[Any]) -> str | None:
    """The trace id ``run_agent`` recorded (None when tracing is off)."""
    value = response.additional_properties.get("trace_id")
    return str(value) if value else None


def problem_text(exc: ValidationError) -> str:
    """A pydantic error as one line the model can act on."""
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'answer'}: {e['msg']}" for e in exc.errors()
    )


def bad_reply(exc: Exception) -> str | None:
    """Why the model's reply didn't fit the output model, or None for any other failure.

    The Foundry client parses a structured reply inside the request, so a malformed reply
    arrives as ``ChatClientException`` wrapping a ``ValidationError``. Timeouts, 429s, and
    other service errors return None: they are the caller's retry policy (TASK-20).
    """
    if not isinstance(exc, ChatClientException):
        return None
    for inner in (*exc.args, exc.__cause__):
        if isinstance(inner, ValidationError):
            return problem_text(inner)
    return None


def tool_calls(response: AgentResponse[Any]) -> list[tuple[str, dict[str, Any]]]:
    """Every tool call the model made during a run, as (name, arguments), in order."""
    calls = []
    for message in response.messages:
        for c in message.contents:
            if c.type == "function_call":
                args = c.arguments
                if isinstance(args, str):
                    args = json.loads(args or "{}")
                calls.append((str(c.name), dict(args or {})))
    return calls


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
