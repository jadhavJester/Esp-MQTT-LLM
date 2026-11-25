"""Tests for ollama_agent.main.

main() opens the MQTT transport client, waits up to 10 seconds for an
ESP32 MCP server to connect, then hands over to chat_loop(). A fake
transport client and a fake anyio namespace (instant sleep, a cancel
scope that models the 10-second deadline) stand in for the broker and
the real runtime, so these tests run without hardware or an LLM key.
"""
import asyncio
import logging
from types import SimpleNamespace

import pytest

import ollama_agent


class _FakeCancelled(Exception):
    """Stands in for anyio's cancel exception at the move_on_after deadline."""


class _FakeCancelScope:
    """Context manager modelling anyio.move_on_after: swallows the
    deadline exception, lets everything else through."""

    def __init__(self, cancel_exc):
        self.cancel_exc = cancel_exc

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return exc_type is self.cancel_exc


class _FakeAnyio:
    def __init__(self, sleep_behaviour):
        self._sleep_behaviour = sleep_behaviour

    async def sleep(self, seconds):
        await self._sleep_behaviour(seconds)

    def move_on_after(self, seconds):
        return _FakeCancelScope(_FakeCancelled)


class _FakeMqttClient:
    instances = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.started = False
        _FakeMqttClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def start(self):
        self.started = True


async def _noop_sleep(seconds):
    return None


async def _deadline_sleep(seconds):
    raise _FakeCancelled()


@pytest.fixture(autouse=True)
def _clean_state():
    ollama_agent.connected_servers.clear()
    ollama_agent.mcp_client_ref.clear()
    _FakeMqttClient.instances.clear()
    yield
    ollama_agent.connected_servers.clear()
    ollama_agent.mcp_client_ref.clear()
    _FakeMqttClient.instances.clear()


@pytest.fixture()
def _chat_loop_spy(monkeypatch):
    calls = []

    async def fake_chat_loop():
        calls.append(True)

    monkeypatch.setattr(ollama_agent, "chat_loop", fake_chat_loop)
    return calls


def _run_main(monkeypatch, sleep_behaviour):
    monkeypatch.setattr(ollama_agent, "anyio", _FakeAnyio(sleep_behaviour))
    monkeypatch.setattr(ollama_agent.mcp_mqtt, "MqttTransportClient",
                        _FakeMqttClient, raising=False)
    asyncio.run(ollama_agent.main())
    return _FakeMqttClient.instances[0]


def test_main_with_connected_server_runs_chat_loop(
        monkeypatch, caplog, _chat_loop_spy):
    ollama_agent.connected_servers["esp32_devkit"] = []
    with caplog.at_level(logging.INFO, logger="ollama_agent"):
        client = _run_main(monkeypatch, _noop_sleep)
    assert client.started
    assert client.args[0].startswith("ollama_agent_")
    assert client.kwargs["auto_connect_to_mcp_server"] is False
    assert client.kwargs["on_mcp_connect"] is ollama_agent.on_mcp_connect
    assert ollama_agent.mcp_client_ref["client"] is client
    assert len(_chat_loop_spy) == 1
    assert "connected and tools loaded successfully" in caplog.text


def test_main_without_server_warns_and_still_runs_chat_loop(
        monkeypatch, caplog, _chat_loop_spy):
    with caplog.at_level(logging.WARNING, logger="ollama_agent"):
        client = _run_main(monkeypatch, _deadline_sleep)
    assert client.started
    assert "No ESP32 MCP server connected within 10 seconds" in caplog.text
    assert len(_chat_loop_spy) == 1
