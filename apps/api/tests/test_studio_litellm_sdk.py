"""Offline SDK regression test for LiteLLM's normal function tools.

Install the optional SDK and run this in CI. It uses LiteLLM mock_response
with a dummy API key: no Gemini/network calls and no user data are involved.
"""
import asyncio

import pytest

litellm = pytest.importorskip("litellm")

TOOL = {
    "type": "function",
    "function": {
        "name": "record_test",
        "description": "Record a result",
        "parameters": {
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
        },
    },
}
PARAMS = {
    "model": "gemini/gemini-2.5-flash",
    "messages": [{"role": "user", "content": "Reply OK"}],
    "tools": [TOOL],
    "tool_choice": "auto",
    "mock_response": "OK",
    "api_key": "local-test-placeholder-not-a-real-key",
    "num_retries": 0,
    # The 1.108.3 plain-SDK handler tries to import optional MCP even for
    # ordinary function calls. This flag skips that unrelated proxy handler.
    "_skip_mcp_handler": True,
}


def test_sdk_function_tool_workaround_sync_no_network():
    result = litellm.completion(**PARAMS)
    assert result.choices


def test_sdk_function_tool_workaround_async_no_network():
    result = asyncio.run(litellm.acompletion(**PARAMS))
    assert result.choices
