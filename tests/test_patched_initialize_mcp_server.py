"""Tests for ollama_agent.patched_initialize_mcp_server.

The monkey-patch keeps the MCP session alive inside its background task
instead of letting the SDK's cancel scope die with the task. A fake
transport client stands in for the real MQTT client, so these tests run
without hardware, a broker, or an LLM key.
"""
import asyncio
from types import SimpleNamespace

import ollama_agent


class _FakeTaskGroup:
    """Collects start_soon() calls; the test drains them in FIFO order."""

    def __init__(self):
        self.scheduled = []

    def start_soon(self, func, *args):
        # anyio accepts a callable returning a coroutine (e.g. a lambda)
        self.scheduled.append(func(*args))

    async def drain(self):
        while self.scheduled:
            await self.scheduled.pop(0)


class _FakeSession:
    def __init__(self, init_result=None, init_error=None):
        self.init_result = init_result if init_result is not None else {"server": "fake"}
        self.init_error = init_error
        self.server_info = None
        self.initialized = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def initialize(self):
        if self.init_error is not None:
            raise self.init_error
        self.initialized = True
        return self.init_result


class _FakeTransportClient:
    def __init__(self, subscribe_result="success", session=None,
                 create_session_error=None):
        self.client_sessions = {}
        self._task_group = _FakeTaskGroup()
        self.subscribe_result = subscribe_result
        self.session = session if session is not None else _FakeSession()
        self.create_session_error = create_session_error
        self.subscribe_calls = []
        self.connect_calls = []
        self.on_mcp_connect = self._record_connect

    def pick_server_id(self, server_name):
        return f"id-{server_name}"

    def _create_session(self, server_id, server_name, *args, **kwargs):
        if self.create_session_error is not None:
            raise self.create_session_error
        return self.session

    async def subscribe_mcp_server_topics(self, server_name, after_subscribed):
        self.subscribe_calls.append(server_name)
        await after_subscribed(self.subscribe_result)

    async def _record_connect(self, client, server_name, result):
        self.connect_calls.append((server_name, result))


def _initialize(client, server_name="esp32_devkit"):
    asyncio.run(ollama_agent.patched_initialize_mcp_server(client, server_name))
    asyncio.run(client._task_group.drain())


def test_already_connected_returns_ok_without_subscribing():
    client = _FakeTransportClient()
    client.client_sessions["esp32_devkit"] = SimpleNamespace()
    out = asyncio.run(
        ollama_agent.patched_initialize_mcp_server(client, "esp32_devkit"))
    assert out == "ok"
    assert client.subscribe_calls == []
    assert client._task_group.scheduled == []


def test_subscribe_error_reports_connect_failure():
    client = _FakeTransportClient(subscribe_result="error")
    _initialize(client)
    assert client.subscribe_calls == ["esp32_devkit"]
    assert "esp32_devkit" not in client.client_sessions
    assert client.connect_calls == [
        ("esp32_devkit", ("error", "subscribe_mcp_server_topics_failed"))]


def test_successful_subscribe_initializes_session_and_reports_connect(monkeypatch):
    client = _FakeTransportClient()

    async def fake_sleep(seconds):
        # Simulate the session ending so the keep-alive loop exits
        client.client_sessions.pop("esp32_devkit", None)

    monkeypatch.setattr(ollama_agent.anyio, "sleep", fake_sleep, raising=False)
    _initialize(client)
    assert client.subscribe_calls == ["esp32_devkit"]
    assert client.session.initialized
    assert client.session.server_info == {"server": "fake"}
    assert client.connect_calls == [
        ("esp32_devkit", ("ok", {"server": "fake"}))]
    # The keep-alive loop exited once the session was gone
    assert "esp32_devkit" not in client.client_sessions


def test_failed_initialize_cleans_up_session():
    client = _FakeTransportClient(session=_FakeSession(init_error=RuntimeError("boom")))
    _initialize(client)
    assert "esp32_devkit" not in client.client_sessions
    assert client.connect_calls == []


def test_create_session_mcp_error_reports_connect_failure():
    # _create_session raising McpError must hit the except branch: drop
    # the (never registered) session and report the failure, not crash
    # the background task.
    client = _FakeTransportClient(
        create_session_error=ollama_agent.McpError("boom"))
    _initialize(client)
    assert "esp32_devkit" not in client.client_sessions
    assert client.connect_calls == [
        ("esp32_devkit", ("error", ollama_agent.McpError))]
