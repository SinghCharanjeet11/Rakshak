"""The model layer, against a mocked provider.

Until now `llm/` had zero call-path coverage: the tests asserted its tool declarations and
its prompts, but nothing ever exercised `complete_json`, `parse` or `explain_batch`. That
left the two headline capabilities — free-text ingestion and plain-English explanations —
as claims rather than demonstrations.

A fake provider closes that without a key and without a network call. What it cannot prove
is that a *real* model returns good output; it proves that whatever the model returns is
handled correctly, which is the part the architecture actually depends on.
"""

from types import SimpleNamespace

import pytest

from app.core.models import Severity, Violation
from app.llm import _provider, explanation_agent, ingestion_agent
from app.llm._provider import LLMUnavailable, Usage, complete_json


# --------------------------------------------------------------------------
# fake provider
# --------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, content, prompt_tokens=1000, completion_tokens=500, tool_calls=None):
        self.choices = [
            SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))
        ]
        self.usage = SimpleNamespace(
            prompt_tokens=prompt_tokens, completion_tokens=completion_tokens
        )


class FakeClient:
    """Records what it was called with, so the tests can assert the contract."""

    def __init__(self, response=None, error=None):
        self.calls = []
        self._response = response
        self._error = error
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


@pytest.fixture
def fake_provider(monkeypatch):
    """Installs a fake client and hands the test a way to program its reply."""

    holder = {}

    def install(content="{}", **kw):
        client = FakeClient(response=FakeResponse(content, **kw))
        monkeypatch.setattr(_provider, "_client", lambda: client)
        holder["client"] = client
        return client

    def fail(error):
        client = FakeClient(error=error)
        monkeypatch.setattr(_provider, "_client", lambda: client)
        holder["client"] = client
        return client

    return SimpleNamespace(install=install, fail=fail, holder=holder)


# --------------------------------------------------------------------------
# cost accounting
# --------------------------------------------------------------------------


def test_usage_totals():
    u = Usage(prompt_tokens=1200, completion_tokens=800)
    assert u.total_tokens == 2000


def test_cost_is_priced_per_direction():
    """Output tokens cost 4x input at gpt-4o-mini rates; a flat average would understate
    an explanation-heavy run, which is the one that generates the most output."""
    inp = Usage(prompt_tokens=1_000_000, completion_tokens=0).cost_inr
    out = Usage(prompt_tokens=0, completion_tokens=1_000_000).cost_inr
    assert out == pytest.approx(inp * 4, rel=1e-6)


def test_cost_of_a_realistic_run_is_negligible():
    """05-requirements.md claims a run costs well under a tenth of a cent. Worth pinning:
    the run budget (Rs 5) is meaningless if the real figure is 100x this."""
    cost = Usage(prompt_tokens=4000, completion_tokens=1500).cost_inr
    assert cost < 0.15  # rupees


def test_zero_usage_is_free():
    assert Usage().cost_inr == 0.0


# --------------------------------------------------------------------------
# complete_json
# --------------------------------------------------------------------------


async def test_complete_json_returns_parsed_data_and_usage(fake_provider):
    client = fake_provider.install('{"actions": [{"id": "a_1"}]}', prompt_tokens=120, completion_tokens=45)

    resp = await complete_json("SYS", "USER", temperature=0.0)

    assert resp.data == {"actions": [{"id": "a_1"}]}
    assert resp.usage.prompt_tokens == 120
    assert resp.usage.completion_tokens == 45
    assert resp.tool_calls == []

    (kwargs,) = client.calls
    assert kwargs["temperature"] == 0.0
    assert kwargs["response_format"] == {"type": "json_object"}
    assert kwargs["messages"][0] == {"role": "system", "content": "SYS"}
    assert kwargs["messages"][1] == {"role": "user", "content": "USER"}


async def test_no_tools_are_ever_attached(fake_provider):
    """Least privilege, asserted at the call site and not only in the source."""
    client = fake_provider.install("{}")
    await complete_json("SYS", "USER")
    (kwargs,) = client.calls
    assert "tools" not in kwargs
    assert "tool_choice" not in kwargs


async def test_provider_error_becomes_llm_unavailable(fake_provider):
    fake_provider.fail(RuntimeError("connection reset"))
    with pytest.raises(LLMUnavailable, match="connection reset"):
        await complete_json("SYS", "USER")


