from __future__ import annotations

from contextlib import contextmanager

from app import agent as agent_module


class ManagedPrompt:
    version = 3

    def compile(self, **variables: str) -> str:
        return (
            f"Feature={variables['feature']}\n"
            f"Docs={variables['docs']}\n"
            f"Question={variables['message']}"
        )


class RecordingLangfuseClient:
    def __init__(self) -> None:
        self.prompt = ManagedPrompt()
        self.span_updates: list[dict] = []

    def get_prompt(self, name: str, **kwargs):
        return self.prompt

    def update_current_span(self, **kwargs) -> None:
        self.span_updates.append(kwargs)


def test_agent_records_prompt_version_with_v4_observation_api(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("LANGFUSE_PROMPT_LABEL", "production")
    client = RecordingLangfuseClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    propagated: list[dict] = []

    @contextmanager
    def record_attributes(**kwargs):
        propagated.append(kwargs)
        yield

    monkeypatch.setattr(agent_module, "propagate_attributes", record_attributes)

    agent = agent_module.LabAgent()
    agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="Explain traces",
        correlation_id="req-12345678",
    )

    span_update = client.span_updates[-1]
    assert span_update["metadata"] == {
        "doc_count": 1,
        "query_preview": "Explain traces",
        "prompt_name": "day13-chat",
        "prompt_label": "production",
        "prompt_version": "3",
        "prompt_source": "langfuse",
        "prompt_fetch_error": "",
    }
    assert span_update["version"] == "3"
    assert propagated[0]["metadata"]["correlation_id"] == "req-12345678"
    assert propagated[-1]["prompt"] is client.prompt


class GenerationRecordingClient(RecordingLangfuseClient):
    def __init__(self) -> None:
        super().__init__()
        self.generation_updates: list[dict] = []

    def update_current_generation(self, **kwargs) -> None:
        self.generation_updates.append(kwargs)

    def get_current_trace_id(self) -> str:
        return "trace-abc"


def test_generation_observation_receives_model_usage_cost_and_prompt(monkeypatch) -> None:
    client = GenerationRecordingClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    agent = agent_module.LabAgent()
    result = agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="My email is student@vinuni.edu.vn, explain traces",
        correlation_id="req-12345678",
    )

    generation = client.generation_updates[-1]
    assert generation["model"] == agent.model
    assert generation["prompt"] is client.prompt
    assert generation["usage_details"]["input"] == result.tokens_in
    assert generation["usage_details"]["output"] == result.tokens_out
    assert generation["cost_details"]["total"] == result.cost_usd
    assert "student@" not in str(generation["input"])
    retrieval = client.span_updates[0]
    assert retrieval["output"]["doc_count"] == 1
    assert "student@" not in str(retrieval["input"])
    assert result.trace_id == "trace-abc"
