# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Agent Definition Module (`app/agent.py`)
========================================
This is the core definition file for our AI Agent!

If you are new to AI Agent development, here is what is happening conceptually:
-------------------------------------------------------------------------------
1. **What is an LLM vs an Agent?**
   - An **LLM (Large Language Model)** like Gemini is a text predictor; it takes a 
     prompt and generates a probable completion. By itself, it has no memory, 
     cannot browse live data, and cannot perform actions.
   - An **Agent** wraps the LLM with *agency*: it is given a goal/persona 
     (instructions), memory (sessions), and capabilities (tools). The agent can 
     reason, decide to call a tool, inspect the result, and decide what to do next.

2. **What is Function Calling / Tool Use?**
   - In ADK, standard Python functions serve as "tools".
   - The framework inspects the function's name, type hints, and docstring, and 
     translates them into a JSON schema for the Gemini model.
   - When a user asks a question requiring external data (e.g., "What's the weather in SF?"),
     the LLM returns a structured request asking the runtime to run that tool.
   - The runtime executes the Python function, returns the output to the LLM, and 
     the LLM formulates the final conversational response.

3. **What is Google ADK (Agent Development Kit)?**
   - Google ADK is an open-source framework designed to build, run, evaluate, 
     and deploy production-ready AI agents using Google Gemini and Vertex AI.
"""

# ------------------------------------------------------------------------------
# Standard Library Imports
# ------------------------------------------------------------------------------
# `datetime` is Python's standard library module for manipulating dates and times.
# We will use it in our `get_current_time` tool to query the current clock time.
import datetime

# `ZoneInfo` (standard in Python 3.9+) provides IANA time zone support (e.g., "America/Los_Angeles").
# This ensures that time calculations accurately account for daylight saving time and offsets.
from zoneinfo import ZoneInfo

# ------------------------------------------------------------------------------
# Google ADK & GenAI Imports
# ------------------------------------------------------------------------------
# `Agent`: The fundamental building block in ADK. It defines an intelligent agent with:
#   - A model (e.g., Gemini)
#   - System instructions (who the agent is and how it behaves)
#   - Tools (actions the agent can perform)
#   - Sub-agents (for hierarchical or multi-agent orchestration)
from google.adk.agents import Agent

# `App`: The top-level application wrapper in ADK. An `App` encapsulates one or more
# agents (starting from a `root_agent`) and manages sessions, runners, and configuration.
from google.adk.apps import App

# `Gemini`: The ADK model wrapper that connects to Google's Gemini models using the
# new Google GenAI SDK (`google-genai`).
from google.adk.models import Gemini

# `types`: Provides data structures, configurations, and schemas used across the Google GenAI SDK,
# such as retry configurations, content types, and generation parameters.
from google.genai import types

# ------------------------------------------------------------------------------
# Model Configuration
# ------------------------------------------------------------------------------
# We define the model name string here as a constant.
# "gemini-3.7-flash" is a state-of-the-art, high-speed, multimodal Gemini model.
# Flash models are optimized for low latency and high cost-efficiency, making them
# ideal for real-time conversational agents and tool-calling loops.
MODEL = "gemini-3.7-flash"


# ------------------------------------------------------------------------------
# Tool Definitions
# ------------------------------------------------------------------------------
# In AI agent architectures, a "Tool" is simply a Python function that the agent
# is allowed to execute when answering user queries.
#
# CRITICAL RULE FOR TOOLS:
# The docstring and type hints (`query: str -> str`) are NOT just documentation for
# human developers! The ADK converts them into an OpenAPI/JSON schema that is fed
# directly to the LLM. The LLM reads this description to understand:
#   1. When should I call this tool? (from the docstring summary)
#   2. What arguments should I provide? (from the Args section)
#   3. What type of data will it return? (from the Returns section and return type hint)

def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    # For demonstration purposes, this tool simulates external weather API lookups.
    # In a production app, you would use `requests` or `httpx` to call an API like OpenWeatherMap.
    
    # Check if the user query mentions San Francisco (case-insensitively)
    if "sf" in query.lower() or "san francisco" in query.lower():
        # Return a simulated cloudy/foggy weather report
        return "It's 60 degrees and foggy."
    
    # Default fallback simulated response for any other location
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    # Determine the IANA timezone string based on the city requested in the query.
    if "sf" in query.lower() or "san francisco" in query.lower():
        # San Francisco uses the Pacific Time Zone
        tz_identifier = "America/Los_Angeles"
    else:
        # If we don't recognize the city in this simple demo, return an informative error message.
        # The LLM will read this returned string and politely explain to the user that it doesn't know.
        return f"Sorry, I don't have timezone information for query: {query}."

    # Create a ZoneInfo object representing the Pacific timezone
    tz = ZoneInfo(tz_identifier)
    
    # Get the current date and time aware of that specific timezone
    now = datetime.datetime.now(tz)
    
    # Format the time nicely into Year-Month-Day Hour:Minute:Second Timezone (e.g. 2026-09-13 15:30:00 PDT-0700)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


# ------------------------------------------------------------------------------
# Root Agent Configuration
# ------------------------------------------------------------------------------
# Here we instantiate our `root_agent` using ADK's `Agent` class.
# The "root agent" is the primary entry point agent that receives the user's initial prompt.
root_agent = Agent(
    # `name`: Unique identifier for this agent. Used in telemetry, logs, and A2A routing.
    name="website_generator",
    
    # `model`: Configures which LLM powers this agent.
    # We wrap the model name inside `Gemini(...)` and specify retry resilience.
    model=Gemini(
        model=MODEL,
        # `retry_options`: Configures automatic retry behavior for network glitches or rate limits.
        # `attempts=3` means if an HTTP error (like 429 or 503) occurs, the SDK retries up to 3 times.
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    
    # `instruction`: The system prompt for the LLM.
    # This establishes the persona, behavioral boundaries, and tone of the agent.
    # The LLM always sees this instruction in its context window before any conversation messages.
    instruction="You are a helpful AI assistant designed to provide accurate and useful information.",
    
    # `tools`: A list of Python functions the agent is allowed to invoke.
    # The ADK automatically parses their signatures and docstrings, exposes them to Gemini,
    # and handles executing them when Gemini requests a function call.
    tools=[get_weather, get_current_time],
)


# ------------------------------------------------------------------------------
# Top-Level ADK Application
# ------------------------------------------------------------------------------
# An `App` encapsulates your agent setup into a deployable application package.
# It links the `root_agent` to an application name.
app = App(
    # `root_agent`: The primary agent that handles conversations in this application.
    root_agent=root_agent,
    # `name`: The application identifier, referenced in API endpoints (e.g., `/apps/app/...`).
    name="app",
)
