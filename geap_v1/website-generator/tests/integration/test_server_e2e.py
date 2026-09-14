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
End-to-End (E2E) Server Integration Tests (`tests/integration/test_server_e2e.py`)
================================================================================
This test suite verifies that the complete FastAPI server starts properly and all
four network protocols work over real HTTP connections:

1. **Native ADK SSE Route (`/run_sse`)**: Real-time event streaming.
2. **A2A JSON-RPC Streaming (`/a2a/app/`)**: Agent-to-Agent message exchange.
3. **A2A Agent Card Discovery (`/.well-known/agent-card.json`)**: Capability discovery.
4. **Vertex AI Reasoning Engine Adapter (`/api/stream_reasoning_engine`)**: Both sync & async.

E2E Testing Architecture (Novice Guide):
----------------------------------------
- **How it runs:** Pytest starts the Uvicorn web server in a separate background OS process
  using `subprocess.Popen`.
- **Readiness check:** The test polls the server until it responds HTTP 200 on the Agent Card endpoint.
- **Fixture teardown:** When all tests finish, Pytest cleanly terminates the server process.
"""

# ------------------------------------------------------------------------------
# Standard Library Imports
# ------------------------------------------------------------------------------
# `asyncio` allows running asynchronous coroutines inside synchronous test functions.
import asyncio

# `json` provides encoding and decoding between Python dictionaries and JSON strings.
import json

# `logging` provides structured log output with severity levels (INFO, ERROR, DEBUG).
import logging

# `os` enables reading and setting environment variables passed to the child server process.
import os

# `subprocess` allows running system commands and launching child processes (like uvicorn).
import subprocess

# `sys` provides access to Python interpreter information (like `sys.executable` to run Python).
import sys

# `threading` allows running background threads in parallel to pipe server logs to our terminal.
import threading

# `time` provides timing functions like `time.time()` and `time.sleep()` for timeouts and polling.
import time

# `uuid` generates universally unique identifiers (UUIDs) for random user IDs and session IDs.
import uuid

# `Iterator` type hint used for pytest generator fixtures (yielding a resource and tearing it down).
from collections.abc import Iterator

# `Any` type hint representing any data type.
from typing import Any

# ------------------------------------------------------------------------------
# Third-Party Testing & Networking Imports
# ------------------------------------------------------------------------------
# `httpx`: Modern asynchronous HTTP client used by the A2A client SDK.
import httpx

# `pytest`: Python's premier automated testing framework.
import pytest

# `requests`: Standard synchronous HTTP library used to send REST requests to the server.
import requests

# A2A SDK client modules used to test Agent-to-Agent communication:
from a2a.client import ClientConfig, create_client
from a2a.types import (
    Message,
    Part,
    Role,
    SendMessageRequest,
    StreamResponse,
    TaskState,
)

# Exception class raised by `requests` when a network connection fails (e.g. server not ready yet).
from requests.exceptions import RequestException

# ------------------------------------------------------------------------------
# Logging Configuration
# ------------------------------------------------------------------------------
# Configure the standard logger to output messages at INFO level and above
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------
# Server URLs and Constants
# ------------------------------------------------------------------------------
# The base URL where our background test server will listen on localhost
BASE_URL = "http://127.0.0.1:8000"

# Endpoint for native ADK Server-Sent Events (SSE) streaming
RUN_SSE_URL = BASE_URL + "/run_sse"

# Endpoint for A2A JSON-RPC communication
A2A_RPC_URL = BASE_URL + "/a2a/app/"

# Standard discovery path for the A2A Agent Card metadata document
AGENT_CARD_URL = A2A_RPC_URL + ".well-known/agent-card.json"

# Common HTTP headers specifying that request payloads are JSON
HEADERS = {"Content-Type": "application/json"}


# ------------------------------------------------------------------------------
# Helper Functions for Server Management
# ------------------------------------------------------------------------------
def log_output(pipe: Any, log_func: Any) -> None:
    """Reads lines from a subprocess pipe (stdout or stderr) and forwards them to a logger.
    
    This ensures that server logs appear in real-time in the test runner output.
    """
    for line in iter(pipe.readline, ""):
        log_func(line.strip())


def start_server() -> subprocess.Popen[str]:
    """Start the FastAPI server as a background subprocess using Uvicorn.
    
    Returns:
        A `subprocess.Popen` process handle representing the running server.
    """
    # Construct the command line arguments:
    # Uses the current Python executable (`sys.executable`) to invoke:
    #   python -m uvicorn app.fast_api_app:app --host 0.0.0.0 --port 8000
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.fast_api_app:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
    ]
    
    # Copy current environment variables and inject test-specific settings:
    env = os.environ.copy()
    env["INTEGRATION_TEST"] = "TRUE"
    # Set APP_URL to localhost so the A2A card advertises the local address
    env["APP_URL"] = BASE_URL
    
    # Launch the process non-blockingly
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,  # Capture standard output
        stderr=subprocess.PIPE,  # Capture error output
        text=True,               # Decode output as UTF-8 text rather than bytes
        bufsize=1,               # Line-buffered output
        env=env,                 # Pass our custom environment dictionary
    )

    # Launch background daemon threads to capture stdout and stderr asynchronously
    # (daemon=True means these threads exit automatically when the main program exits)
    threading.Thread(
        target=log_output, args=(process.stdout, logger.info), daemon=True
    ).start()
    threading.Thread(
        target=log_output, args=(process.stderr, logger.error), daemon=True
    ).start()

    return process


def wait_for_server(timeout: int = 90, interval: int = 1) -> bool:
    """Poll the server until it is fully started and responsive.
    
    The server lifespan must complete before the Agent Card endpoint returns HTTP 200.
    We poll every `interval` seconds until `timeout` seconds have elapsed.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # Send an HTTP GET request to check if the server is up
            response = requests.get(AGENT_CARD_URL, timeout=10)
            if response.status_code == 200:
                logger.info("Server is ready")
                return True
        except RequestException:
            # Server is not accepting connections yet; ignore and try again
            pass
        time.sleep(interval)
        
    logger.error(f"Server did not become ready within {timeout} seconds")
    return False


