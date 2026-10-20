"""Tests for ollama_agent.mcp_tools_to_ollama_tools.

The ESP32 exposes MCP tools; the PC agent must translate them into the
Ollama function-calling schema before the LLM can call them. These tests
pin that translation, including its defaults for missing fields.
"""

from types import SimpleNamespace

from ollama_agent import mcp_tools_to_ollama_tools


def tool(name, description=None, schema=None):
    return SimpleNamespace(name=name, description=description,
                           inputSchema=schema)


def test_converts_tool_with_full_schema():
    schema = {"type": "object",
              "properties": {"state": {"type": "string"}}}
    out = mcp_tools_to_ollama_tools([tool("led_on", "Turn LED on", schema)])
    assert out == [{
        "type": "function",
        "function": {
            "name": "led_on",
            "description": "Turn LED on",
            "parameters": schema,
        },
    }]


def test_missing_description_and_schema_get_defaults():
    out = mcp_tools_to_ollama_tools([tool("read_boot_button")])
    fn = out[0]["function"]
    assert fn["description"] == ""
    assert fn["parameters"] == {"type": "object", "properties": {}}


def test_empty_and_multiple_tools():
    assert mcp_tools_to_ollama_tools([]) == []
    out = mcp_tools_to_ollama_tools(
        [tool("led_on"), tool("led_off"), tool("delay")])
    assert [t["function"]["name"] for t in out] == \
        ["led_on", "led_off", "delay"]
    assert all(t["type"] == "function" for t in out)
