"""Tests for ollama_agent.build_chat_tools.

The chat loop offers the model every tool from every connected ESP32 plus
a local delay helper for pacing. This pins the merge: tools convert to the
Ollama schema, each device tool maps back to its owning server, and the
delay tool is always appended even when no server is connected.
"""
from types import SimpleNamespace

from ollama_agent import build_chat_tools


def _mcp_tool(name):
    return SimpleNamespace(name=name, description=f"{name} tool",
                           inputSchema={"type": "object", "properties": {}})


def test_merges_servers_and_tracks_owners():
    servers = {
        "esp32_a": [_mcp_tool("led_on"), _mcp_tool("led_off")],
        "esp32_b": [_mcp_tool("read_boot_button")],
    }
    tools, owners = build_chat_tools(servers)
    names = [t["function"]["name"] for t in tools]
    assert names == ["led_on", "led_off", "read_boot_button", "delay"]
    assert owners == {
        "led_on": "esp32_a",
        "led_off": "esp32_a",
        "read_boot_button": "esp32_b",
    }
    assert all(t["type"] == "function" for t in tools)


def test_delay_tool_always_present_with_no_servers():
    tools, owners = build_chat_tools({})
    assert [t["function"]["name"] for t in tools] == ["delay"]
    assert owners == {}
    delay = tools[0]["function"]
    assert "delay" in delay["description"].lower()
    assert delay["parameters"]["properties"]["seconds"]["type"] == "number"
    assert "seconds" in delay["parameters"]["required"]
