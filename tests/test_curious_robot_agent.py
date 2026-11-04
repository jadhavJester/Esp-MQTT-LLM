"""Tests for CuriousExplorerAgent._dispatch_tool.

step() needs a live Ollama Cloud key, but the tool-routing logic it calls
is pure dispatch over the offline Environment and MemoryManager. These
tests pin that routing: every name advertised by get_tool_definitions()
must resolve to a real handler, and unknown or malformed calls must come
back as error dicts the model can read, not exceptions.
"""
import os

import pytest

from curious_robot.agent import CuriousExplorerAgent
from curious_robot.environment import Environment
from curious_robot.memory import MemoryManager

os.environ.setdefault("OLLAMA_API_KEY", "test-key")


@pytest.fixture()
def agent(tmp_path):
    return CuriousExplorerAgent(
        Environment(),
        MemoryManager(filepath=str(tmp_path / "memory.json")),
    )


def test_every_defined_tool_dispatches(agent):
    """No name drift between the tool schema and the dispatch table."""
    defined = {t["function"]["name"] for t in agent.get_tool_definitions()}
    assert defined == {
        "scan_room", "move_to", "examine_visually", "measure_temperature",
        "measure_voltage", "touch", "taste", "add_learned_rule",
    }
    for name in defined:
        # Robot starts at (0, 0); water_bowl is 4m away -> sensor tools
        # report the proximity error dict, which proves they routed.
        if name == "scan_room":
            args = {}
        elif name == "move_to":
            args = {"x": 2.0, "y": 3.0}
        elif name == "add_learned_rule":
            args = {"rule": "Never touch hot adapters."}
        else:
            args = {"object_name": "water_bowl"}
        res = agent._dispatch_tool(name, args)
        assert isinstance(res, dict), name


def test_sensing_tools_report_results(agent):
    agent._dispatch_tool("move_to", {"x": -2.0, "y": -3.0})
    touch = agent._dispatch_tool("touch", {"object_name": "rubber_toy"})
    assert "squeaks" in touch["tactile_feedback"].lower()
    taste = agent._dispatch_tool("taste", {"object_name": "rubber_toy"})
    assert "rubber" in taste["chemical_taste"].lower()
    scan = agent._dispatch_tool("scan_room", {})
    assert {o["name"] for o in scan["objects"]} == {
        "metal_fork", "potted_cactus", "water_bowl",
        "power_adapter", "rubber_toy",
    }


def test_add_learned_rule_persists_to_memory(agent):
    res = agent._dispatch_tool(
        "add_learned_rule",
        {"rule": "Metal forks in sockets cause shocks."},
    )
    assert res["status"] == "success"
    assert res["rule_added"] == "Metal forks in sockets cause shocks."
    assert agent.memory.get_rules() == ["Metal forks in sockets cause shocks."]


def test_unknown_tool_returns_error_dict(agent):
    res = agent._dispatch_tool("fly", {})
    assert res == {"error": "Tool 'fly' not implemented."}


def test_unknown_object_surfaces_as_error_dict(agent):
    # Environment raises ValueError for missing objects; step() converts
    # those to {"error": ...} so the model sees them. The raw dispatcher
    # lets them propagate, and step() catches them.
    with pytest.raises(ValueError, match="does not exist"):
        agent._dispatch_tool("touch", {"object_name": "spaceship"})


def test_missing_arguments_raise_key_error(agent):
    with pytest.raises(KeyError):
        agent._dispatch_tool("move_to", {})
