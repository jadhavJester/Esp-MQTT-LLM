"""
PC-side agent: discovers the ESP32's MCP-over-MQTT server, exposes its tools
to Ollama Cloud, and runs a simple chat loop where the model can call those
tools to control the device.

Install:
    pip install ollama --break-system-packages
    pip install "mcp[cli]" --break-system-packages
    pip install "git+https://github.com/emqx/mcp-python-sdk@main" --break-system-packages

Env vars:
    OLLAMA_API_KEY   - from https://ollama.com/settings/keys
    MQTT_BROKER_HOST - same broker host the ESP32 firmware is configured with

Run:
    python ollama_agent.py
"""

import os
import json
import logging
import anyio
import uuid
import mcp.client.mqtt as mcp_mqtt
from mcp.shared.mqtt import configure_logging
from ollama import Client

# Monkey patch MqttTransportClient.initialize_mcp_server to avoid AnyIO cancel scope lifetime violations.
# The original SDK enters the session context manager inside a short-lived background task, but never exits it
# within that task, leaving the cancel scope dangling on the finished task's stack.
# We fix this by keeping the background task running inside an `async with` block for the session's entire lifetime.
import mcp.types as types
from mcp.shared.exceptions import McpError
from typing import Literal

async def patched_initialize_mcp_server(
    self,
    server_name: str,
    read_timeout_seconds: float | None = None,
    sampling_callback = None,
    list_roots_callback = None,
    logging_callback = None,
    message_handler = None
):
    if server_name in self.client_sessions:
        return "ok"
    server_id = self.pick_server_id(server_name)

    async def after_subscribed(subscribe_result: Literal["success", "error"]):
        if subscribe_result == "error":
            if self.on_mcp_connect:
                self._task_group.start_soon(self.on_mcp_connect, self, server_name, ("error", "subscribe_mcp_server_topics_failed"))
            return
        client_session = self._create_session(
            server_id,
            server_name,
            read_timeout_seconds,
            sampling_callback,
            list_roots_callback,
            logging_callback,
            message_handler
        )
        self.client_sessions[server_name] = client_session
        try:
            logger.debug(f"before initialize: {server_name}")
            async def after_initialize():
                try:
                    async with client_session as session:
                        init_result = await session.initialize()
                        session.server_info = init_result
                        if self.on_mcp_connect:
                            self._task_group.start_soon(self.on_mcp_connect, self, server_name, ("ok", init_result))
                        
                        # Keep the context open and the task alive as long as the session exists
                        while server_name in self.client_sessions and self.client_sessions[server_name] is client_session:
                            await anyio.sleep(0.5)
                except Exception as e:
                    self.client_sessions.pop(server_name, None)
                    logger.error(f"Failed to initialize/run server {server_name}: {e}")
            self._task_group.start_soon(after_initialize)
            logger.debug(f"after initialize: {server_name}")
        except McpError as exc:
            self.client_sessions.pop(server_name, None)
            logger.error(f"Failed to connect to MCP server: {exc}")
            if self.on_mcp_connect:
                self._task_group.start_soon(self.on_mcp_connect, self, server_name, ("error", McpError))

    self._task_group.start_soon(
        lambda: self.subscribe_mcp_server_topics(server_name, after_subscribed)
    )

mcp_mqtt.MqttTransportClient.initialize_mcp_server = patched_initialize_mcp_server


configure_logging(level="INFO")
logger = logging.getLogger(__name__)

OLLAMA_MODEL = "gemma4:31b-cloud"  # any Ollama Cloud model, see `curl https://ollama.com/api/tags`
MQTT_BROKER_HOST = os.environ.get("MQTT_BROKER_HOST", "broker.emqx.io")

ollama_headers = {}
api_key = os.environ.get("OLLAMA_API_KEY")
if api_key:
    ollama_headers["Authorization"] = f"Bearer {api_key}"

ollama_client = Client(
    host="https://ollama.com",
    headers=ollama_headers,
)

# Populated as MCP servers (ESP32 devices) are discovered
connected_servers = {}   # server_name -> list of mcp.types.Tool
mcp_client_ref = {}      # holds the running MqttTransportClient


def mcp_tools_to_ollama_tools(tools):
    """Convert MCP tool definitions to the Ollama function-calling schema."""
    ollama_tools = []
    for t in tools:
        ollama_tools.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description or "",
                "parameters": t.inputSchema or {"type": "object", "properties": {}},
            },
        })
    return ollama_tools


async def on_mcp_server_discovered(client, server_name):
    logger.info(f"Discovered MCP server: {server_name}, connecting...")
    await client.initialize_mcp_server(server_name)


async def on_mcp_connect(client, server_name, connect_result):
    success, init_result = connect_result
    if success == "error":
        logger.error(f"Failed to connect to {server_name}: {init_result}")
        return
    tools_result = await client.list_tools(server_name)
    connected_servers[server_name] = tools_result.tools
    logger.info(f"Connected to {server_name}. Tools: {[t.name for t in tools_result.tools]}")


async def on_mcp_disconnect(client, server_name):
    connected_servers.pop(server_name, None)
    logger.info(f"Disconnected from {server_name}")