# ------------------------------------------------------------------------------
# Pytest Session Fixture
# ------------------------------------------------------------------------------
# `scope="session"` means this fixture runs ONCE for the entire test session,
# sharing the single server instance across all tests in this file.
@pytest.fixture(scope="session")
def server_fixture(request: Any) -> Iterator[subprocess.Popen[str]]:
    """Pytest fixture to start and stop the server for testing."""
    logger.info("Starting server process")
    # Launch the server process
    server_process = start_server()
    
    # Wait until the server responds to HTTP requests
    if not wait_for_server():
        pytest.fail("Server failed to start")
    logger.info("Server process started")

    # Teardown logic: registered with `addfinalizer` to execute when tests finish
    def stop_server() -> None:
        logger.info("Stopping server process")
        server_process.terminate()  # Send SIGTERM to stop uvicorn
        server_process.wait()       # Wait for the process to exit cleanly
        logger.info("Server process stopped")

    request.addfinalizer(stop_server)
    # Yield the running process handle to the tests
    yield server_process


# ------------------------------------------------------------------------------
# Test 1: Native ADK Server-Sent Events (SSE) Route
# ------------------------------------------------------------------------------
def test_adk_run_sse(server_fixture: subprocess.Popen[str]) -> None:
    """Test the native ADK route (/run_sse) end to end."""
    logger.info("Starting ADK /run_sse test")
    
    # Generate a unique test user ID
    user_id = f"user_{uuid.uuid4()}"
    
    # Initial session state data (user preferences)
    session_data = {"state": {"preferred_language": "English", "visit_count": 1}}

    # Step 1: Create a session on the server via POST /apps/{app}/users/{user}/sessions
    session_response = requests.post(
        f"{BASE_URL}/apps/app/users/{user_id}/sessions",
        headers=HEADERS,
        json=session_data,
        timeout=60,
    )
    # Verify session creation returned HTTP 200 OK
    assert session_response.status_code == 200
    session_id = session_response.json()["id"]

    # Step 2: Prepare payload for the `/run_sse` streaming endpoint
    data = {
        "app_name": "app",
        "user_id": user_id,
        "session_id": session_id,
        "new_message": {"role": "user", "parts": [{"text": "Hi!"}]},
        "streaming": True,
    }
    
    # Step 3: Send POST request with `stream=True` to consume chunked HTTP stream
    response = requests.post(
        RUN_SSE_URL, headers=HEADERS, json=data, stream=True, timeout=60
    )
    assert response.status_code == 200

    # Step 4: Parse SSE events formatted as "data: {JSON}\n\n"
    events = []
    for line in response.iter_lines():
        if line:
            line_str = line.decode("utf-8")
            if line_str.startswith("data: "):
                # Strip the "data: " prefix and parse the JSON payload
                events.append(json.loads(line_str[6:]))

    # Assert that we received events
    assert events, "No events received from stream"
    
    # Check that at least one event in the stream contained text from the assistant
    has_text_content = any(
        (content := event.get("content"))
        and content.get("parts")
        and any(part.get("text") for part in content["parts"])
        for event in events
    )
    assert has_text_content, "Expected at least one event with text content"


