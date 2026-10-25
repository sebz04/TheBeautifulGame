from pathlib import Path

import pytest
from mcp import Client
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from matchmind.agents.runtime import (
    PROMPT_DIR,
    FakeCall,
    FakeChatClient,
    FakeReply,
    configure_tracing,
    make_agent,
    make_chat_client,
    run_agent,
    stats_tools,
    tool_call,
)
from matchmind.config import Settings
from matchmind.mcp_server.server import TOOL_NAMES, build_mcp
from matchmind.store.blob import LocalBackend, TrackingStore
from matchmind.store.db import Repo


class Answer(BaseModel):
    headline: str
    count: int


@pytest.fixture
def prompt(tmp_path: Path) -> str:
    path = tmp_path / "tester.v1.md"
    path.write_text("You are the test agent. Reply in JSON.")
    return str(path)


async def test_fake_client_structured_output(prompt: str) -> None:
    client = FakeChatClient({"*": '{"headline": "Press won the ball", "count": 4}'})
    agent = make_agent("tester", prompt, Answer, tools=None, client=client)
    response = await agent.run("Explain moment m1")
    assert response.value == Answer(headline="Press won the ball", count=4)


async def test_fake_client_routes_by_text_and_records_calls(prompt: str) -> None:
    client = FakeChatClient({"moment m2": '{"headline": "b", "count": 2}', "*": "{}"})
    agent = make_agent("tester", prompt, Answer, tools=None, client=client)
    assert (await agent.run("Explain moment m2")).value == Answer(headline="b", count=2)
    (call,) = client.calls
    assert "test agent" in call.instructions and "moment m2" in call.text


async def test_fake_client_callable_and_missing_reply(prompt: str) -> None:
    client = FakeChatClient(lambda call: Answer(headline=call.text[-2:], count=1).model_dump_json())
    agent = make_agent("tester", prompt, Answer, tools=None, client=client)
    assert (await agent.run("moment m7")).value == Answer(headline="m7", count=1)
    strict = make_agent("tester", prompt, Answer, tools=None, client=FakeChatClient({"x": "{}"}))
    with pytest.raises(KeyError, match="no fake reply"):
        await strict.run("nothing matches")


def test_prompt_file_by_name_resolves_in_prompt_dir() -> None:
    assert PROMPT_DIR.name == "prompts" and PROMPT_DIR.parent.name == "agents"
    with pytest.raises(FileNotFoundError):
        make_agent("x", "missing.v1.md", Answer, tools=None, client=FakeChatClient({}))


async def test_run_agent_emits_span_with_moment_and_attempt(prompt: str) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    client = FakeChatClient({"*": '{"headline": "h", "count": 0}'})
    agent = make_agent("tester", prompt, Answer, tools=None, client=client)
    result = await run_agent(
        agent, "m1", moment_id="m1", attempt=2, tracer=provider.get_tracer("t")
    )
    assert result.value == Answer(headline="h", count=0)
    (span,) = [s for s in exporter.get_finished_spans() if s.name == "agent_run tester"]
    assert span.attributes is not None
    assert span.attributes["matchmind.moment_id"] == "m1"
    assert span.attributes["matchmind.attempt"] == 2
    assert span.attributes["matchmind.agent"] == "tester"


async def test_run_agent_marks_span_on_error(prompt: str) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    agent = make_agent("tester", prompt, Answer, tools=None, client=FakeChatClient({}))
    with pytest.raises(KeyError):
        await run_agent(agent, "m1", moment_id="m1", attempt=1, tracer=provider.get_tracer("t"))
    (span,) = exporter.get_finished_spans()
    assert not span.status.is_ok


async def test_stats_tools_load_the_mcp_server(tmp_path: Path) -> None:
    server = build_mcp(Repo(f"sqlite:///{tmp_path}/x.db"), TrackingStore(LocalBackend(tmp_path)))
    async with Client(server) as mcp_client:
        tool = stats_tools(Settings(_env_file=None), session=mcp_client.session)
        async with tool:
            assert sorted(f.name for f in tool.functions) == sorted(TOOL_NAMES)
            summary = next(f for f in tool.functions if f.name == "get_match_summary")
            result = await summary.invoke(arguments={"match_id": "nope"})
            assert "error" in str(result[0].text)


def test_stats_tools_point_at_the_mcp_url() -> None:
    tool = stats_tools(Settings(_env_file=None, mcp_url="http://localhost:9000/mcp"))
    assert tool.url == "http://localhost:9000/mcp"


def test_make_chat_client_needs_an_endpoint() -> None:
    with pytest.raises(RuntimeError, match="FOUNDRY_PROJECT_ENDPOINT"):
        make_chat_client(Settings(_env_file=None, foundry_project_endpoint=None))


def test_configure_tracing_is_off_without_a_connection_string() -> None:
    assert configure_tracing(Settings(_env_file=None, appinsights_connection_string=None)) is False


