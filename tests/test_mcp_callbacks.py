"""Tests for ollama_agent.on_mcp_connect / on_mcp_disconnect.

These callbacks maintain the module-level registry of connected ESP32
servers and their tools. A fake transport client stands in for the real
MQTT client, so these tests run without hardware, a broker, or an LLM key.
"""
import asyncio
from types import SimpleNamespace

import pytest

import ollama_agent


class _FakeClient:
    def __init__(self, tools):
        self._tools = tools
        self.listed = []

    async def list_tools(self, server_name):
        self.listed.append(server_name)
        return SimpleNamespace(tools=self._tools)


def _mcp_tool(name):
    return SimpleNamespace(
        name=name, description=f"{name} tool",
        inputSchema={"type": "object", "properties": {}})


@pytest.fixture(autouse=True)
def _clean_registry():
    ollama_agent.connected_servers.clear()
    yield
    ollama_agent.connected_servers.clear()


def test_connect_registers_server_tools():
    client = _FakeClient([_mcp_tool("led_on"), _mcp_tool("led_off")])
    asyncio.run(ollama_agent.on_mcp_connect(
        client, "esp32_devkit", ("ok", {"server": "esp32_devkit"})))
    assert client.listed == ["esp32_devkit"]
    assert [t.name for t in ollama_agent.connected_servers["esp32_devkit"]] == [
        "led_on", "led_off"]


def test_connect_error_does_not_register_server():
    client = _FakeClient([_mcp_tool("led_on")])
    asyncio.run(ollama_agent.on_mcp_connect(
        client, "esp32_devkit", ("error", "subscribe_mcp_server_topics_failed")))
    assert "esp32_devkit" not in ollama_agent.connected_servers
    assert client.listed == []


def test_disconnect_removes_server():
    ollama_agent.connected_servers["esp32_devkit"] = [_mcp_tool("led_on")]
    asyncio.run(ollama_agent.on_mcp_disconnect(None, "esp32_devkit"))
    assert "esp32_devkit" not in ollama_agent.connected_servers


def test_disconnect_of_unknown_server_is_safe():
    asyncio.run(ollama_agent.on_mcp_disconnect(None, "never_connected"))
    assert ollama_agent.connected_servers == {}
