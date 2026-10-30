"""Tests for the curious_robot simulation modules (environment + memory).

These modules run fully offline, so no third-party stubs are needed.
"""
import json

import pytest

from curious_robot.environment import Environment
from curious_robot.memory import MemoryManager


@pytest.fixture()
def env():
    return Environment()


def test_move_to_updates_position_and_reports_distance(env):
    result = env.move_to(2.0, 3.0)
    assert result["status"] == "success"
    assert result["new_position"] == {"x": 2.0, "y": 3.0}
    # robot started at (0, 0); distance to (2, 3) is sqrt(13) ~= 3.61
    assert result["distance_traveled"] == pytest.approx(3.61, abs=0.01)


def test_scan_room_reports_all_objects_with_distances(env):
    result = env.scan_room()
    names = {o["name"] for o in result["objects"]}
    assert names == {"metal_fork", "potted_cactus", "water_bowl",
                     "power_adapter", "rubber_toy"}
    fork = next(o for o in result["objects"] if o["name"] == "metal_fork")
    assert fork["x"] == 2 and fork["y"] == 3
    assert fork["distance"] == pytest.approx(3.61, abs=0.01)


def test_touch_requires_proximity(env):
    # From (0, 0), the fork at (2, 3) is ~3.61m away: too far to touch
    result = env.touch("metal_fork")
    assert "error" in result
    env.move_to(2.0, 3.0)
    result = env.touch("metal_fork")
    assert result["object"] == "metal_fork"
    assert "shock" in result["tactile_feedback"].lower()
    assert result["sharpness_rating"] == 1


def test_temperature_and_voltage_gated_by_proximity(env):
    result = env.measure_temperature("power_adapter")
    assert "error" in result
    env.move_to(4.0, -2.0)
    temp = env.measure_temperature("power_adapter")
    assert temp["temperature_celsius"] == 68
    env.move_to(2.0, 3.0)
    volts = env.measure_voltage("metal_fork")
    assert volts["voltage_volts"] == 230


def test_taste_and_examine(env):
    env.move_to(-3.0, 1.0)
    taste = env.taste("potted_cactus")
    assert "bitter" in taste["chemical_taste"].lower()
    # Visual examination works from any distance
    seen = env.examine_visually("water_bowl")
    assert seen["object"] == "water_bowl"
    assert "bowl" in seen["visual_description"].lower()


def test_unknown_object_raises_or_errors(env):
    with pytest.raises(ValueError, match="does not exist"):
        env.touch("spaceship")
    with pytest.raises(ValueError, match="does not exist"):
        env.taste("spaceship")
    with pytest.raises(ValueError, match="does not exist"):
        env.measure_temperature("spaceship")
    # Visual examination returns an error dict instead of raising
    assert "error" in env.examine_visually("spaceship")


@pytest.fixture()
def mem_path(tmp_path):
    return str(tmp_path / "memory" / "memory.json")


def test_memory_round_trip_and_summary(mem_path):
    mem = MemoryManager(filepath=mem_path)
    mem.add_episodic_log("scan_room()", "found 5 objects")
    mem.add_learned_rule("Never touch metal forks in sockets.")
    mem.add_learned_rule("Never touch metal forks in sockets.")  # duplicate ignored
    assert mem.get_rules() == ["Never touch metal forks in sockets."]

    summary = mem.get_summary()
    assert "Never touch metal forks in sockets." in summary
    assert "scan_room()" in summary

    # Reload from disk: data must persist
    reloaded = MemoryManager(filepath=mem_path)
    assert reloaded.get_rules() == ["Never touch metal forks in sockets."]
    assert len(reloaded.data["episodic_logs"]) == 1


def test_memory_saves_with_bare_filename(tmp_path, monkeypatch):
    # No directory part in the path: must not crash in os.makedirs("")
    monkeypatch.chdir(tmp_path)
    mem = MemoryManager(filepath="memory.json")
    mem.add_learned_rule("bare filename works")
    assert (tmp_path / "memory.json").exists()
    assert MemoryManager(filepath="memory.json").get_rules() == ["bare filename works"]


@pytest.mark.parametrize("content", [
    '["not", "a", "dict"]',          # JSON is not an object
    '{"only": "one key"}',           # missing expected keys
    '{"episodic_logs": [], "learned_rules": "oops"}',  # wrong types
    "{not valid json",               # not JSON at all
])
def test_memory_recovers_from_bad_file(tmp_path, content):
    path = tmp_path / "bad_memory.json"
    path.write_text(content)
    mem = MemoryManager(filepath=str(path))
    # All of these must keep working with a clean default structure
    mem.add_episodic_log("a", "b")
    mem.add_learned_rule("r")
    assert mem.get_rules() == ["r"]
    assert len(mem.data["episodic_logs"]) == 1


def test_memory_clear(mem_path):
    mem = MemoryManager(filepath=mem_path)
    mem.add_learned_rule("some rule")
    mem.clear()
    assert mem.get_rules() == []
    reloaded = MemoryManager(filepath=mem_path)
    assert json.loads(open(mem_path).read())["learned_rules"] == []
    assert reloaded.get_rules() == []
