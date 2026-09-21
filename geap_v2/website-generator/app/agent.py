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
import gzip
import hashlib
import requests
import google.auth
from google.auth.transport.requests import Request

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
    # Create the "public" directory inside our temporary deployment folder.
    # Firebase Hosting requires all static assets to be served from a specific directory,
    # which is traditionally named "public".
    public_dir = os.path.join(DEPLOY_DIR, "public")
    
    # exist_ok=True ensures we don't throw an error if the directory already exists
    # from a previous tool call during this conversation session.
    os.makedirs(public_dir, exist_ok=True)
    
    # Write the raw HTML generated by the LLM into index.html
    # This acts as the entry point for the static website.
    with open(os.path.join(public_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(html_content)
        
    # Generate the minimal firebase.json configuration file required by the Firebase CLI.
    # This tells the CLI that the "public" folder contains the static assets to upload.
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
    
    # Save the configuration file in the root of the deployment directory.
    # When we run `firebase deploy` later, it will look for this file to understand the project layout.
    with open(os.path.join(DEPLOY_DIR, "firebase.json"), "w", encoding="utf-8") as f:
        json.dump(firebase_config, f, indent=2)
        
    # Returning a descriptive string to the LLM so it knows the step was successful
    # and what it should do next (call deploy_saved_website).
    return f"Website content saved successfully to {DEPLOY_DIR}. You can now call deploy_saved_website."


def deploy_saved_website() -> str:
    """Deploys the previously saved website to Firebase Hosting Preview Channels."""
    # Safety check: ensure the LLM didn't skip the save_website_content step.
    if not os.path.exists(DEPLOY_DIR):
        return "Error: No website content found. Please call save_website_content first."
        
    try:
        env = os.environ.copy()
        # Suppress strict Node engine checks which can cause warnings/failures with older packages
        env["npm_config_engine_strict"] = "false"
        
        # ----------------------------------------------------------------------
        # Project Discovery
        # ----------------------------------------------------------------------
        # Fetch the active Google Cloud project ID to pass to the Firebase CLI.
        # 1. First, check standard serverless environment variables used by Cloud Run/Functions.
        gcloud_proj = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
        
        # 2. If not found in env vars, fallback to checking the local gcloud CLI config.
        if not gcloud_proj:
            try:
                gcloud_proj = subprocess.run(
                    ["gcloud", "config", "get-value", "project"], 
                    capture_output=True, text=True, check=True
                ).stdout.strip()
            except Exception:
                gcloud_proj = None
            
        # ----------------------------------------------------------------------
        # CLI Execution
        # ----------------------------------------------------------------------
        # We use `npx -y` to execute the latest firebase-tools CLI directly without requiring a global install.
        # `hosting:channel:deploy ai-generated-preview` deploys the site to a temporary preview URL instead of production.
        cmd = ["npx", "-y", "firebase-tools@latest", "hosting:channel:deploy", "ai-generated-preview", "--expires", "30m", "--non-interactive"]
        if gcloud_proj:
            cmd.extend(["--project", gcloud_proj])
            
        # Execute the deployment command inside the directory where we saved firebase.json and public/index.html
        result = subprocess.run(
            cmd,
            cwd=DEPLOY_DIR,
            env=env,
            capture_output=True,
            text=True,
            check=True
        )
        
        # Print output to the backend console for developer observability
        print("Firebase Deploy Output:\n", result.stdout)
        
        # Return the output to the LLM so it can parse the live URL and share it with the user
        return f"Successfully deployed! Output:\n{result.stdout}"
    except subprocess.CalledProcessError as e:
        # If the CLI returns a non-zero exit code, capture the stdout/stderr and return it to the LLM
        # This allows the LLM to potentially debug the issue and try again.
        print("Firebase Deploy Failed!\nSTDOUT:\n", e.stdout, "\nSTDERR:\n", e.stderr)
        return f"Failed to deploy.\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}"


def deploy_website_unified(html_content: str) -> str:
    """Saves the generated HTML content and deploys it to Firebase Hosting in a single step.
    
    Args:
        html_content: The unified HTML, CSS, and JS content.
    """
    try:
        # ----------------------------------------------------------------------
        # 1. Project Identity and Authentication setup
        # ----------------------------------------------------------------------
        # Fetch the active project to pass to the Firebase REST API.
        gcloud_proj = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
        
        if not gcloud_proj:
            try:
                gcloud_proj = subprocess.run(
                    ["gcloud", "config", "get-value", "project"], 
                    capture_output=True, text=True, check=True
                ).stdout.strip()
            except Exception:
                gcloud_proj = None
                
        if not gcloud_proj:
            return "Failed to deploy: Could not determine Google Cloud project."
            
        # Instead of relying on the Firebase CLI (which struggles with headless auth in Cloud Run),
        # we directly request an OAuth2 access token from the Agent Runtime metadata server.
        credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(Request())
        token = credentials.token
        
        # This authorization header will be attached to every REST API call below
        headers = {"Authorization": f"Bearer {token}"}
        
        # ----------------------------------------------------------------------
        # 2. File Preparation (Hashing and Compression)
        # ----------------------------------------------------------------------
        # The Firebase Hosting API requires us to declare the exact SHA256 hashes of the files
        # BEFORE we upload them, so it can tell us if it already has them cached globally.
        html_bytes = html_content.encode('utf-8')
        
        # Firebase expects the hashes to be calculated on the GZIPPED version of the file.
        gzipped_bytes = gzip.compress(html_bytes)
        file_hash = hashlib.sha256(gzipped_bytes).hexdigest()
        
        # ----------------------------------------------------------------------
        # 3. Deployment Flow via Firebase Hosting REST API
        # ----------------------------------------------------------------------
        
        # Step A: Create a new Version for the site.
        # A Version represents a specific deployment payload. We define a Cache-Control 
        # header of 0 here so the AI-generated site refreshes immediately without CDN caching.
        res = requests.post(
            f"https://firebasehosting.googleapis.com/v1beta1/sites/{gcloud_proj}/versions",
            headers=headers,
            json={"config": {"headers": [{"glob": "**", "headers": {"Cache-Control": "max-age=0"}}]}}
        )
        res.raise_for_status()
        version_name = res.json()["name"]
        
        # Step B: Populate Files.
        # We tell Firebase "Here are the files I want in this version, and their hashes".
        res = requests.post(
            f"https://firebasehosting.googleapis.com/v1beta1/{version_name}:populateFiles",
            headers=headers,
            json={"files": {"/index.html": file_hash}}
        )
        res.raise_for_status()
        pop_data = res.json()
        upload_url = pop_data.get("uploadUrl")
        
        # Firebase responds with an array of hashes that it doesn't already have.
        required_hashes = pop_data.get("uploadRequiredHashes", [])
        
        # Step C: Upload any missing files.
        # If this exact HTML file hasn't been uploaded before, we POST the raw gzipped bytes
        # to the dedicated high-speed upload endpoint.
        if file_hash in required_hashes:
            res = requests.post(
                f"{upload_url}/{file_hash}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"},
                data=gzipped_bytes
            )
            res.raise_for_status()
            
        # Step D: Finalize the Version.
        # This locks the version, indicating all required files have been successfully uploaded.
        res = requests.patch(
            f"https://firebasehosting.googleapis.com/v1beta1/{version_name}?updateMask=status",
            headers=headers,
            json={"status": "FINALIZED"}
        )
        res.raise_for_status()
        
        # Step E: Prepare the Preview Channel.
        # We define a preview channel named 'ai-generated-preview' with a 30-minute TTL (1800s).
        channel_id = "ai-generated-preview"
        channel_url = f"https://firebasehosting.googleapis.com/v1beta1/sites/{gcloud_proj}/channels/{channel_id}"
        
        # We use PATCH with updateMask=ttl to create the channel or extend its expiration if it already exists.
        res = requests.patch(
            f"{channel_url}?updateMask=ttl",
            headers=headers,
            json={"ttl": "1800s"}
        )
        res.raise_for_status()
        
        # The channel response gives us the preview URL.
        channel_data = res.json()
        preview_url = channel_data.get("url", f"https://{gcloud_proj}--{channel_id}.web.app")
        
        # Step F: Release the Version to the Preview Channel.
        # This points the preview URL to our newly finalized version.
        res = requests.post(
            f"{channel_url}/releases",
            headers=headers,
            params={"versionName": version_name}
        )
        res.raise_for_status()
        
        # Return the final deployed preview URL to the LLM so it can display it to the user.
        return f"Successfully deployed to preview channel! Website is live at: {preview_url} (Expires in 30 minutes)"
        
    except requests.exceptions.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            error_msg += f"\nResponse details: {e.response.text}"
        print(f"Firebase REST API Deploy Failed: {error_msg}")
        return f"Failed to deploy via Firebase REST API:\n{error_msg}"
    except Exception as e:
        print(f"Deployment failed with exception: {str(e)}")
        return f"Failed to deploy due to exception: {str(e)}"


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
        "and then use `deploy_saved_website` to execute the deployment. If explicitly instructed to use the unified tool, use `deploy_website_unified` instead."
    ),
    
    # `tools`: A list of Python functions the agent is allowed to invoke.
    # The ADK automatically parses their signatures and docstrings, exposes them to Gemini,
    # and handles executing them when Gemini requests a function call.
    tools=[save_website_content, deploy_saved_website, deploy_website_unified],
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
