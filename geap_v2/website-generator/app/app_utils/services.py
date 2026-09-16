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
Shared ADK Services Module (`app/app_utils/services.py`)
========================================================
This module configures the state persistence layers (Sessions & Artifacts)
for the entire agent application.

Agent Concepts Explained for Novices:
-------------------------------------
1. **What is an Agent Session?**
   - LLMs are fundamentally stateless: they do not remember previous messages on their own.
   - To have a coherent multi-turn conversation (e.g., "What's the weather?" followed by "What about tomorrow?"),
     the agent needs memory.
   - A **Session** stores the history of user messages, assistant responses, tool executions,
     and custom state variables associated with a specific user.
   - In ADK, a `SessionService` is responsible for saving and loading these session records.

2. **What is an Agent Artifact?**
   - During complex workflows, an agent might create, read, or update files—such as
     generated HTML code, downloaded PDFs, images, or output reports.
   - These generated files are called **Artifacts**.
   - An `ArtifactService` handles storing these artifacts (either in memory during testing
     or in Google Cloud Storage (GCS) in production).

3. **Why "Shared" Services?**
   - Our FastAPI application serves THREE different API protocols:
       1) Native ADK routes (`/run_sse`)
       2) A2A protocol routes (`/a2a/...`)
       3) Vertex AI Reasoning Engine routes (`/api/reasoning_engine`)
   - By creating process-wide singletons registered under `shared://`, any session created
     on one interface is instantly visible and usable across all other interfaces!
"""

# Enable modern type hinting syntax from Python 3.10+ (like `str | None` instead of `Optional[str]`)
from __future__ import annotations

# `functools`: Standard library module providing higher-order functions.
# We use `functools.cache` to implement the Singleton pattern (caching the function output
# so the service is only initialized once and reused everywhere).
import functools

# `os`: Standard library module to read environment variables (cloud project, bucket name, etc.).
import os

# ------------------------------------------------------------------------------
# ADK Artifact Services
# ------------------------------------------------------------------------------
# `GcsArtifactService`: Persists generated agent artifacts directly to a Google Cloud Storage (GCS) bucket.
# `InMemoryArtifactService`: Keeps artifacts in RAM; useful for local development and fast unit testing.
from google.adk.artifacts import GcsArtifactService, InMemoryArtifactService

# `get_service_registry`: Registry where ADK looks up storage backends by URI scheme (e.g., "shared://", "gcs://").
from google.adk.cli.service_registry import get_service_registry

# Factory function to build session services based on configured URI strings (e.g. database, memory, or cloud).
from google.adk.cli.utils.service_factory import create_session_service_from_options

# ------------------------------------------------------------------------------
# Service URI Constants
# ------------------------------------------------------------------------------
# These custom URI schemes tell ADK components to use our custom shared providers registered below.
SESSION_SERVICE_URI = "shared://session"
ARTIFACT_SERVICE_URI = "shared://artifact"

# Compute the root agent project directory by traversing 3 levels up from this file.
_AGENT_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


# ------------------------------------------------------------------------------
# Session Service Provider
# ------------------------------------------------------------------------------
# `@functools.cache` ensures this function runs only ONCE. Subsequent calls return the
# exact same cached session service instance (Singleton pattern).
@functools.cache
def get_session_service():
    """Returns the process-wide session service shared across every serving surface.

    Resolution strategy:
      1. If `SESSION_SERVICE_URI` environment variable is set, use ADK's factory.
      2. If deployed to Google Cloud Agent Engine (`GOOGLE_CLOUD_AGENT_ENGINE_ID` set),
         use Vertex AI's managed cloud session service.
      3. Otherwise (local development), fall back to `InMemorySessionService` stored in RAM.
    """
    # 1. Custom session service URI provided explicitly via environment variable
    if uri := os.environ.get("SESSION_SERVICE_URI"):
        return create_session_service_from_options(
            base_dir=_AGENT_DIR, session_service_uri=uri
        )
    
    # 2. Running on Google Cloud Vertex AI Agent Engine
    if agent_engine_id := os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID"):
        # Import Vertex AI session service dynamically so local developers don't need cloud credentials
        from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService

        return VertexAiSessionService(
            project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
            # Runtime-injected agent-engine region, not GOOGLE_CLOUD_LOCATION
            # (which agent.py pins to "global").
            location=os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_LOCATION")
            or os.environ.get("GOOGLE_CLOUD_LOCATION"),
            agent_engine_id=agent_engine_id,
        )
    
    # 3. Default fallback: In-Memory session storage (ideal for local testing without cloud setup)
    from google.adk.sessions.in_memory_session_service import InMemorySessionService

    return InMemorySessionService()


# ------------------------------------------------------------------------------
# Artifact Service Provider
# ------------------------------------------------------------------------------
@functools.cache
def get_artifact_service():
    """Returns the process-wide artifact service: GCS when a bucket is set, else in-memory.

    Resolution strategy:
      1. If `LOGS_BUCKET_NAME` environment variable is set, save artifacts to Google Cloud Storage.
      2. Otherwise, store artifacts in memory (RAM) for fast local iteration.
    """
    # If a GCS bucket name is provided, persist files to the cloud bucket
    if bucket := os.environ.get("LOGS_BUCKET_NAME"):
        return GcsArtifactService(bucket_name=bucket)
    
    # Otherwise keep files in RAM
    return InMemoryArtifactService()


# ------------------------------------------------------------------------------
# ADK Service Registry Hook
# ------------------------------------------------------------------------------
# ADK has a central service registry. Here, we register our custom scheme handler:
# Whenever ADK encounters a URI starting with `shared://`, it calls our factory functions.
_registry = get_service_registry()
_registry.register_session_service("shared", lambda uri, **kw: get_session_service())
_registry.register_artifact_service("shared", lambda uri, **kw: get_artifact_service())
