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
LLM-as-a-Judge Evaluation Module (`tests/eval/response_quality.py`)
=================================================================
This file implements an automated quality evaluator for our AI agent.

What is "LLM-as-a-Judge" and Agent Evaluation? (Novice Guide):
--------------------------------------------------------------
1. **The Challenge of Testing Generative AI:**
   - In traditional software, `assert add(2, 2) == 4` is straightforward.
   - But AI agents answer in natural language, and phrasing varies each time.
   - How can you automatically tell if an agent's answer is accurate, helpful, and polite?

2. **The LLM-as-a-Judge Pattern:**
   - We prompt a powerful, impartial language model (like Gemini) to act as a judge.
   - We give the judge:
     a) A clear evaluation **rubric** (e.g., 1-5 rating scale).
     b) The user's input **prompt**.
     c) The agent's generated **response**.
     d) The full **agent execution trace** (including tool calls and outputs).
     e) An optional "ground truth" **reference answer** to penalize factual errors.

3. **Structured Outputs with Pydantic:**
   - Instead of asking the judge model for unstructured text, we enforce a strict schema
     using a Pydantic `BaseModel` (`_Verdict`).
   - Gemini guarantees that its output will conform to the `{ "score": int, "explanation": str }` format!
"""

# ------------------------------------------------------------------------------
# Standard Library Imports
# ------------------------------------------------------------------------------
# `threading` provides threading primitives.
# We use `threading.local()` to store per-thread state.
import threading

# ------------------------------------------------------------------------------
# Third-Party & Google GenAI Imports
# ------------------------------------------------------------------------------
# `google.genai` is the official, unified Google GenAI SDK for Gemini models.
from google import genai

# `types` provides configuration classes like `GenerateContentConfig`.
from google.genai import types

# `BaseModel` from Pydantic allows defining data validation models and schemas.
from pydantic import BaseModel

# ------------------------------------------------------------------------------
# Thread-Local Storage for GenAI Clients
# ------------------------------------------------------------------------------
# `threading.local()` creates a thread-isolated storage object.
# Attributes assigned to `_local` inside one thread are invisible to other threads.
_local = threading.local()


# ------------------------------------------------------------------------------
# Evaluation Verdict Schema
# ------------------------------------------------------------------------------
# By inheriting from Pydantic's `BaseModel`, we define the exact JSON structure
# we want Gemini to return when grading an agent's response.
class _Verdict(BaseModel):
    """Pydantic schema representing the judge model's evaluation."""
    score: int        # Numerical score from 1 (poor) to 5 (excellent)
    explanation: str  # Detailed textual reasoning behind why this score was assigned


# ------------------------------------------------------------------------------
# GenAI Client Provider (Per-Thread Singleton)
# ------------------------------------------------------------------------------
def _client() -> genai.Client:
    """Provides one `genai.Client` per grading thread.

    Why do this?
      - The evaluation runner executes test cases across multiple parallel worker threads.
      - Initializing a client per thread reuses connections (saving TLS handshakes and ADC token lookups).
      - `google-auth` freezes the SSL context on the first connection when client certificates exist,
        so each thread needs its own independent client to prevent SSL race conditions.
    """
    client = getattr(_local, "client", None)
    if client is None:
        # Automatically detects credentials from Google Application Default Credentials (ADC)
        # or the `GEMINI_API_KEY` environment variable.
        client = _local.client = genai.Client()
    return client


# ------------------------------------------------------------------------------
# Evaluation Entrypoint
# ------------------------------------------------------------------------------
def evaluate(instance: dict) -> dict:
    """Evaluates a single agent execution instance and returns a score with an explanation.

    Args:
        instance: A dictionary provided by the eval framework containing:
          - "prompt": The question or instruction sent to the agent.
          - "response": The agent's final text answer.
          - "reference": (Optional) Ground truth answer.
          - "agent_data": Full agent execution trace (intermediate steps, tool calls).

    Returns:
        A dictionary: {"score": int (1-5), "explanation": str}
    """
    # Extract ground truth reference answer if one was provided in the eval dataset
    reference = instance.get("reference")
    
    # Define the grading rubric for the judge model
    rubric = (
        "Grade the agent's final response on a 1-5 scale (1 poor, 5 excellent) for "
        "accuracy, relevance, and clarity."
    )
    if reference:
        rubric += (
            " The response should agree with the expected answer below; penalize "
            "factual disagreement with it."
        )
        
    # Construct the evaluation prompt for Gemini
    prompt = (
        f"You are an expert QA evaluator for an enterprise AI assistant. {rubric}\n"
        f"User Prompt: {instance.get('prompt', '')}\n"
        f"Final Response: {instance.get('response', '')}\n"
    )
    if reference:
        prompt += f"Expected Answer (ground truth): {reference}\n"
    prompt += f"Full Agent Trace: {instance.get('agent_data', '')}\n"

    # Call Gemini to grade the response
    response = _client().models.generate_content(
        model="gemini-3.7-flash",  # Fast, highly accurate grading model
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,             # Temperature 0 makes the grading strictly deterministic and consistent
            response_mime_type="application/json",  # Instructs model to return pure JSON
            response_schema=_Verdict,  # Enforces that JSON matches our `_Verdict` Pydantic class
        ),
    )
    
    # The GenAI SDK automatically parses JSON matching the schema into the Pydantic instance
    verdict = response.parsed
    
    # If the model returned an invalid or empty response, return 0 with raw text
    if verdict is None:
        return {"score": 0, "explanation": response.text or ""}
        
    # Clamp score between 1 and 5 and return the result dictionary
    return {"score": max(1, min(5, verdict.score)), "explanation": verdict.explanation}
