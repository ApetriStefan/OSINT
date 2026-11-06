"""Unit tests for Ollama client, token cleaning, JSON extraction, and num_ctx=131072."""

import json
from pydantic import BaseModel
import pytest
import responses

from src.llm.client import (
    OllamaClient,
    clean_thinking_tokens,
    extract_json_from_text,
)


class DummyModel(BaseModel):
    message: str
    count: int


def test_clean_thinking_tokens():
    """Verify thinking tags and internal monologues are stripped."""
    text_with_think = "<think>Analyzing user query and reviewing records.</think>Final answer."
    assert clean_thinking_tokens(text_with_think) == "Final answer."

    unclosed_think = "<think>Still thinking about it...\n\nResult after thought."
    assert clean_thinking_tokens(unclosed_think) == "Result after thought."

    pure_thought = "<think>Only internal monologue without content."
    assert clean_thinking_tokens(pure_thought) == ""

    clean_text = "Just a direct response without thinking tags."
    assert clean_thinking_tokens(clean_text) == clean_text


def test_extract_json_from_text():
    """Verify JSON extraction from markdown code fences and noisy preamble."""
    markdown_json = 'Here is the response:\n```json\n{"message": "success", "count": 10}\n```\nHope that helps!'
    extracted = extract_json_from_text(markdown_json)
    parsed = json.loads(extracted)
    assert parsed["message"] == "success"
    assert parsed["count"] == 10

    raw_array = "Leading noise [1, 2, 3] trailing noise"
    extracted_arr = extract_json_from_text(raw_array)
    assert extracted_arr == "[1, 2, 3]"


def test_ollama_client_preserves_131072_num_ctx():
    """CRITICAL REQUIREMENT: Verify client options default to num_ctx=131072."""
    client = OllamaClient()
    assert client.num_ctx == 131072


@responses.activate
def test_ollama_client_structured_generation():
    """Verify generate_structured passes Pydantic schema in payload format."""
    def request_callback(request):
        payload = json.loads(request.body)
        # Verify critical context window and keep_alive
        assert payload["options"]["num_ctx"] == 131072
        assert payload.get("keep_alive") == "30m"
        # Verify schema is in format
        assert "format" in payload
        assert payload["format"]["properties"]["message"]["type"] == "string"
        return (200, {}, json.dumps({"message": {"content": '{"message": "ok", "count": 42}'}}))

    responses.add_callback(
        responses.POST,
        "http://localhost:11434/api/chat",
        callback=request_callback,
        content_type="application/json"
    )

    client = OllamaClient()
    result = client.generate_structured(
        system_prompt="System instructions",
        user_prompt="Input data",
        response_model=DummyModel,
        stream=False
    )
    assert isinstance(result, DummyModel)
    assert result.message == "ok"
    assert result.count == 42


@responses.activate
def test_ollama_client_streaming_thinking_and_content_events():
    """Verify streaming handles message.thinking and message.content chunks to event sink."""
    from src.events import EventBus

    stream_chunks = [
        json.dumps({"message": {"thinking": "Analyzing scenario..."}}),
        json.dumps({"message": {"thinking": "Checking historical precedents."}}),
        json.dumps({"message": {"content": "Sinteza "}}),
        json.dumps({"message": {"content": "evenimentului."}}),
    ]
    body = "\n".join(stream_chunks) + "\n"

    responses.add(
        responses.POST,
        "http://localhost:11434/api/chat",
        body=body,
        status=200,
        content_type="application/x-ndjson"
    )

    test_bus = EventBus(max_history=50)
    client = OllamaClient()

    output = client.generate(
        system_prompt="Analist",
        user_prompt="Sinteză",
        stream=True,
        agent_name="archivist",
        run_id="run_test_thinking",
        event_sink=test_bus
    )

    assert "Sinteza evenimentului." in output
    history = test_bus.get_history()
    
    thinking_events = [ev for ev in history if ev.type == "thinking"]
    token_events = [ev for ev in history if ev.type == "token"]

    assert len(thinking_events) == 2
    assert "Analyzing scenario..." in thinking_events[0].text
    assert thinking_events[0].agent == "archivist"
    assert thinking_events[0].run_id == "run_test_thinking"

    assert len(token_events) == 2
    assert token_events[0].text == "Sinteza "
    assert token_events[1].text == "evenimentului."


@responses.activate
def test_ollama_client_streaming_inline_think_tags():
    """Verify streaming correctly parses inline <think> tags inside content."""
    from src.events import EventBus

    stream_chunks = [
        json.dumps({"message": {"content": "<think>Deliberating internal motives."}}),
        json.dumps({"message": {"content": "</think>Concluzie clară."}}),
    ]
    body = "\n".join(stream_chunks) + "\n"

    responses.add(
        responses.POST,
        "http://localhost:11434/api/chat",
        body=body,
        status=200,
        content_type="application/x-ndjson"
    )

    test_bus = EventBus(max_history=50)
    client = OllamaClient()

    output = client.generate(
        system_prompt="Analist",
        user_prompt="Sinteză",
        stream=True,
        agent_name="red_team",
        run_id="run_inline_think",
        event_sink=test_bus
    )

    assert "Concluzie clară." in output
    history = test_bus.get_history()

    thinking_events = [ev for ev in history if ev.type == "thinking"]
    token_events = [ev for ev in history if ev.type == "token"]

    assert len(thinking_events) >= 1
    assert "Deliberating internal motives." in thinking_events[0].text
    assert thinking_events[0].agent == "red_team"

    assert len(token_events) >= 1
    assert "Concluzie clară." in token_events[0].text
