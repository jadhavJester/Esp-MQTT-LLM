"""Tests for ollama_agent.handle_tool_call.

The chat loop's per-call dispatch (local delay tool, unknown-tool error,
device-tool call and its failure path) runs here without a live LLM,
broker, or hardware: the device caller and the sleep are stubbed.
"""
import asyncio
import json

import ollama_agent


def _run(fn_name, fn_args, tool_owner):
    return asyncio.run(ollama_agent.handle_tool_call(fn_name, fn_args, tool_owner))


def test_delay_sleeps_and_reports_seconds(monkeypatch):
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(ollama_agent.anyio, "sleep", fake_sleep, raising=False)
    out = _run("delay", {"seconds": 1.5}, {})
    assert json.loads(out) == {"status": "ok", "delayed_seconds": 1.5}
    assert slept == [1.5]


def test_delay_defaults_to_one_second(monkeypatch):
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(ollama_agent.anyio, "sleep", fake_sleep, raising=False)
    out = _run("delay", {}, {})
    assert json.loads(out) == {"status": "ok", "delayed_seconds": 1.0}
    assert slept == [1.0]


def test_unknown_tool_reports_no_owner():
    out = _run("led_on", {}, {})
    assert out == "Error: no connected device exposes tool 'led_on'"


def test_device_tool_call_is_forwarded(monkeypatch):
    seen = []

    async def fake_call(server_name, tool_name, arguments):
        seen.append((server_name, tool_name, arguments))
        return '{"status": "ok", "led": "on"}'

    monkeypatch.setattr(ollama_agent, "call_device_tool", fake_call)
    out = _run("led_on", {}, {"led_on": "esp32_devkit"})
    assert out == '{"status": "ok", "led": "on"}'
    assert seen == [("esp32_devkit", "led_on", {})]


def test_device_tool_error_becomes_json_error(monkeypatch):
    async def failing_call(server_name, tool_name, arguments):
        raise RuntimeError("broker down")

    monkeypatch.setattr(ollama_agent, "call_device_tool", failing_call)
    out = _run("read_boot_button", {}, {"read_boot_button": "esp32_devkit"})
    assert json.loads(out) == {"error": "broker down"}