def test_configure_tracing_warns_and_stays_off_on_a_bad_connection_string(caplog) -> None:
    settings = Settings(_env_file=None, appinsights_connection_string="not-a-connection-string")
    assert configure_tracing(settings) is False
    assert "connection string" in caplog.text


async def test_fake_client_can_call_tools(prompt: str) -> None:
    from agent_framework import tool

    seen: list[str] = []

    @tool
    def get_moment(moment_id: str) -> str:
        """Look up a moment."""
        seen.append(moment_id)
        return '{"kind": "goal"}'

    def reply(call: FakeCall) -> FakeReply:
        if not call.tool_results:
            return [tool_call("get_moment", moment_id="m1")]
        return Answer(headline=call.tool_results[0], count=1).model_dump_json()

    agent = make_agent("tester", prompt, Answer, tools=[get_moment], client=FakeChatClient(reply))
    response = await agent.run("go")
    assert seen == ["m1"]
    assert response.value == Answer(headline='{"kind": "goal"}', count=1)


async def test_fake_client_rejects_a_reply_that_breaks_the_output_model(prompt: str) -> None:
    """Like the real client: the reply is parsed into response_format inside the client."""
    from agent_framework.exceptions import ChatClientException

    agent = make_agent("tester", prompt, Answer, tools=None, client=FakeChatClient({"*": "{}"}))
    with pytest.raises(ChatClientException, match="headline"):
        await agent.run("go")


# --- retries, run logging, throttling (TASK-20) ----------------------------------------


def _flaky(failures: int, error: str = "Error code: 429 - Too Many Requests") -> FakeChatClient:
    """Raises ``error`` ``failures`` times, then answers."""
    from agent_framework.exceptions import ChatClientException

    state = {"n": 0}

    def reply(call: FakeCall) -> FakeReply:
        state["n"] += 1
        if state["n"] <= failures:
            raise ChatClientException(error)
        return Answer(headline="ok", count=state["n"]).model_dump_json()

    return FakeChatClient(reply)


async def test_transient_errors_retry_with_backoff(prompt: str) -> None:
    from matchmind.agents.runtime import RunLog, pipeline_scope

    sleeps: list[float] = []

    async def sleep(s: float) -> None:
        sleeps.append(s)

    log = RunLog()
    agent = make_agent("tester", prompt, Answer, tools=None, client=_flaky(2))
    with pipeline_scope(log=log, sleep=sleep):
        response = await run_agent(agent, "go", moment_id="m1", attempt=1)
    assert response.value == Answer(headline="ok", count=3)
    assert sleeps == [1.0, 2.0]
    (run,) = log.runs
    assert (run.agent, run.moment_id, run.status, run.attempts) == ("tester", "m1", "retry", 3)


async def test_transient_errors_give_up_after_three_retries(prompt: str) -> None:
    from agent_framework.exceptions import ChatClientException

    from matchmind.agents.runtime import RunLog, pipeline_scope

    sleeps: list[float] = []

    async def sleep(s: float) -> None:
        sleeps.append(s)

    log = RunLog()
    agent = make_agent("tester", prompt, Answer, tools=None, client=_flaky(9, "Request timed out."))
    with pipeline_scope(log=log, sleep=sleep), pytest.raises(ChatClientException):
        await run_agent(agent, "go", moment_id="m1", attempt=1)
    assert sleeps == [1.0, 2.0, 4.0]
    assert log.runs[0].status == "failed" and "timed out" in (log.runs[0].error or "")


async def test_other_errors_are_not_retried(prompt: str) -> None:
    from agent_framework.exceptions import ChatClientException

    from matchmind.agents.runtime import RunLog, pipeline_scope

    log = RunLog()
    agent = make_agent("tester", prompt, Answer, tools=None, client=FakeChatClient({"*": "{}"}))
    with pipeline_scope(log=log), pytest.raises(ChatClientException):
        await run_agent(agent, "go", moment_id="m1", attempt=1)  # malformed: no retry here
    assert log.runs[0].attempts == 1 and log.runs[0].status == "failed"


async def test_run_log_counts_tokens(prompt: str) -> None:
    from matchmind.agents.runtime import RunLog, pipeline_scope

    log = RunLog()
    agent = make_agent("tester", prompt, Answer, tools=None, client=_flaky(0))
    with pipeline_scope(log=log):
        await run_agent(agent, "x" * 400, moment_id=None, attempt=1)
    (run,) = log.runs
    assert run.tokens_in >= 100 and run.tokens_out > 0 and run.status == "ok"
    assert log.tokens() == (run.tokens_in, run.tokens_out)


async def test_token_bucket_waits_for_capacity() -> None:
    from matchmind.agents.runtime import TokenBucket

    now = [0.0]
    sleeps: list[float] = []

    async def sleep(s: float) -> None:
        sleeps.append(s)
        now[0] += s

    bucket = TokenBucket(tpm=600, clock=lambda: now[0], sleep=sleep)  # 10 tokens a second
    await bucket.acquire(600)
    assert sleeps == []
    await bucket.acquire(100)
    assert sum(sleeps) == pytest.approx(10.0)
