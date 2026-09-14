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
FastAPI Server Entrypoint (`app/fast_api_app.py`)
=================================================
This file turns our AI agent into a full-featured web server and REST/streaming API.

Key Agent Concepts Explained for Novices:
-----------------------------------------
1. **Why do we need a Web Server for an AI Agent?**
   - An agent defined in Python (`app/agent.py`) can run locally in a script, but in
     production, web browsers, frontends, mobile apps, or other services need to
     talk to it over the network via HTTP or WebSocket connections.
   - FastAPI exposes REST endpoints, Server-Sent Events (SSE) streams, and JSON-RPC
     interfaces so clients can send messages and receive streamed answers.

2. **What is Server-Sent Events (SSE)?**
   - When an LLM generates a response, it produces text token-by-token.
   - Instead of waiting 10 seconds for the entire answer to finish, SSE allows the
     server to push each token to the client in real-time as soon as it is generated.
   - This creates the familiar "typing" animation seen in ChatGPT and Gemini.

3. **Multi-Protocol Support in this File:**
   This server exposes THREE ways to communicate with the agent:
     a) **ADK Native Routes (`/run_sse`, `/apps/...`)**: Standard streaming endpoints
        used by ADK clients and the built-in web UI.
     b) **A2A (Agent2Agent) Protocol (`/a2a/...`)**: Google's open protocol allowing
        autonomous AI agents to discover each other and collaborate.
     c) **Reasoning Engine Adapter (`/api/reasoning_engine`)**: Vertex AI's standard
        calling contract for Google Cloud Console and Gemini Enterprise.
"""

# ------------------------------------------------------------------------------
# Standard Library Imports
# ------------------------------------------------------------------------------
# `contextlib` provides utilities for working with context managers (objects with `with` statements).
# We use `asynccontextmanager` to define the lifespan (startup/shutdown lifecycle) of FastAPI.
import contextlib

# `os` provides tools to interact with the operating system, access file paths,
# and read environment variables (like API keys, cloud project IDs, and ports).
import os

# `AsyncIterator` is a typing class that describes an asynchronous generator
# (a function using `async def` that yields values asynchronously).
from collections.abc import AsyncIterator

# ------------------------------------------------------------------------------
# Third-Party & Framework Imports
# ------------------------------------------------------------------------------
# `InMemoryTaskStore`: A simple in-memory storage manager for tracking A2A tasks.
# When other agents delegate tasks to this agent, this store tracks task status (queued, running, completed).
from a2a.server.tasks import InMemoryTaskStore

# `load_dotenv`: Reads key-value pairs from a `.env` file in the project root
# and adds them to `os.environ` so secret keys and configuration can be loaded safely.
from dotenv import load_dotenv

# `FastAPI`: High-performance, modern Python web framework used for building web APIs.
from fastapi import FastAPI

# `get_fast_api_app`: Built-in helper from ADK that constructs a pre-configured FastAPI app.
# It automatically sets up default routes for conversation management, agent running, and web UI.
from google.adk.cli.fast_api import get_fast_api_app

# `Runner`: The execution brain in ADK. A `Runner` takes an `App`, binds it to session
# and artifact services, and handles the orchestrating loop: receiving user inputs,
# prompting the model, executing tool calls, and saving history.
from google.adk.runners import Runner

# ------------------------------------------------------------------------------
# Application Utilities Imports
# ------------------------------------------------------------------------------
# `services`: Manages shared session storage (chat history) and artifact storage (generated files/data).
from app.app_utils import services

# `attach_a2a_routes`: Helper function to register Agent-to-Agent (A2A) endpoints.
from app.app_utils.a2a import attach_a2a_routes

# `attach_reasoning_engine_routes`: Helper function to register endpoints required by
# Google Cloud Vertex AI's Reasoning Engine infrastructure.
from app.app_utils.reasoning_engine_adapter import (
    attach_reasoning_engine_routes,
)

# ------------------------------------------------------------------------------
# Environment & Configuration Setup
# ------------------------------------------------------------------------------
# Load environment variables from the local `.env` file into `os.environ`.
load_dotenv()

# `allow_origins`: Configures Cross-Origin Resource Sharing (CORS).
# CORS tells the browser which frontend domains (e.g. http://localhost:3000)
# are permitted to make API calls to this backend server.
# If `ALLOW_ORIGINS` is provided as a comma-separated string, split it into a list; otherwise None.
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

# `otel_to_cloud`: OpenTelemetry flag.
# If set to "true" or "1", performance metrics and distributed execution traces
# are automatically forwarded to Google Cloud Monitoring & Cloud Trace for observability.
otel_to_cloud = os.environ.get(
    "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY", ""
).lower() in ("true", "1")

# `AGENT_DIR`: The root directory path of the website-generator project.
# `__file__` is this file (`app/fast_api_app.py`).
# Taking two parent directories gives the base folder of the project.
AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ------------------------------------------------------------------------------
# Lifespan Management (Startup and Shutdown Logic)
# ------------------------------------------------------------------------------
# In FastAPI, a `lifespan` function defines actions that should occur:
#   1. BEFORE the server begins accepting requests (startup phase, before `yield`)
#   2. AFTER the server stops receiving requests (shutdown phase, after `yield`)
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manages application startup and shutdown lifecycle.

    During startup:
      - Imports the ADK agent and app definition lazily (to prevent circular imports).
      - Initializes the ADK `Runner` connected to session and artifact stores.
      - Registers the dynamic A2A (Agent2Agent) communication endpoints.
    """
    # Lazy imports: We import `app` and `root_agent` here inside the function
    # so that `agent.py` and `fast_api_app.py` do not get stuck in circular dependency loops.
    from app.agent import app as adk_app
    from app.agent import root_agent

    # Instantiate the ADK Runner.
    # The Runner coordinates executing the agent's logic.
    runner = Runner(
        # `app`: The ADK App containing the root agent and configuration.
        app=adk_app,
        # `session_service`: Where conversation histories (messages, turns, states) are stored.
        session_service=services.get_session_service(),
        # `artifact_service`: Where files or documents produced by the agent are stored.
        artifact_service=services.get_artifact_service(),
        # `auto_create_session`: If True, automatically creates a new session if the client doesn't provide one.
        auto_create_session=True,
    )
    
    # Store references to the runner and app name in FastAPI's shared application state (`app.state`).
    # This allows other route handlers across the app to access them.
    app.state.runner = runner
    app.state.agent_app_name = adk_app.name

    # Mount Agent-to-Agent (A2A) routes onto the FastAPI application.
    # This registers:
    #   - `/.well-known/agent-card.json`: A manifest describing this agent's skills to other agents.
    #   - `/a2a/{app_name}`: A JSON-RPC endpoint allowing external agents to send requests.
    await attach_a2a_routes(
        app,
        agent=root_agent,
        runner=runner,
        task_store=InMemoryTaskStore(),
        rpc_path=f"/a2a/{adk_app.name}",
    )

    # `yield` pauses execution here while the FastAPI server is running and serving requests.
    # When the server receives a shutdown signal (e.g. CTRL+C), execution resumes immediately after `yield`.
    yield


