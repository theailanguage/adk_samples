"""
Travel planner coordinator agent declaration.

This is the central orchestration/coordinator agent that acts as a manager 
and delegates specialized tasks to its sub-agents.
"""

# Import pathlib for clean cross-platform path resolution.
import pathlib

# Import sys to allow runtime modification of Python's module search path (sys.path).
import sys

# Import the core Agent class from Google ADK.
from google.adk.agents import Agent

# --- Sys Path Modification & Peer Sub-package Imports ---
# Get the absolute path of the directory containing this script.
current_dir = pathlib.Path(__file__).parent.resolve()

# Go up one level to find the root 'agents' package directory.
parent_dir = current_dir.parent

# In Python, relative imports between separate subfolders (packages) can sometimes 
# cause issues depending on how the execution entry point is called. By dynamically 
# adding the parent 'agents' directory to sys.path, we can perform clean, robust, 
# absolute imports of peer subagent modules from any context.
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Clean absolute imports of peer sub-agents.
# Since we added 'parent_dir' to sys.path, these packages can be resolved absolutely.
from weather_checker.agent import root_agent as weather_checker
from flight_booker.agent import root_agent as flight_booker
from itinerary_agent.agent import root_agent as itinerary_agent

# --- Load Instructions ---
instruction_path = current_dir / "instruction.txt"
with open(instruction_path, "r", encoding="utf-8") as f:
    instruction_text = f.read()

# --- Coordinator Agent Initialization ---
root_agent = Agent(
    # Unique name for system orchestration.
    name="travel_planner",
    
    # Specify the core Gemini language model that powers the coordinator.
    # The coordinator receives user prompts and determines which subagent 
    # to delegate to based on their descriptions.
    # model="gemini-flash-latest",  # Canonical Gemini model
    model="gemini-2.5-flash",  # Canonical Gemini model
    
    # Registers the specialized worker sub-agents that this coordinator can manage.
    # When the coordinator agent requires specific sub-tasks, it relies on the ADK's 
    # hierarchical delegation to hand off conversation contexts to these sub-agents.
    sub_agents=[weather_checker, flight_booker, itinerary_agent],
    
    # System instructions guiding the coordination flow.
    instruction=instruction_text,
    
    # Explanatory description of the coordinator.
    description="The main travel planner coordinator that acts as a manager and delegates to specialized subagents.",
)
