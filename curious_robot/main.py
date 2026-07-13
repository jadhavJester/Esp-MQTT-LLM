import anyio
import os
import sys
import logging
from curious_robot.environment import Environment
from curious_robot.memory import MemoryManager
from curious_robot.agent import CuriousExplorerAgent

# Set up clean logging
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    print("=" * 60, flush=True)
    print("        WELCOME TO THE CURIOUS ROBOT SIMULATION        ", flush=True)
    print("=" * 60, flush=True)
    print("This simulation runs an LLM-driven robot agent that explores a", flush=True)
    print("room, touches/tastes objects, reflects on pain/heat/shocks,", flush=True)
    print("and records general physical safety rules to memory.json.", flush=True)
    print("=" * 60, flush=True)

    # Confirm API key is set
    if not os.environ.get("OLLAMA_API_KEY"):
        print("Error: OLLAMA_API_KEY environment variable is not set!", flush=True)
        print("Please run: $env:OLLAMA_API_KEY='your_key' in PowerShell first.", flush=True)
        sys.exit(1)

    # Initialize environment, memory, and agent
    env = Environment()
    memory = MemoryManager()
    
    # Clean memory for a fresh demonstration
    print("Cleaning previous session memory...", flush=True)
    memory.clear()
    
    agent = CuriousExplorerAgent(env, memory)
    
    # Run the loop for 10 steps to witness discovery and memory formation
    max_steps = 10
    print(f"\nStarting 10-step exploration sequence...", flush=True)
    
    for step_num in range(1, max_steps + 1):
        print(f"\n--- STEP {step_num}/{max_steps} ---", flush=True)
        try:
            await agent.step()
        except KeyboardInterrupt:
            print("\nSimulation aborted by user.", flush=True)
            break
        except Exception as e:
            print(f"\nError during step: {e}", flush=True)
            break
            
    print("\n" + "=" * 60, flush=True)
    print("        SIMULATION SEQUENCE FINISHED        ", flush=True)
    print("=" * 60, flush=True)
    print(memory.get_summary(), flush=True)
    print("=" * 60, flush=True)

if __name__ == "__main__":
    anyio.run(main)