# ------------------------------------------------------------------------------
# Test 2: Agent2Agent (A2A) JSON-RPC Streaming Route
# ------------------------------------------------------------------------------
def test_a2a_chat_stream(server_fixture: subprocess.Popen[str]) -> None:
    """Test the A2A route using the JSON-RPC streaming protocol."""
    logger.info("Starting A2A chat stream test")

    # Define an async function to use the A2A SDK client
    async def _stream() -> list[StreamResponse]:
        # Configure client with streaming enabled and a 60-second timeout
        config = ClientConfig(
            streaming=True,
            httpx_client=httpx.AsyncClient(timeout=60.0),
        )
        # Connect to the agent's A2A RPC endpoint
        client = await create_client(A2A_RPC_URL.rstrip("/"), config)
        
        # Build standard A2A Message data structure
        message = Message(
            message_id=f"msg-user-{uuid.uuid4()}",
            role=Role.ROLE_USER,
            parts=[Part(text="Hi!")],
        )
        
        # Send message and collect all streaming response chunks
        return [
            chunk
            async for chunk in client.send_message(SendMessageRequest(message=message))
        ]

    # Run the async coroutine to completion using asyncio.run()
    responses = asyncio.run(_stream())
    assert responses, "No responses received from stream"

    # Helper function to check if a response chunk signifies completion
    def _is_completed(chunk: StreamResponse) -> bool:
        if chunk.HasField("status_update"):
            return chunk.status_update.status.state == TaskState.TASK_STATE_COMPLETED
        if chunk.HasField("task"):
            return chunk.task.status.state == TaskState.TASK_STATE_COMPLETED
        return False

    # Assert that the task completed successfully
    assert any(_is_completed(chunk) for chunk in responses), (
        "No completed task received from stream"
    )


# ------------------------------------------------------------------------------
# Test 3: A2A Agent Card Discovery Endpoint
# ------------------------------------------------------------------------------
def test_agent_card(server_fixture: subprocess.Popen[str]) -> None:
    """Test that the A2A agent card is served at the well-known URI."""
    # Fetch the Agent Card JSON document
    response = requests.get(AGENT_CARD_URL, timeout=10)
    assert response.status_code == 200, f"A2A endpoint returned {response.status_code}"

    served_agent_card = response.json()
    
    # Verify all essential schema fields are present in the served card
    for field in (
        "name",
        "description",
        "skills",
        "capabilities",
        "version",
        "supportedInterfaces",
    ):
        assert field in served_agent_card, f"Missing field in agent card: {field}"


# ------------------------------------------------------------------------------
# Test 4: Reasoning Engine Adapter (Async Streaming)
# ------------------------------------------------------------------------------
def test_reasoning_engine_stream(server_fixture: subprocess.Popen[str]) -> None:
    """The reasoning_engine adapter (/api/stream_reasoning_engine) runs the agent.

    This is the contract Vertex AI Agent Engine forwards :streamQuery calls to.
    """
    # Send a POST request calling `async_stream_query`
    response = requests.post(
        f"{BASE_URL}/api/stream_reasoning_engine",
        headers=HEADERS,
        json={
            "class_method": "async_stream_query",
            "input": {"user_id": f"u-{uuid.uuid4()}", "message": "Hi!"},
        },
        stream=True,
        timeout=60,
    )
    assert response.status_code == 200

    # Parse newline-delimited JSON chunks
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events, "No events from reasoning_engine adapter"
    
    # Verify that at least one event contains text content
    has_text = any(
        (event.get("content") or {}).get("parts")
        and any(part.get("text") for part in event["content"]["parts"])
        for event in events
    )
    assert has_text, "No text content in reasoning_engine events"


# ------------------------------------------------------------------------------
# Test 5: Reasoning Engine Adapter (Sync Generator Streaming)
# ------------------------------------------------------------------------------
def test_reasoning_engine_sync_stream(server_fixture: subprocess.Popen[str]) -> None:
    """The reasoning_engine adapter supports sync generators via stream_query."""
    # Send a POST request calling `stream_query` (synchronous generator variant)
    response = requests.post(
        f"{BASE_URL}/api/stream_reasoning_engine",
        headers=HEADERS,
        json={
            "class_method": "stream_query",
            "input": {"user_id": f"u-{uuid.uuid4()}", "message": "Hi!"},
        },
        stream=True,
        timeout=60,
    )
    assert response.status_code == 200

    # Parse newline-delimited JSON chunks
    events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    assert events, "No events from reasoning_engine adapter"
    
    # Verify that at least one event contains text content
    has_text = any(
        (event.get("content") or {}).get("parts")
        and any(part.get("text") for part in event["content"]["parts"])
        for event in events
    )
    assert has_text, "No text content in reasoning_engine sync events"
