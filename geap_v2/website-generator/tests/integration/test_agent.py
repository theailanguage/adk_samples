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
Agent Integration Test Module (`tests/integration/test_agent.py`)
================================================================
This test verifies that the AI agent can execute end-to-end with the LLM and stream events.

What is an Integration Test in Agent Development? (Novice Guide):
-----------------------------------------------------------------
1. **Unit Test vs. Integration Test:**
   - A **unit test** tests an isolated function without calling external services.
   - An **integration test** tests how multiple components work TOGETHER. Here, it connects:
     - The `root_agent` definition (prompts & instructions)
     - The `Runner` execution engine
     - The `InMemorySessionService` memory store
     - The live `Gemini` model endpoint (sending a real prompt and receiving streamed response tokens)

2. **Why test streaming specifically?**
   - In modern agent apps, responses are streamed so users don't face long latency delays.
   - We must verify that:
     a) The model connection succeeds.
     b) The runner yields a sequence of event objects.
     c) At least one event contains valid generated text.
"""

# ------------------------------------------------------------------------------
# Google ADK Imports
# ------------------------------------------------------------------------------
# `RunConfig`: Configuration object passed to an agent execution run.
# `StreamingMode`: Enum specifying how streaming should be packaged (e.g., SSE for Server-Sent Events).
from google.adk.agents.run_config import RunConfig, StreamingMode

# `Runner`: The orchestration engine that executes an agent, handles LLM calls,
# executes tool invocations, and updates session histories.
from google.adk.runners import Runner

# `InMemorySessionService`: A session backend that stores chat history in memory (RAM).
# Perfect for tests because it requires no database or cloud infrastructure.
from google.adk.sessions import InMemorySessionService

# `types`: Provides data structures from Google GenAI SDK, including `Content` and `Part`.
from google.genai import types

# ------------------------------------------------------------------------------
# Agent Import
# ------------------------------------------------------------------------------
# Import the root agent configured in our application (`app/agent.py`).
from app.agent import root_agent


def test_agent_stream() -> None:
    """Integration test for the agent stream functionality.
    
    Walkthrough of what this test does:
      1. Initializes an in-memory session service to track conversational turns.
      2. Creates a new session for a test user.
      3. Builds a `Runner` connected to our `root_agent`.
      4. Crafts a user message: "Why is the sky blue?".
      5. Runs the agent with SSE streaming enabled and collects generated events.
      6. Asserts that valid text content was streamed back by Gemini.
    """
    # Step 1: Create a fresh in-memory session service instance
    session_service = InMemorySessionService()

    # Step 2: Create a conversation session for a dummy user named "test_user".
    # In ADK, every conversation belongs to a session ID within an application name.
    session = session_service.create_session_sync(user_id="test_user", app_name="test")

    # Step 3: Instantiate the ADK Runner to execute the agent.
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    # Step 4: Construct the incoming user message using Google GenAI SDK types.
    # A `Content` object contains a `role` ("user" or "model") and a list of `Part` objects
    # (which can be text, images, function calls, or function responses).
    message = types.Content(
        role="user", parts=[types.Part.from_text(text="Why is the sky blue?")]
    )

    # Step 5: Execute the agent run!
    # `runner.run()` is a generator that yields events as the agent reasons, calls tools,
    # and streams text back. Wrapping it in `list(...)` collects all emitted events into a list.
    events = list(
        runner.run(
            new_message=message,                                    # The user prompt
            user_id="test_user",                                    # User identifier
            session_id=session.id,                                  # Session identifier
            run_config=RunConfig(streaming_mode=StreamingMode.SSE), # Request Server-Sent Events mode
        )
    )

    # Step 6: Verify that the agent actually produced output events
    assert len(events) > 0, "Expected at least one message"

    # Step 7: Check that at least one event contains readable text from the LLM
    has_text_content = False
    for event in events:
        # Check if the event contains content, parts, and any part with non-empty text
        if (
            event.content
            and event.content.parts
            and any(part.text for part in event.content.parts)
        ):
            has_text_content = True
            break  # Found text content, exit loop early

    # Assert that readable text was successfully returned by the agent
    assert has_text_content, "Expected at least one message with text content"
