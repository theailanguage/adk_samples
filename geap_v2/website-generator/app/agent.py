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
import os
import subprocess
import json
import tempfile

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

# We'll use a fixed temp directory name so it persists across tool calls
DEPLOY_DIR = os.path.join(tempfile.gettempdir(), "geap_website_deploy")

def save_website_content(html_content: str) -> str:
    """Saves the generated HTML content to the deployment directory and configures Firebase.
    
    Args:
        html_content: The unified HTML, CSS, and JS content.
    """
    public_dir = os.path.join(DEPLOY_DIR, "public")
    os.makedirs(public_dir, exist_ok=True)
    
    with open(os.path.join(public_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
        
    firebase_config = {
        "hosting": {
            "public": "public",
            "ignore": [
                "firebase.json",
                "**/.*",
                "**/node_modules/**"
            ]
        }
    }
    with open(os.path.join(DEPLOY_DIR, "firebase.json"), "w", encoding="utf-8") as f:
        json.dump(firebase_config, f, indent=2)
        
    return f"Website content saved successfully to {DEPLOY_DIR}. You can now call deploy_saved_website."


def deploy_saved_website() -> str:
    """Deploys the previously saved website to Firebase Hosting Preview Channels."""
    if not os.path.exists(DEPLOY_DIR):
        return "Error: No website content found. Please call save_website_content first."
        
    try:
        env = os.environ.copy()
        env["npm_config_engine_strict"] = "false"
        
        # Fetch the active project to pass to the Firebase CLI.
        # 1. Check for standard GCP serverless environment variables (Cloud Run, Cloud Functions)
        gcloud_proj = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
        
        # 2. If not found, try fetching from the local gcloud CLI
        if not gcloud_proj:
            try:
                gcloud_proj = subprocess.run(
                    ["gcloud", "config", "get-value", "project"], 
                    capture_output=True, text=True, check=True
                ).stdout.strip()
            except Exception:
                gcloud_proj = None
            
        cmd = ["npx", "-y", "firebase-tools@latest", "hosting:channel:deploy", "ai-generated-preview", "--expires", "30m", "--non-interactive"]
        if gcloud_proj:
            cmd.extend(["--project", gcloud_proj])
            
        result = subprocess.run(
            cmd,
            cwd=DEPLOY_DIR,
            env=env,
            capture_output=True,
            text=True,
            check=True
        )
        print("Firebase Deploy Output:\n", result.stdout)
        return f"Successfully deployed! Output:\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        # Print to console for debugging
        print("Firebase Deploy Failed!\nSTDOUT:\n", e.stdout, "\nSTDERR:\n", e.stderr)
        return f"Failed to deploy.\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"


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
    instruction=(
        "You are a website generator. Take in the user query, understand context and "
        "generate a single page HTML CSS JS unified document. You may converse freely with the user. "
        "When asked to deploy the website, first use `save_website_content` to save the HTML document, "
        "and then use `deploy_saved_website` to execute the deployment."
    ),
    
    # `tools`: A list of Python functions the agent is allowed to invoke.
    # The ADK automatically parses their signatures and docstrings, exposes them to Gemini,
    # and handles executing them when Gemini requests a function call.
    tools=[save_website_content, deploy_saved_website],
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
