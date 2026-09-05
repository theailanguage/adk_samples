"""Agent and Workflow orchestration for the Credit Card Approval application.

In the Google Agent Development Kit (ADK v2), complex applications are composed
using three primary constructs:
1. **`Agent`**: An intelligent LLM entity (powered here by `gemini-2.5-flash`) equipped
   with prompt instructions, optional tool functions, and optional structured output schemas.
2. **`Workflow`**: A directed graph container that specifies the execution pipeline
   and routing logic via `edges`. Workflows coordinate both LLM agents and deterministic
   Python functions.
3. **`App`**: The top-level runtime application container that encapsulates the workflow,
   session storage, and resumability configuration (essential for Human-In-The-Loop pauses).
"""

import os

from google.adk import Agent, Workflow
from google.adk.apps import App
from google.adk.apps.app import ResumabilityConfig

from .tools import (
    auto_rejected,
    check_balance,
    fetch_credit_history,
    fetch_customer_balance,  # Tool called by the intake agent to look up customer data
    get_consent,
    handle_denied_consent,
    process_new_card,
    route_analysis,
)
from .types import AnalysisResult

# ==============================================================================
# PROMPT CONFIGURATION
# ==============================================================================
# Separating system prompts into external files (`instruction.txt`) keeps Python
# source code clean, facilitates prompt versioning, and makes prompt engineering easier.
current_dir = os.path.dirname(os.path.abspath(__file__))
instruction_path = os.path.join(current_dir, "instruction.txt")
with open(instruction_path, "r", encoding="utf-8") as f:
    instruction_text = f.read()


# ==============================================================================
# AGENT DEFINITIONS
# ==============================================================================

# 1. Customer Intake Agent
# ------------------------
# This conversational agent acts as the frontline customer representative.
# When a user submits an application message (e.g., "I want a card, my ID is 12345"),
# this agent parses the user's intent, extracts their customer ID, and executes the
# `fetch_customer_balance` tool.
#
# Key Features:
# - `name`: Unique identifier within the workflow graph.
# - `model`: "gemini-2.5-flash" provides high speed, low latency, and accurate tool calling.
# - `tools`: Registered Python functions that the model can choose to execute autonomously.
intake_agent = Agent(
    name="intake_agent",
    model="gemini-2.5-flash",
    instruction=(
        "You are the friendly Customer Intake Agent for the Credit Card Approval Workflow.\n"
        "Your sole task is to receive the customer's request to apply for a credit card. "
        "When the user mentions their Customer ID, you MUST call the `fetch_customer_balance` tool to retrieve their balance.\n"
        "Do not make up any numbers or balances. Once the tool returns the balance, acknowledge it and pass the flow over "
        "to the automated balance checking and risk evaluation system."
    ),
    tools=[fetch_customer_balance],
)

# 2. Credit Risk Underwriter Agent
# --------------------------------
# This agent acts as the expert financial underwriter. It evaluates raw credit bureau
# data received from `fetch_credit_history` against risk rubrics.
#
# Key Features:
# - `output_schema`: Enforces structured JSON output matching the Pydantic `AnalysisResult`
#   class (containing `approved: bool` and `reason: str`).
# - ADK automatically validates the model output and converts it to a typed Python object
#   before delivering it to downstream nodes.
analyze_history = Agent(
    name="analyze_history",
    model="gemini-2.5-flash",
    instruction=instruction_text,
    output_schema=AnalysisResult,  # Forces structured Pydantic response
)


# ==============================================================================
# WORKFLOW GRAPH TOPOLOGY
# ==============================================================================
# A `Workflow` connects nodes using directed `edges`.
# In ADK v2, an edge can be:
# - A 2-tuple `(A, B)`: Unconditional transition; when A completes, execute B.
# - A 3-tuple `(A, B, C)`: Sequential chain; executes A -> B -> C in sequence.
# - A branching dictionary `(A, {route_key: B, ...})`: Conditional transition;
#   when node A yields an `Event(route=route_key)`, execution branches to the matching node.

root_agent = Workflow(
    name="credit_card_approval_workflow",
    edges=[
        # ----------------------------------------------------------------------
        # ENTRY POINT:
        # ----------------------------------------------------------------------
        # "START" is the special ADK entry point constant. When an application run begins,
        # execution starts at `intake_agent`.
        ("START", intake_agent),

        # Once intake_agent fetches balance and acknowledges the customer,
        # proceed immediately to the deterministic balance checker.
        (intake_agent, check_balance),

        # ----------------------------------------------------------------------
        # STEP 1: Deterministic Filter Branching
        # ----------------------------------------------------------------------
        # `check_balance` evaluates the balance and yields an Event with route:
        # - "rejected"  -> Routes immediately to auto_rejected (balance < $5k)
        # - "approved"  -> Routes immediately to process_new_card (balance > $20k)
        # - "gray_area" -> Routes to get_consent for HITL review ($5k - $20k)
        (
            check_balance,
            {
                "rejected": auto_rejected,
                "approved": process_new_card,
                "gray_area": get_consent,
            },
        ),

        # ----------------------------------------------------------------------
        # STEP 2: Human-In-The-Loop (HITL) Consent Branching
        # ----------------------------------------------------------------------
        # `get_consent` pauses the workflow to ask the applicant for authorization.
        # Once resumed with the applicant's response:
        # - "consent_granted" -> Routes to fetch_credit_history
        # - "consent_denied"  -> Routes to handle_denied_consent (terminates cleanly)
        (
            get_consent,
            {
                "consent_granted": fetch_credit_history,
                "consent_denied": handle_denied_consent,
            },
        ),

        # ----------------------------------------------------------------------
        # STEPS 3 & 4: Linear Underwriting Chain
        # ----------------------------------------------------------------------
        # 1. `fetch_credit_history`: Pulls bureau data and emits Event(output=history).
        # 2. `analyze_history`: LLM Agent consumes `history`, evaluates risk, and outputs AnalysisResult.
        # 3. `route_analysis`: Inspects AnalysisResult and emits Event(route="approved"|"rejected").
        (fetch_credit_history, analyze_history, route_analysis),

        # ----------------------------------------------------------------------
        # STEP 5: Final Decision Branching
        # ----------------------------------------------------------------------
        # Routes the AI underwriter's decision to terminal action nodes:
        # - "approved" -> Provisions new credit card
        # - "rejected" -> Explains rejection and closes application
        (
            route_analysis,
            {
                "approved": process_new_card,
                "rejected": auto_rejected,
            },
        ),
    ],
)


# ==============================================================================
# APP CONTAINER & RESUMABILITY CONFIGURATION
# ==============================================================================
# In ADK v2, an `App` is the top-level deployment unit.
#
# Why `ResumabilityConfig(is_resumable=True)` is critical:
# - HITL workflows pause execution (via `RequestInput`) while waiting for human answers.
# - Without resumability, pausing would terminate the execution thread and lose session state.
# - Enabling `is_resumable=True` causes ADK to persist session state checkpoints. When the
#   user resumes the workflow with their answer, the runner rehydrates the session state
#   and seamlessly resumes execution from the paused node.
app = App(
    name="credit_card_workflow",
    root_agent=root_agent,
    resumability_config=ResumabilityConfig(is_resumable=True),
)