async def test_missing_key_is_llm_unavailable(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    with pytest.raises(LLMUnavailable, match="OPENAI_API_KEY"):
        await complete_json("SYS", "USER")


async def test_non_object_json_becomes_empty_dict(fake_provider):
    """json_object mode should prevent this, but a bare array must not crash the caller."""
    fake_provider.install("[1, 2, 3]")
    assert (await complete_json("SYS", "USER")).data == {}


async def test_null_content_is_tolerated(fake_provider):
    fake_provider.install(None)
    assert (await complete_json("SYS", "USER")).data == {}


async def test_tool_calls_are_surfaced(fake_provider):
    """The ingestion agent is given no tools, so any tool call at all is out of contract
    and must reach the orchestrator's tool_call_validity signal."""
    call = SimpleNamespace(function=SimpleNamespace(name="read_file"))
    fake_provider.install("{}", tool_calls=[call])
    assert (await complete_json("SYS", "USER")).tool_calls == ["read_file"]


# --------------------------------------------------------------------------
# ingestion agent
# --------------------------------------------------------------------------


async def test_ingestion_pins_temperature_to_zero(fake_provider):
    """03-backend.md §4: temperature=0 for parsing, to maximise reproducibility."""
    client = fake_provider.install('{"actions": []}')
    await ingestion_agent.parse("some log")
    assert client.calls[0]["temperature"] == 0.0


async def test_ingestion_sends_the_log_verbatim_as_the_user_turn(fake_provider):
    client = fake_provider.install('{"actions": []}')
    await ingestion_agent.parse("[11:00 IST] act_1 RETRY")
    assert client.calls[0]["messages"][1]["content"] == "[11:00 IST] act_1 RETRY"
    assert "You convert a payment-recovery agent" in client.calls[0]["messages"][0]["content"]


async def test_ingestion_does_not_validate_its_own_output(fake_provider):
    """The membrane is the single gate. If `parse` also filtered, there would be two
    places to keep correct and one of them would silently drift."""
    fake_provider.install('{"actions": [{"totally": "invalid"}]}')
    resp = await ingestion_agent.parse("log")
    assert resp.data == {"actions": [{"totally": "invalid"}]}


@pytest.mark.parametrize(
    "raw,count,expected",
    [
        ("a\nb\nc\nd", 4, 1.0),
        ("a\nb\nc\nd", 2, 0.5),
        ("a\nb\nc\nd", 0, 0.0),
        ("", 0, 1.0),
        ("--- header ---\n# note\na", 1, 1.0),  # decoration is not a missed action
        ("a\nb", 9, 1.0),  # clamped, never above 1
    ],
)
def test_parse_coverage(raw, count, expected):
    assert ingestion_agent.parse_coverage(raw, count) == pytest.approx(expected)


# --------------------------------------------------------------------------
# explanation agent
# --------------------------------------------------------------------------


def _violation(action_id="a_1", rule_id="AFA_ABOVE_THRESHOLD"):
    return Violation(
        action_id=action_id,
        rule_id=rule_id,
        title="t",
        severity=Severity.CRITICAL,
        offending_value="o",
        clause="c",
        source="s",
    )


async def test_no_violations_makes_no_call(fake_provider):
    client = fake_provider.install('{"explanations": []}')
    out, usage = await explanation_agent.explain_batch([])
    assert out == {} and usage.total_tokens == 0
    assert client.calls == [], "a clean batch must not spend a token"


async def test_explanations_are_returned_by_action(fake_provider):
    fake_provider.install(
        '{"explanations": [{"action_id": "a_1", "text": "Because the amount exceeded."}]}'
    )
    out, usage = await explanation_agent.explain_batch([_violation()])
    assert out == {"a_1": "Because the amount exceeded."}
    assert usage.total_tokens > 0


async def test_only_decided_fields_are_sent(fake_provider):
    """The explainer is read-only over the verdict, so it is handed the citation and the
    offending value — not the machinery that could let it re-litigate the decision."""
    client = fake_provider.install('{"explanations": []}')
    await explanation_agent.explain_batch([_violation()])
    import json as _json

    sent = _json.loads(client.calls[0]["messages"][1]["content"])
    assert set(sent[0]) == {"action_id", "rule_id", "title", "clause", "offending_value"}


async def test_explainer_failure_degrades_instead_of_raising(fake_provider):
    """Invariant I9. A report with verdicts and no prose is a good report; an exception
    here would throw away six correct verdicts over a cosmetic failure."""
    fake_provider.fail(RuntimeError("502 from provider"))
    out, usage = await explanation_agent.explain_batch([_violation()])
    assert out == {} and usage.total_tokens == 0


@pytest.mark.parametrize(
    "payload",
    [
        '{"explanations": [{"action_id": "a_1"}]}',           # no text
        '{"explanations": [{"text": "orphan"}]}',              # no action_id
        '{"explanations": [{"action_id": 7, "text": "x"}]}',   # wrong type
        '{"explanations": "not a list"}',
        '{"wrong_key": []}',
        "{}",
    ],
)
async def test_malformed_explanations_are_dropped_not_crashed(fake_provider, payload):
    fake_provider.install(payload)
    out, _ = await explanation_agent.explain_batch([_violation()])
    assert out == {}


async def test_a_model_that_disputes_the_verdict_cannot_change_it(fake_provider):
    """The prompt forbids second-guessing, but prompts are not a control. Even if the model
    returns verdict fields, `explain_batch` reads only action_id and text, so they are
    dropped before anything downstream sees them (invariant I8)."""
    fake_provider.install(
        '{"explanations": [{"action_id": "a_1", "text": "Actually compliant.",'
        ' "severity": "low", "rule_id": "NONE", "verdict": "pass"}]}'
    )
    out, _ = await explanation_agent.explain_batch([_violation()])
    assert out == {"a_1": "Actually compliant."}

    v = _violation()
    before = v.model_dump(exclude={"explanation"})
    explanation_agent.attach([v], out)
    assert v.explanation == "Actually compliant."
    assert v.model_dump(exclude={"explanation"}) == before
    assert v.severity == Severity.CRITICAL and v.rule_id == "AFA_ABOVE_THRESHOLD"


def test_attach_leaves_unexplained_violations_alone():
    a, b = _violation("a_1"), _violation("a_2")
    explanation_agent.attach([a, b], {"a_1": "prose"})
    assert a.explanation == "prose"
    assert b.explanation is None
