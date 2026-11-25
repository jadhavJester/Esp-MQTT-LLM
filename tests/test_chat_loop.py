"""Tests for ollama_agent.chat_loop.

The interactive loop reads user input, asks the model, and runs any tool
calls until the model gives a final answer. A fake anyio namespace feeds
canned input lines and a stub Ollama client returns canned replies, so
these tests run without a live LLM, broker, or hardware.
"""
import asyncio
from types import SimpleNamespace

import pytest

import ollama_agent


class _StubChatClient:
    """Fake Ollama client returning one canned reply per chat() call."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, model, messages, tools):
        # Snapshot the message list: chat_loop keeps mutating it.
        self.calls.append({"model": model, "messages": list(messages),
                           "tools": tools})
        return {"message": self.replies.pop(0)}


def _reply(content=None, tool_calls=None):
    msg = {}
    if content is not None:
        msg["content"] = content
    if tool_calls is not None:
        msg["tool_calls"] = tool_calls
    return msg


def _tool_call(name, arguments=None):
    return {"function": {"name": name, "arguments": arguments or {}}}


@pytest.fixture()
def _fake_anyio(monkeypatch):
    """Stand in for the stubbed anyio module: canned input + instant sleep."""
    fake = SimpleNamespace(inputs=[])

    async def fake_run_sync(func, *args, **kwargs):
        if not fake.inputs:
            raise EOFError
        return fake.inputs.pop(0)

    async def fake_sleep(seconds):
        return None

    fake.sleep = fake_sleep
    fake.to_thread = SimpleNamespace(run_sync=fake_run_sync)
    monkeypatch.setattr(ollama_agent, "anyio", fake)
    return fake


@pytest.fixture(autouse=True)
def _clean_registry():
    ollama_agent.connected_servers.clear()
    yield
    ollama_agent.connected_servers.clear()


def _run_loop(inputs, replies, monkeypatch, capsys, fake_anyio):
    fake_anyio.inputs = list(inputs)
    stub = _StubChatClient(replies)
    monkeypatch.setattr(ollama_agent, "ollama_client", stub)
    asyncio.run(ollama_agent.chat_loop())
    return stub, capsys.readouterr().out


def test_chat_loop_quits_immediately(monkeypatch, capsys, _fake_anyio):
    stub, out = _run_loop(["quit"], [], monkeypatch, capsys, _fake_anyio)
    assert stub.calls == []
    assert "Connected." in out


def test_chat_loop_exits_on_eof(monkeypatch, capsys, _fake_anyio):
    stub, out = _run_loop([], [], monkeypatch, capsys, _fake_anyio)
    assert stub.calls == []
    assert "Goodbye!" in out


def test_chat_loop_prints_plain_reply(monkeypatch, capsys, _fake_anyio):
    stub, out = _run_loop(
        ["turn the LED on", "quit"],
        [_reply(content="LED is on.")],
        monkeypatch, capsys, _fake_anyio)
    assert len(stub.calls) == 1
    assert stub.calls[0]["messages"][-1] == {
        "role": "user", "content": "turn the LED on"}
    assert "agent> LED is on." in out


def test_chat_loop_runs_tool_calls_until_final_answer(
        monkeypatch, capsys, _fake_anyio):
    stub, out = _run_loop(
        ["blink once", "quit"],
        [_reply(tool_calls=[_tool_call("delay", {"seconds": 0.5})]),
         _reply(content="Blinked.")],
        monkeypatch, capsys, _fake_anyio)
    assert len(stub.calls) == 2
    # The delay result went back to the model as a tool message.
    tool_msgs = [m for m in stub.calls[1]["messages"]
                 if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["name"] == "delay"
    assert "delayed_seconds" in tool_msgs[0]["content"]
    assert "agent> Blinked." in out
