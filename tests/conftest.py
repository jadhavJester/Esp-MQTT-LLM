"""Test setup for Esp-MQTT-LLM.

ollama_agent.py imports the MCP SDK, anyio and the Ollama client at module
level. Where those third-party packages are not installed, lightweight
stand-ins are installed into sys.modules before the module under test is
imported. Where they ARE installed (e.g. from requirements.txt), the real
packages are used, so the suite exercises the real imports.
"""

import importlib.util
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _stub(name, **attrs):
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    sys.modules[name] = mod
    return mod


def _missing(name):
    return importlib.util.find_spec(name) is None


class _DummyClient:
    def __init__(self, *args, **kwargs):
        pass


class _McpError(Exception):
    pass


class _MqttTransportClient:
    async def initialize_mcp_server(self, *args, **kwargs):
        pass


class _MqttOptions:
    def __init__(self, *args, **kwargs):
        pass


if _missing("mcp") or _missing("ollama") or _missing("anyio"):
    if _missing("anyio"):
        _stub("anyio")
    if _missing("ollama"):
        _stub("ollama", Client=_DummyClient)
    if _missing("mcp"):
        mcp = _stub("mcp")
        client = _stub("mcp.client")
        mqtt = _stub("mcp.client.mqtt",
                     MqttTransportClient=_MqttTransportClient,
                     MqttOptions=_MqttOptions)
        shared = _stub("mcp.shared")
        shared_mqtt = _stub("mcp.shared.mqtt",
                            configure_logging=lambda *a, **k: None)
        types_mod = _stub("mcp.types")
        exceptions = _stub("mcp.shared.exceptions", McpError=_McpError)
        # `import a.b.c as x` walks attributes, so link the package tree.
        mcp.client = client
        mcp.shared = shared
        mcp.types = types_mod
        client.mqtt = mqtt
        shared.mqtt = shared_mqtt
        shared.exceptions = exceptions
