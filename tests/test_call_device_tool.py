"""Tests for ollama_agent.call_device_tool.

The tool caller talks to the ESP32 over MCP and returns the text of the
device's reply. A fake transport client stands in for the real MQTT
client, so these tests run without hardware, a broker, or an LLM key.
"""

import asyncio
from types import SimpleNamespace

import ollama_agent


class _FakeClient:
    def __init__(self, result):
        self.result = result
        self.seen = None

    async def call_tool(self, server_name, name, arguments):
        self.seen = (server_name, name, arguments)
        return self.result


def _block(kind, text=None):
    block = SimpleNamespace(type=kind)
    if text is not None:
        block.text = text
    return block


def _run(server_name, tool_name, arguments, result):
    client = _FakeClient(result)
    previous = ollama_agent.mcp_client_ref.get("client")
    ollama_agent.mcp_client_ref["client"] = client
    try:
        out = asyncio.run(
            ollama_agent.call_device_tool(server_name, tool_name, arguments))
    finally:
        if previous is None:
            ollama_agent.mcp_client_ref.pop("client", None)
        else:
            ollama_agent.mcp_client_ref["client"] = previous
    return client, out


def test_joins_text_blocks_and_forwards_call():
    result = SimpleNamespace(content=[
        _block("text", '{"status": "ok"'),
        _block("text", '"led": "on"}'),
    ])
    client, out = _run("esp32_devkit", "led_on", {},
                       result)
    assert client.seen == ("esp32_devkit", "led_on", {})
    assert out == '{"status": "ok"\n"led": "on"}'


def test_non_text_blocks_fall_back_to_full_result():
    result = SimpleNamespace(content=[_block("image")])
    _, out = _run("esp32_devkit", "read_boot_button", {}, result)
    assert out == str(result)


def test_empty_content_falls_back_to_full_result():
    result = SimpleNamespace(content=[])
    _, out = _run("esp32_devkit", "get_led_state", {}, result)
    assert out == str(result)
