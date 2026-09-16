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
Vertex AI Reasoning Engine Adapter (`app/app_utils/reasoning_engine_adapter.py`)
==============================================================================
This module adapts our ADK agent to conform to the HTTP contract expected by
Google Cloud Vertex AI's "Reasoning Engine".

What is Vertex AI Reasoning Engine? (Novice Guide):
---------------------------------------------------
1. **Managed Agent Infrastructure in Google Cloud:**
   - When you deploy an AI agent to Google Cloud Vertex AI, it can run inside
     **Vertex AI Reasoning Engine**—a secure, scalable runtime for agentic workflows.
   - The Vertex AI Console provides a web-based "Playground" UI where developers and
     product managers can test agents directly in the Google Cloud browser console.

2. **The Reasoning Engine Calling Contract:**
   Instead of standard REST paths like `/chat`, Reasoning Engine uses a RPC-style
   dispatch pattern over HTTP:
     - Client posts JSON: `{"class_method": "stream_query", "input": {"message": "Hello"}}`
     - The server dynamically invokes the requested method on the underlying agent template.

3. **Why this Adapter File Exists:**
   This adapter registers two specific routes on our FastAPI application:
     - `POST /api/stream_reasoning_engine`: For real-time streaming queries.
     - `POST /api/reasoning_engine`: For standard request/response queries.
   By providing these routes, our agent works seamlessly inside Vertex AI Console Playground,
   Gemini Enterprise, and custom applications using the Vertex AI Python SDK.