# ------------------------------------------------------------------------------
# FastAPI Application Construction
# ------------------------------------------------------------------------------
# `get_fast_api_app` is an ADK utility that creates a pre-wired FastAPI instance.
# It sets up default ADK routes such as:
#   - `POST /run_sse`: Server-Sent Events endpoint to chat with the agent in real time.
#   - `POST /apps/{app}/users/{user}/sessions`: Session creation and management.
app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,                      # Path to the agent project directory
    web=True,                                 # Enable the built-in ADK web testing UI in browser
    artifact_service_uri=services.ARTIFACT_SERVICE_URI,  # Shared artifact service scheme ("shared://artifact")
    allow_origins=allow_origins,              # Allowed CORS domains for frontend browser calls
    session_service_uri=services.SESSION_SERVICE_URI,    # Shared session service scheme ("shared://session")
    otel_to_cloud=otel_to_cloud,              # Enable Google Cloud OpenTelemetry tracing
    lifespan=lifespan,                        # Attach our startup/shutdown lifecycle hook
)

# Set human-readable metadata for the API documentation (Swagger UI available at `/docs`).
app.title = "website-generator"
app.description = "API for interacting with the Agent website-generator"

# Register proxy routes for Google Cloud Vertex AI Reasoning Engine:
#   - `/api/reasoning_engine` (for synchronous queries)
#   - `/api/stream_reasoning_engine` (for streaming queries)
# This enables the Vertex AI Console Playground and Gemini Enterprise to seamlessly talk to our agent.
attach_reasoning_engine_routes(app)


# ------------------------------------------------------------------------------
# Local Server Execution
# ------------------------------------------------------------------------------
# If this file is run directly from the command line (`python app/fast_api_app.py`):
if __name__ == "__main__":
    # `uvicorn` is an ASGI (Asynchronous Server Gateway Interface) web server implementation for Python.
    # It handles incoming network connections, HTTP requests, and websockets, passing them to FastAPI.
    import uvicorn

    # Run the server:
    #   - `host="0.0.0.0"`: Listen on all network interfaces (allows external/Docker connections).
    #   - `port=8000`: The TCP port number where the server will listen (http://localhost:8000).
    uvicorn.run(app, host="0.0.0.0", port=8000)
