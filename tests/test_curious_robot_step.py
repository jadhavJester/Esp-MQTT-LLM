"""Tests for CuriousExplorerAgent.step().

step() drives the LLM chat loop: it sends the memory summary and robot
position as context, then dispatches whatever tools the model calls and
logs the outcome to episodic memory. A stub Ollama client returns canned
model replies, so these tests run without a live LLM key.
"""
import asyncio
import os

import pytest

import curious_robot.agent as agent_module
from curious_robot.agent import CuriousExplorerAgent
from curious_robot.environment import Environment
from curious_robot.memory import MemoryManager

os.environ.setdefault("OLLAMA_API_KEY", "test-key")


class _StubClient:
    """Fake Ollama client returning one canned reply per chat() call."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, model, messages, tools):
        self.calls.append({"model": model, "messages": messages, "tools": tools})
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
def agent(tmp_path, monkeypatch):
    stub = _StubClient([_reply(content="I will scan the room.",
                               tool_calls=[_tool_call("scan_room")])])
    monkeypatch.setattr(agent_module, "Client", lambda *a, **k: stub)
    instance = CuriousExplorerAgent(
        Environment(),
        MemoryManager(filepath=str(tmp_path / "memory.json")),
    )
    instance._stub = stub
    return instance


def test_step_dispatches_tool_call_and_logs_it(agent):
    asyncio.run(agent.step())
    # The scan ran: the tool reply is in the message history ...
    tool_msgs = [m for m in agent.messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["name"] == "scan_room"
    assert "metal_fork" in tool_msgs[0]["content"]
    # ... and the action was recorded in episodic memory.
    assert len(agent.memory.data["episodic_logs"]) == 1
    assert "scan_room" in agent.memory.data["episodic_logs"][0]["action"]
    # The model saw the memory summary + robot position in its context.
    assert agent._stub.calls[0]["model"] == "gemma4:31b-cloud"


def test_step_with_no_tool_call_just_talks(tmp_path, monkeypatch):
    stub = _StubClient([_reply(content="Hello, I am exploring.")])
    monkeypatch.setattr(agent_module, "Client", lambda *a, **k: stub)
    agent = CuriousExplorerAgent(
        Environment(),
        MemoryManager(filepath=str(tmp_path / "memory.json")),
    )
    asyncio.run(agent.step())
    assert agent.messages[-1]["content"] == "Hello, I am exploring."
    assert not [m for m in agent.messages if m.get("role") == "tool"]
    assert agent.memory.data["episodic_logs"] == []


def test_second_step_sends_memory_summary_as_context(tmp_path, monkeypatch):
    # The first step seeds the chat with "Start exploring the room."; later
    # steps must instead append the live memory summary + robot position
    # as a user message, so the model reasons from current state.
    stub = _StubClient([
        _reply(content="First.", tool_calls=[_tool_call("scan_room")]),
        _reply(content="Second."),
    ])
    monkeypatch.setattr(agent_module, "Client", lambda *a, **k: stub)
    agent = CuriousExplorerAgent(
        Environment(),
        MemoryManager(filepath=str(tmp_path / "memory.json")),
    )
    asyncio.run(agent.step())
    asyncio.run(agent.step())
    assert len(stub.calls) == 2
    # The stub records the live message list by reference, so read the
    # agent's own history: the second user message must be the context
    # prompt, not another "Start exploring" seed.
    user_msgs = [m for m in agent.messages if m.get("role") == "user"]
    assert len(user_msgs) == 2
    assert "ROBOT MEMORY STATE" in user_msgs[1]["content"]
    assert "Robot Current Location" in user_msgs[1]["content"]
    assert "scan_room" in user_msgs[1]["content"]  # episodic log from step 1


def test_step_turns_bad_tool_call_into_error_message(tmp_path, monkeypatch):
    # move_to without coordinates: _dispatch_tool raises KeyError, step()
    # must convert it into an error dict the model can read, not crash.
    stub = _StubClient([_reply(tool_calls=[_tool_call("move_to", {})])])
    monkeypatch.setattr(agent_module, "Client", lambda *a, **k: stub)
    agent = CuriousExplorerAgent(
        Environment(),
        MemoryManager(filepath=str(tmp_path / "memory.json")),
    )
    asyncio.run(agent.step())
    tool_msgs = [m for m in agent.messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert "error" in tool_msgs[0]["content"]
    assert agent.memory.data["episodic_logs"][0]["action"].startswith("move_to")