"""

# ------------------------------------------------------------------------------
# Standard Library Imports
# ------------------------------------------------------------------------------
# `inspect` provides live introspection of Python objects (checking function signatures,
# whether a function is an async coroutine, etc.).
import inspect

# `json` provides encoding and decoding of JSON strings.
import json

# ------------------------------------------------------------------------------
# Third-Party & Framework Imports
# ------------------------------------------------------------------------------
# `AdkApp`: The official template class provided by Vertex AI Agent Engines for ADK applications.
# It encapsulates setting up runners, session services, and operations.
from agentplatform.agent_engines.templates.adk import AdkApp

# FastAPI web framework classes:
#   - `FastAPI`: The application class
#   - `HTTPException`: Used to return HTTP error responses (e.g., 404 Not Found)
#   - `Request`: Represents incoming HTTP requests
#   - `encoders.jsonable_encoder`: Converts complex Python/Pydantic objects into JSON-compatible types
#   - `responses`: Provides specialized HTTP response types (JSONResponse, StreamingResponse)
from fastapi import FastAPI, HTTPException, Request, encoders, responses

# Starlette concurrency helpers:
#   - `iterate_in_threadpool`: Consumes a synchronous generator in a background worker thread
#     so it does not block FastAPI's async event loop.
#   - `run_in_threadpool`: Runs a synchronous blocking function in a background worker thread.
from starlette.concurrency import iterate_in_threadpool, run_in_threadpool

# Shared state persistence services (sessions and artifacts)
from app.app_utils import services


# ------------------------------------------------------------------------------
# Instrumentor Helper
# ------------------------------------------------------------------------------
def _no_op_instrumentor_builder(project_id: str) -> None:
    """No-op instrumentor builder function.

    By returning `None`, `AdkApp.set_up()` preserves the existing startup telemetry
    instrumentation and content generation spans without overriding them.
    """
    return None


# ------------------------------------------------------------------------------
# Route Attachment Function
# ------------------------------------------------------------------------------
def attach_reasoning_engine_routes(app: FastAPI) -> None:
    """Register reasoning_engine routes that dispatch to an AdkApp template.

    Adds two HTTP POST routes to the FastAPI application:
      1. `/api/stream_reasoning_engine` (streaming tokens)
      2. `/api/reasoning_engine` (single synchronous JSON response)
    """
    # Closure variables to hold the lazy-loaded runtime and sets of allowed method names
    runtime: AdkApp | None = None
    streaming_methods: set[str] = set()
    sync_methods: set[str] = set()

    def get_runtime() -> AdkApp:
        """Lazy initialization helper to instantiate the Vertex AI AdkApp runtime.
        
        Initializes only upon the first incoming request to avoid startup delays.
        """
        nonlocal runtime, streaming_methods, sync_methods
        if runtime is None:
            # Lazy import to avoid circular dependencies
            from app.agent import app as adk_app

            # Instantiate the Vertex AI AdkApp template.
            # Notice we pass our process-wide shared session & artifact service builders
            # so sessions are synchronized with all other endpoints!
            runtime = AdkApp(
                app=adk_app,
                session_service_builder=services.get_session_service,
                artifact_service_builder=services.get_artifact_service,
                instrumentor_builder=_no_op_instrumentor_builder,
            )
            # Run one-time setup on the AdkApp template
            runtime.set_up()
            
            # `register_operations()` returns a dictionary mapping operation categories
            # (like "stream", "async_stream", "async", and "") to lists of allowed method names.
            operations = runtime.register_operations()
            
            # Collect names of methods that support streaming responses (e.g. stream_query, async_stream_query)
            streaming_methods = set(operations.get("stream", [])) | set(
                operations.get("async_stream", [])
            )
            # Collect names of methods that return synchronous responses (e.g. query, async_query)
            sync_methods = set(operations.get("", [])) | set(
                operations.get("async", [])
            )
        return runtime

    def resolve_method(class_method: str, *, streaming: bool):
        """Security validator: Ensures the client can only call pre-approved operations.
        
        Prevents arbitrary method execution attacks on the runtime object.
        """
        rt = get_runtime()
        allowed = streaming_methods if streaming else sync_methods
        if class_method not in allowed:
            # If the client requests a method not in the allowed operations list, return HTTP 404
            raise HTTPException(
                status_code=404,
                detail=f"Unsupported reasoning_engine method: {class_method!r}",
            )
        # Return the callable method attribute from the runtime object
        return getattr(rt, class_method)

    # --------------------------------------------------------------------------
    # Streaming Endpoint: /api/stream_reasoning_engine
    # --------------------------------------------------------------------------
    @app.post("/api/stream_reasoning_engine")
    async def stream_query(request: Request) -> responses.StreamingResponse:
        """Handles streaming queries from the Vertex AI Console Playground and SDK.

        Expects a JSON body like:
          {
            "class_method": "async_stream_query",
            "input": {
              "message": "Hi!",
              "user_id": "user_123"
            }
          }
        Streams back events as newline-delimited JSON chunks (`application/json`).
        """
        # Parse incoming JSON payload
        body = await request.json()
        
        # Verify and resolve the requested method
        method = resolve_method(body["class_method"], streaming=True)
        
        # Extract the input parameters dictionary
        kwargs = body.get("input") or {}
        
        # Call the method: await if it's an async coroutine, otherwise execute directly
        stream = (
            await method(**kwargs)
            if inspect.iscoroutinefunction(method)
            else method(**kwargs)
        )

        # Generator function that yields JSON strings terminated with a newline (`\n`)
        async def generator():
            # If the stream is an asynchronous generator (`async for`):
            if hasattr(stream, "__aiter__"):
                async for event in stream:
                    # Convert event object to JSON and yield with a newline delimiter
                    yield json.dumps(encoders.jsonable_encoder(event)) + "\n"
            # If the stream is a standard synchronous generator (`for`):
            else:
                # Consume in threadpool to prevent blocking FastAPI's event loop
                async for event in iterate_in_threadpool(stream):
                    yield json.dumps(encoders.jsonable_encoder(event)) + "\n"

        # Return an HTTP 200 StreamingResponse containing the streaming generator
        return responses.StreamingResponse(
            content=generator(), media_type="application/json"
        )

    # --------------------------------------------------------------------------
    # Non-Streaming Endpoint: /api/reasoning_engine
    # --------------------------------------------------------------------------
    @app.post("/api/reasoning_engine")
    async def query(request: Request) -> responses.JSONResponse:
        """Handles synchronous single-turn queries.

        Expects a JSON body like:
          {
            "class_method": "query",
            "input": {
              "message": "Hi!",
              "user_id": "user_123"
            }
          }
        Returns a single JSON response: `{"output": ...}`.
        """
        # Parse incoming JSON payload
        body = await request.json()
        
        # Verify and resolve the requested non-streaming method
        method = resolve_method(body["class_method"], streaming=False)
        
        # Extract input kwargs
        kwargs = body.get("input") or {}
        
        # Execute the method
        if inspect.iscoroutinefunction(method):
            output = await method(**kwargs)
        else:
            # Run blocking synchronous functions in a background threadpool
            output = await run_in_threadpool(method, **kwargs)
            
        # Return standard JSON response wrapped in {"output": ...}
        return responses.JSONResponse(
            content=encoders.jsonable_encoder({"output": output})
        )