async def call_device_tool(server_name, tool_name, arguments):
    client = mcp_client_ref["client"]
    result = await client.call_tool(server_name, name=tool_name, arguments=arguments)
    # MCP tool results are a list of content blocks; join any text blocks
    text_parts = [c.text for c in result.content if getattr(c, "type", None) == "text"]
    return "\n".join(text_parts) if text_parts else str(result)

SYSTEM_PROMPT = """You are a helpful hardware assistant controlling an ESP32 microcontroller devkit via MCP (Model Context Protocol).
You have tools to control the onboard LED (led_on, led_off, get_led_state), read the physical BOOT button (read_boot_button), and pause/delay execution (delay).

Guidelines:
1. When asked to blink the LED, turn it on, delay, turn it off, delay, etc. Do not just turn it on and off without a delay, as it will happen too fast for the user to see. Always insert a `delay` tool call between state changes.
2. If the user asks for a specific number of blinks or a specific delay, use the `delay` tool with the corresponding `seconds` parameter.
3. If the user asks to wait for the button to be pressed, check the button state. You can poll it if necessary, or explain the status.
4. Do not output code blocks showing how to write programs. Execute the tools directly to perform the physical tasks on the device.
5. Keep your responses short and friendly, reporting the outcome of the actions you performed.
"""


async def chat_loop():
    print("Connected. Type a message (or 'quit'). Example: 'turn the LED on'", flush=True)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    while True:
        try:
            print("you> ", end="", flush=True)
            user_input = await anyio.to_thread.run_sync(input)
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!", flush=True)
            break
        if user_input.strip().lower() in ("quit", "exit"):
            break
        messages.append({"role": "user", "content": user_input})

        # Gather all tools from all currently connected ESP32 MCP servers
        all_tools = []
        tool_owner = {}  # tool name -> server_name
        for server_name, tools in connected_servers.items():
            for t in tools:
                tool_owner[t.name] = server_name
            all_tools.extend(mcp_tools_to_ollama_tools(tools))

        # Add the local delay tool for pacing actions/blinking
        all_tools.append({
            "type": "function",
            "function": {
                "name": "delay",
                "description": "Introduce a delay (pause) between sequential actions. Use this to wait between turning a state on and off, e.g. for blinking an LED with specific intervals.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "seconds": {
                            "type": "number",
                            "description": "Number of seconds to delay/pause before the next action"
                        }
                    },
                    "required": ["seconds"]
                }
            }
        })

        response = ollama_client.chat(
            model=OLLAMA_MODEL,
            messages=messages,
            tools=all_tools if all_tools else None,
        )
        msg = response["message"]
        messages.append(msg)

        # Tool-calling loop: keep calling tools until the model gives a final answer
        while msg.get("tool_calls"):
            for call in msg["tool_calls"]:
                fn_name = call["function"]["name"]
                fn_args = call["function"].get("arguments", {})
                
                if fn_name == "delay":
                    seconds = float(fn_args.get("seconds", 1.0))
                    logger.info(f"Local delay tool: pausing for {seconds} seconds...")
                    await anyio.sleep(seconds)
                    tool_result = json.dumps({"status": "ok", "delayed_seconds": seconds})
                else:
                    server_name = tool_owner.get(fn_name)
                    if not server_name:
                        tool_result = f"Error: no connected device exposes tool '{fn_name}'"
                    else:
                        try:
                            tool_result = await call_device_tool(server_name, fn_name, fn_args)
                            logger.info(f"Called {fn_name}({fn_args}) on {server_name} -> {tool_result}")
                        except Exception as e:
                            logger.error(f"Error calling {fn_name}({fn_args}) on {server_name}: {e}")
                            tool_result = json.dumps({"error": str(e)})
                messages.append({"role": "tool", "content": tool_result, "name": fn_name})

            response = ollama_client.chat(model=OLLAMA_MODEL, messages=messages, tools=all_tools)
            msg = response["message"]
            messages.append(msg)

        print(f"agent> {msg.get('content', '')}", flush=True)


async def main():
    client_id = f"ollama_agent_{uuid.uuid4().hex[:8]}"
    async with mcp_mqtt.MqttTransportClient(
        client_id,
        auto_connect_to_mcp_server=False,
        on_mcp_server_discovered=on_mcp_server_discovered,
        on_mcp_connect=on_mcp_connect,
        on_mcp_disconnect=on_mcp_disconnect,
        mqtt_options=mcp_mqtt.MqttOptions(host=MQTT_BROKER_HOST),
    ) as client:
        mcp_client_ref["client"] = client
        await client.start()
        
        logger.info("Waiting for ESP32 MCP server to connect...")
        with anyio.move_on_after(10):
            while not connected_servers:
                await anyio.sleep(0.1)
                
        if not connected_servers:
            logger.warning("No ESP32 MCP server connected within 10 seconds. Starting chat anyway.")
        else:
            logger.info("ESP32 MCP server connected and tools loaded successfully.")
            
        await chat_loop()


if __name__ == "__main__":
    anyio.run(main)
