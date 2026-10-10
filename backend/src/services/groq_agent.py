"""Free-provider inference with local tools and no paid or automatic provider fallback."""
from __future__ import annotations

import json
import logging
import math
import os
from typing import Any

import httpx


async def complete(messages: list[dict], *, tools: list[dict] | None = None,
                   invoke=None, client: httpx.AsyncClient | None = None,
                   api_key: str | None = None) -> str:
    provider = os.getenv("AGENT_LLM_PROVIDER", "groq")
    if provider not in {"groq", "openrouter"}:
        raise ValueError("AGENT_LLM_PROVIDER must be groq or openrouter.")
    label = "OpenRouter" if provider == "openrouter" else "Groq"
    key_name = "OPENROUTER_API_KEY" if provider == "openrouter" else "GROQ_API_KEY"
    model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free") if provider == "openrouter" else os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    if provider == "openrouter" and not (model.endswith(":free") or model == "openrouter/free"):
        raise ValueError("Only free OpenRouter models are permitted for this demo.")
    endpoint = "https://openrouter.ai/api/v1/chat/completions" if provider == "openrouter" else "https://api.groq.com/openai/v1/chat/completions"
    key = api_key or os.getenv(key_name)
    if not key:
        raise ValueError(f"{key_name} is not configured on the backend.")
    if client is None:
        async with httpx.AsyncClient(timeout=60) as owned:
            return await complete(messages, tools=tools, invoke=invoke, client=owned, api_key=key)
    history = list(messages)
    allowed = {tool["function"]["name"] for tool in tools or []}
    for _ in range(8):
        payload: dict[str, Any] = {
            "model": model,
            "messages": history,
            "max_tokens" if provider == "openrouter" else "max_completion_tokens": 2048,
        }
        if provider == "openrouter":
            payload["provider"] = {"require_parameters": True, "max_price": {"prompt": 0, "completion": 0}}
        if tools:
            payload.update(tools=tools, tool_choice="auto")
            if provider == "groq":
                payload["parallel_tool_calls"] = False
        response = await client.post(endpoint,
                                     headers={"Authorization": f"Bearer {key}"}, json=payload)
        if response.status_code == 429:
            try:
                seconds = max(1, math.ceil(float(response.headers.get("retry-after", ""))))
                wait = f"Wait about {seconds} seconds before sending another message."
            except (ValueError, OverflowError):
                wait = "Please wait before sending another message."
            raise ValueError(f"{label} free-plan rate limit reached. {wait}")
        if response.status_code != 200:
            logging.getLogger(__name__).warning("%s response: HTTP %s", label, response.status_code)
            raise ValueError(f"{label} request failed (HTTP {response.status_code}). No paid fallback was used.")
        message = response.json()["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        if not calls:
            return message.get("content") or "No response was returned. Please try again."
        history.append({k: message[k] for k in ("role", "content", "tool_calls") if k in message})
        for call in calls:
            function = call["function"]
            try:
                if function["name"] not in allowed or invoke is None:
                    raise ValueError("Unknown tool")
                arguments = json.loads(function["arguments"])
                if not isinstance(arguments, dict):
                    raise ValueError("Tool arguments must be an object")
                logging.getLogger(__name__).info("Agent tool: %s", function["name"])
                result = await invoke(function["name"], arguments)
                if function["name"] == "prepare_storage_export" and isinstance(result, dict) and result.get("status") == "pending":
                    return f"I think we should store **{result['title']}**. Please review the exact content in the approval card below. It will be public on IPFS and costs {result['usdc']} test USDC on Base Sepolia. Approve the card or reply yes. Nothing has been uploaded or paid yet."
            except Exception as exc:
                logging.getLogger(__name__).warning("Agent tool failed: %s (%s)", function["name"], type(exc).__name__)
                result = {"error": "Tool execution failed. Do not claim success or repeat a payment."}
            history.append({"role": "tool", "tool_call_id": call["id"],
                            "content": json.dumps(result, default=str)})
    raise ValueError("Agent reached its tool-call limit. Completed actions were not replayed.")
