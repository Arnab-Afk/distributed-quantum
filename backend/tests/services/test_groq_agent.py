import asyncio
import json

import httpx
import pytest

from services.groq_agent import complete


@pytest.fixture(autouse=True)
def default_provider(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "groq")


def test_tool_results_are_returned_to_model_and_executed_once():
    requests, executed = [], []
    def respond(request):
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            message = {"role": "assistant", "content": None, "tool_calls": [{"id": "call1", "type": "function", "function": {"name": "lookup", "arguments": '{"id":"run1"}'}}]}
        else:
            assert body["messages"][-1]["role"] == "tool"
            assert json.loads(body["messages"][-1]["content"]) == {"result": 42}
            message = {"role": "assistant", "content": "The result is 42."}
        return httpx.Response(200, json={"choices": [{"message": message}]})
    async def invoke(name, args):
        executed.append((name, args))
        return {"result": 42}
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await complete([{"role": "user", "content": "Lookup"}], tools=[{"type":"function","function":{"name":"lookup","parameters":{"type":"object"}}}], invoke=invoke, client=client, api_key="test")
    assert asyncio.run(run()) == "The result is 42."
    assert executed == [("lookup", {"id": "run1"})]


def test_rate_limit_is_reported_without_retry():
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(429, headers={"retry-after":"37"}))) as client:
            with pytest.raises(ValueError, match="Wait about 37 seconds"):
                await complete([{"role":"user","content":"hello"}], client=client, api_key="test")
    asyncio.run(run())


def test_missing_key_fails_without_provider_fallback(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        asyncio.run(complete([{"role":"user","content":"hello"}]))


def test_chat_uses_existing_platform_tools_without_coinbase_x402(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from services.ai_agent_service import AIAgentService

    completion = AsyncMock(return_value="Draft ready for review.")
    monkeypatch.setattr("services.groq_agent.complete", completion)
    service = AIAgentService.__new__(AIAgentService)
    service.db = MagicMock()
    reply = asyncio.run(service.chat("agent1", "Researcher", "Draft a report", owner_id="user1"))
    assert reply == "Draft ready for review."
    tools = completion.call_args.kwargs["tools"]
    names = {tool["function"]["name"] for tool in tools}
    assert "list_proposals" in names
    assert "get_wallet" in names
    assert not any("x402" in name.lower() for name in names)


def test_storage_proposal_pauses_for_user_without_second_inference():
    def respond(request):
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "tool_calls": [{"id": "s1", "type": "function", "function": {"name": "prepare_storage_export", "arguments": "{}"}}]}}]})
    async def invoke(name, args):
        return {"status": "pending", "title": "Draft", "usdc": "0.000001"}
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await complete([], tools=[{"function": {"name": "prepare_storage_export"}}], invoke=invoke, client=client, api_key="test")
    assert "Nothing has been uploaded or paid" in asyncio.run(run())


def test_openrouter_uses_only_zero_price_tool_capable_routes(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free")
    def respond(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        body = json.loads(request.content)
        assert body["provider"] == {"require_parameters": True, "max_price": {"prompt": 0, "completion": 0}}
        assert "parallel_tool_calls" not in body
        assert body["max_tokens"] == 2048
        return httpx.Response(200, json={"choices": [{"message": {"content": "Draft ready"}}]})
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            return await complete([], client=client, api_key="test")
    assert asyncio.run(run()) == "Draft ready"


def test_openrouter_refuses_paid_model_before_network(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_MODEL", "paid/model")
    with pytest.raises(ValueError, match="Only free"):
        asyncio.run(complete([], api_key="test"))
