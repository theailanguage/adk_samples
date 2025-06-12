# =============================================================================
# FILE: agent.py
# PURPOSE:
#   This file defines the root LLM agent for the website builder use case.
#   The agent takes a user's natural language prompt describing a simple website,
#   generates a complete HTML+CSS+JS webpage, and uses a tool to save it as a file.
# =============================================================================

# Import the base class for a language-model-powered agent from Google ADK.
from google.adk.agents import LlmAgent

# Import the custom tool that handles writing content to a timestamped .html file.
from tools.file_writer_tool import write_to_file

# Import a utility function that reads instruction and description files from disk.
from utils.file_loader import load_instructions_file

# -----------------------------------------------------------------------------
# Define the root LLM agent for this app. It is a single-agent app (no sub-agents).
# -----------------------------------------------------------------------------
root_agent = LlmAgent(
    name="website_builder_simple",  # Unique name for the agent; also shown in the UI.

    model="gemini-2.0-flash-001",   # The ID of the Gemini model used to generate responses.

    # The prompt/instruction that tells the agent what kind of behavior to exhibit.
    # It is loaded from a file
    instruction=load_instructions_file("agents/website_builder_simple/instructions.txt"),

    # A short summary of what the agent does.
    # It is loaded from a file
    description=load_instructions_file("agents/website_builder_simple/description.txt"),

    # A list of tools the agent can invoke during execution.
    # In this case, just one: a function that writes the generated HTML to a file.
    tools=[write_to_file],
)