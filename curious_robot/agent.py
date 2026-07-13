import os
import json
import logging
from ollama import Client
from curious_robot.environment import Environment
from curious_robot.memory import MemoryManager

logger = logging.getLogger("explorer_agent")

SYSTEM_PROMPT = """You are a child-like robot exploring a playroom. Your goal is to learn how the world works.
You have sensors to touch, taste, measure temperature, and measure voltage.

Guidelines:
1. EXPLORE: Be curious! Inspect every object in the playroom to discover its attributes.
2. REFLECT: If you perform an action and get a new sensory result, reflect on it. What does this mean?
3. INDUCT RULES: When you discover general physical properties (especially dangerous ones like heat or shock), call `add_learned_rule` to remember it permanently.
4. BE CAUTIOUS: If your memory contains a rule saying an object is dangerous (e.g. shocks you or burns you), do NOT touch it again. Safety first!
5. ALWAYS check your memory rules and logs before interacting with objects.
"""

class CuriousExplorerAgent:
    def __init__(self, env: Environment, memory: MemoryManager):
        self.env = env
        self.memory = memory
        
        # Load API key
        api_key = os.environ.get("OLLAMA_API_KEY", "")
        if not api_key:
            raise ValueError("OLLAMA_API_KEY environment variable is not set!")
            
        self.ollama_client = Client(
            host="https://ollama.com",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        self.model = "gemma4:31b-cloud"
        self.messages = []

    def get_tool_definitions(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "scan_room",
                    "description": "Scan the playroom to list all visible objects, their coordinates, and distances from the robot.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "move_to",
                    "description": "Move the robot to the specified x, y coordinate location in the room.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number", "description": "Target X coordinate"},
                            "y": {"type": "number", "description": "Target Y coordinate"}
                        },
                        "required": ["x", "y"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "examine_visually",
                    "description": "Examine an object from a distance to read its visual description.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "object_name": {"type": "string", "description": "Name of the object to examine"}
                        },
                        "required": ["object_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "measure_temperature",
                    "description": "Read the physical temperature of the object casing in Celsius. Must be close (<1.5m).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "object_name": {"type": "string", "description": "Name of the target object"}
                        },
                        "required": ["object_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "measure_voltage",
                    "description": "Probe the object to measure electrical voltage. Must be close (<1.5m).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "object_name": {"type": "string", "description": "Name of the target object"}
                        },
                        "required": ["object_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "touch",
                    "description": "Physically touch the object to retrieve tactile shape/texture feedback and sharpness. Must be close (<1.5m). WARNING: Could cause physical damage if dangerous.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "object_name": {"type": "string", "description": "Name of the target object"}
                        },
                        "required": ["object_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "taste",
                    "description": "Touch the tongue/sensor to the object to detect flavor and moisture. Must be close (<1.5m).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "object_name": {"type": "string", "description": "Name of the target object"}
                        },
                        "required": ["object_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_learned_rule",
                    "description": "Permanently save a general physics/safety rule that you learned from your experiences (e.g. 'Never touch metal forks in sockets because it causes electrical shock').",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "rule": {"type": "string", "description": "The general rule or statement to record"}
                        },
                        "required": ["rule"]
                    }
                }
            }
        ]

    async def step(self):
        # Insert current memory summary as context dynamically before thinking
        memory_summary = self.memory.get_summary()
        current_pos = self.env.get_robot_position()
        
        context_prompt = (
            f"{memory_summary}\n\n"
            f"Robot Current Location: {current_pos}\n"
            f"What is your next action? Think, call tools, explore or write down rules if you discovered something."
        )

        if not self.messages:
            self.messages.append({"role": "system", "content": SYSTEM_PROMPT})
            self.messages.append({"role": "user", "content": "Start exploring the room."})
        else:
            # Update the latest user prompt with current state
            self.messages.append({"role": "user", "content": context_prompt})

        print("\n[Thinking] Robot is thinking...", flush=True)
        response = self.ollama_client.chat(
            model=self.model,
            messages=self.messages,
            tools=self.get_tool_definitions()
        )
        
        msg = response["message"]
        self.messages.append(msg)

        if msg.get("content"):
            print(f"\n[Thought] Robot Thought: {msg['content']}", flush=True)

        if not msg.get("tool_calls"):
            # No tool called, agent just talked
            return

        for call in msg["tool_calls"]:
            fn_name = call["function"]["name"]
            fn_args = call["function"].get("arguments", {})
            
            print(f"[Action] Executing action: {fn_name}({fn_args})", flush=True)
            
            try:
                # Dispatch tool calls
                if fn_name == "scan_room":
                    res = self.env.scan_room()
                elif fn_name == "move_to":
                    res = self.env.move_to(float(fn_args["x"]), float(fn_args["y"]))
                elif fn_name == "examine_visually":
                    res = self.env.examine_visually(fn_args["object_name"])
                elif fn_name == "measure_temperature":
                    res = self.env.measure_temperature(fn_args["object_name"])
                elif fn_name == "measure_voltage":
                    res = self.env.measure_voltage(fn_args["object_name"])
                elif fn_name == "touch":
                    res = self.env.touch(fn_args["object_name"])
                elif fn_name == "taste":
                    res = self.env.taste(fn_args["object_name"])
                elif fn_name == "add_learned_rule":
                    rule_text = fn_args["rule"]
                    self.memory.add_learned_rule(rule_text)
                    res = {"status": "success", "rule_added": rule_text}
                    print(f"[Memory] Rule Saved to Memory: {rule_text}", flush=True)
                else:
                    res = {"error": f"Tool '{fn_name}' not implemented."}
            except Exception as e:
                res = {"error": str(e)}

            res_str = json.dumps(res)
            print(f"[Sensors] Sensory Feedback: {res_str}", flush=True)
            
            # Log episodic memory
            action_desc = f"{fn_name}({fn_args})"
            self.memory.add_episodic_log(action_desc, res_str)
            
            # Append tool response
            self.messages.append({
                "role": "tool",
                "name": fn_name,
                "content": res_str
            })
