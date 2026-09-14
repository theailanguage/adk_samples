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
Agent2Agent (A2A) Routing Integration (`app/app_utils/a2a.py`)
=============================================================
This module integrates Google's Agent2Agent (A2A) protocol into our FastAPI application.

What is A2A (Agent2Agent) Protocol? (Novice Guide):
---------------------------------------------------
1. **The Multi-Agent Future:**
   In real-world enterprise architectures, you rarely have just one monolithic agent.
   Instead, you have specialized agents: a "Website Generator Agent", a "Database Query Agent",
   a "Customer Support Agent", etc.

2. **The Discovery Problem & The "Agent Card":**
   How does Agent A know that Agent B exists and what Agent B is capable of doing?
   A2A solves this using an **Agent Card** (served at a standardized path like
   `/.well-known/agent-card.json`). The Agent Card is like an API "business card"
   specifying:
     - The agent's name and description.
     - Its skills and tools.
     - Its capabilities (e.g., streaming support).
     - Its communication endpoints and supported protocol versions.

3. **Communication via JSON-RPC:**
   Once an agent discovers another agent via its Agent Card, it sends requests and tasks
   using JSON-RPC over HTTP. This module mounts the endpoints needed to handle both:
     - The Agent Card endpoint (`create_agent_card_routes`)
     - The JSON-RPC endpoint (`create_jsonrpc_routes`)
"""

# Enable Python 3.10+ modern typing features across Python 3.9+ environments
from __future__ import annotations

# `os` provides access to environment variables like hostnames, ports, and cloud configs
import os

# `TYPE_CHECKING` is a boolean flag that is True only during static type analysis (e.g., in IDEs or mypy).
# It allows importing types needed for type hints without causing circular dependencies at runtime.
from typing import TYPE_CHECKING

# ------------------------------------------------------------------------------
# A2A SDK Server Imports
# ------------------------------------------------------------------------------
# `DefaultRequestHandler`: The core server dispatcher in the A2A SDK.
# It parses incoming JSON-RPC requests from client agents and delegates work to the executor.
from a2a.server.request_handlers import DefaultRequestHandler

# Route generation utilities that connect A2A handlers to FastAPI
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)

# `TaskStore`: Abstract base class/interface for storing the state of asynchronous A2A tasks
from a2a.server.tasks import TaskStore

# Data classes representing standard A2A data models
from a2a.types import AgentCapabilities, AgentCard, AgentExtension, AgentInterface

# Standardized path constant for discovering agent metadata (`/.well-known/agent-card.json`)
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH

# ------------------------------------------------------------------------------
# Google ADK A2A Integration Imports
# ------------------------------------------------------------------------------
# `A2aAgentExecutor`: Adapter that bridges the A2A protocol to ADK's `Runner`.
# When an A2A JSON-RPC request arrives, this executor turns it into an ADK runner execution.
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor

# `AgentCardBuilder`: Automatically inspects an ADK `Agent` (its name, tools, docstrings)
# and generates a compliant `AgentCard` JSON representation.
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder

# Conditional imports evaluated only by static type checkers, skipped at runtime
if TYPE_CHECKING:
    from fastapi import FastAPI
    from google.adk.agents import BaseAgent
    from google.adk.runners import Runner

# URI advertised on the agent card describing the executor extension shipped by ADK.
# Kept as a module-level constant so callers can override or extend the capabilities list when needed.
_ADK_AGENT_EXECUTOR_EXTENSION_URI = (
    "https://google.github.io/adk-docs/a2a/a2a-extension/"
)


# ------------------------------------------------------------------------------
# Backward Compatibility Helper
# ------------------------------------------------------------------------------
async def _add_v0_3_compat_interface(card: AgentCard) -> AgentCard:
    """Advertise a v0.3 JSON-RPC interface so the served card stays consumable by
    v0.3 A2A clients — notably Gemini Enterprise registration, whose validator
    still requires the 0.3 card shape (top-level ``url``/``protocolVersion``).
    """
    # If the card has modern interfaces defined, append a backward-compatible v0.3 definition
    if card.supported_interfaces:
        card.supported_interfaces.append(
            AgentInterface(
                protocol_binding="JSONRPC",
                protocol_version="0.3",
                url=card.supported_interfaces[0].url,
            )
        )
    return card


# ------------------------------------------------------------------------------
# Default Capabilities Definition
# ------------------------------------------------------------------------------
def _default_capabilities() -> AgentCapabilities:
    """Returns the default A2A capabilities used by scaffolded projects.
    
    Tells client agents that this agent supports:
      - Real-time token streaming (`streaming=True`)
      - The ADK agent executor extension for enhanced task processing
    """
    return AgentCapabilities(
        streaming=True,
        extensions=[
            AgentExtension(
                uri=_ADK_AGENT_EXECUTOR_EXTENSION_URI,
                description=("Ability to use the new agent executor implementation"),
            ),
        ],
    )


# ------------------------------------------------------------------------------
# Public URL Resolution Helper
# ------------------------------------------------------------------------------
def _resolve_app_url(app_url: str | None) -> str:
    """Resolve the public base URL advertised inside the agent card.

    In distributed agent networks, an agent must tell others where it can be reached.
    Resolution order:
      1. Explicit `app_url` argument passed to the function
      2. `APP_URL` environment variable (e.g., https://my-agent.run.app)
      3. Google Cloud Vertex AI Agent Engine dynamic gateway URL
      4. Local development default (`http://0.0.0.0:8000`)
    """
    # 1. Explicitly passed parameter
    if app_url:
        return app_url
    
    # 2. Configured via environment variable
    if env_url := os.getenv("APP_URL"):
        return env_url

    # 3. Running inside Google Cloud Agent Engine (Vertex AI)
    agent_engine_id = os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ID")
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    # Location defaults to "us-east1" if not specified.
    # Note: We do NOT use GOOGLE_CLOUD_LOCATION because agent.py pins it to "global",
    # which would build an invalid URL endpoint.
    location = os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_LOCATION", "us-east1")
    if agent_engine_id and project and location:
        return (
            f"https://{location}-aiplatform.googleapis.com/reasoningEngines/v1"
            f"/projects/{project}/locations/{location}"
            f"/reasoningEngines/{agent_engine_id}/api"
        )

    # 4. Fallback for local testing
    return "http://0.0.0.0:8000"


# ------------------------------------------------------------------------------
# Main Route Attachment Function
# ------------------------------------------------------------------------------
async def attach_a2a_routes(
    app: FastAPI,
    *,
    agent: BaseAgent,
    runner: Runner,
    task_store: TaskStore,
    rpc_path: str,
    capabilities: AgentCapabilities | None = None,
    agent_version: str | None = None,
    app_url: str | None = None,
) -> None:
    """Register A2A routes (JSON-RPC + agent-card endpoints) under ``rpc_path``.

    What this function does step-by-step:
      1. Resolves the public URL, version, and capabilities of the agent.
      2. Automatically builds an AgentCard from the `agent` instance.
      3. Sets up an A2A Request Handler connected to the ADK `Runner` and `task_store`.
      4. Mounts the Agent Card route and JSON-RPC routes onto the FastAPI `app`.
    """
    # Determine the public URL where this agent can be contacted
    resolved_app_url = _resolve_app_url(app_url)
    
    # Determine agent version (defaults to 0.1.0 or AGENT_VERSION env var)
    resolved_agent_version = agent_version or os.getenv("AGENT_VERSION", "0.1.0")
    
    # Determine agent capabilities (streaming, extensions)
    resolved_capabilities = capabilities or _default_capabilities()

    # Step 1: Build the Agent Card asynchronously
    # The builder inspects `agent` to automatically extract its name, tools/skills, and system prompt.
    agent_card = await AgentCardBuilder(
        agent=agent,
        capabilities=resolved_capabilities,
        rpc_url=f"{resolved_app_url}{rpc_path}",
        agent_version=resolved_agent_version,
    ).build()

    # Step 2: Initialize the request handler
    # Connects incoming A2A network requests to our ADK runner via `A2aAgentExecutor`.
    request_handler = DefaultRequestHandler(
        agent_executor=A2aAgentExecutor(runner=runner, force_new_version=True),
        task_store=task_store,
        agent_card=agent_card,
    )

    # Step 3: Mount the endpoints onto the FastAPI web app
    add_a2a_routes_to_fastapi(
        app,
        # Endpoint 1: Serves the agent card metadata at `/.well-known/agent-card.json`
        agent_card_routes=create_agent_card_routes(
            agent_card,
            card_modifier=_add_v0_3_compat_interface,
            card_url=f"{rpc_path}{AGENT_CARD_WELL_KNOWN_PATH}",
        ),
        # Endpoint 2: Serves the JSON-RPC execution endpoint at `rpc_path`
        jsonrpc_routes=create_jsonrpc_routes(
            request_handler,
            rpc_url=rpc_path,
            enable_v0_3_compat=True,
        ),
    )
