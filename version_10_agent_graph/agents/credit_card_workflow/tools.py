"""Programmatic, HITL, and routing nodes for the Credit Card Approval Workflow.

In the Google Agent Development Kit (ADK v2), workflows are structured as directed
graphs composed of **Nodes** connected by **Edges**.

This file defines the node functions and tools that power the workflow:
1. **Tool Functions**: Called directly by LLM agents (e.g., `fetch_customer_balance`).
2. **Deterministic Filter Nodes**: Programmatic Python functions that evaluate rules
   and direct traffic using `Event(route=...)`.
3. **Human-In-The-Loop (HITL) Nodes**: Asynchronous generators decorated with
   `@node(rerun_on_resume=True)` that yield `RequestInput` to pause the workflow, wait
   for human feedback, and resume cleanly.
4. **Data Gathering Nodes**: Helper functions that prepare context and pass data
   downstream via `Event(output=...)`.
5. **Decision Routing & Terminal Nodes**: Nodes that finalize the approval or rejection
   and notify the user.
"""

import random
import re
from typing import Any, AsyncGenerator

from google.adk import Context, Event
from google.adk.events import RequestInput
from google.adk.workflow import node

from .types import AnalysisResult


# ==============================================================================
# TOOL FUNCTION: Customer Balance Retrieval
# ==============================================================================

def fetch_customer_balance(customer_id: str, ctx: Context) -> str:
    """Fetches the account balance for a given customer ID and stores it in session state.

    This function is registered as a **Tool** on the `intake_agent`. When a customer
    mentions their customer ID in conversation, the Gemini model recognizes this tool
    call, extracts the ID argument, and calls this function.

    How ADK State Injection Works:
    - The `ctx: Context` parameter is automatically detected and injected by ADK.
    - `ctx.state` is a persistent dictionary representing the session's shared memory.
    - Storing values in `ctx.state` makes them accessible to downstream graph nodes
      without needing to pass them explicitly through function arguments.

    Args:
        customer_id (str): The customer's unique identifier extracted by the LLM.
        ctx (Context): The ADK execution context holding session state and metadata.

    Returns:
        str: A conversational string response returned to the LLM agent, which
             acknowledges the balance retrieved.
    """
    # For demonstration purposes, we randomly choose between 3 realistic scenarios:
    # 1. $3,500  -> Below $5,000 threshold -> Triggers Path A (Auto-Rejection).
    # 2. $25,000 -> Exceeds $20,000 threshold -> Triggers Path B (Auto-Approval).
    # 3. $12,500 -> Gray Area ($5,000 - $20,000) -> Triggers Path C (HITL Consent).
    balances = [3500, 12500, 25000]
    selected_balance = random.choice(balances)

    # Persist the balance and customer ID into session state.
    # Any subsequent node with a parameter named `balance` or accessing `ctx.state["balance"]`
    # will be able to read this value.
    ctx.state["balance"] = selected_balance
    ctx.state["customer_id"] = customer_id

    return f"Retrieved balance of ${selected_balance:,.2f} for Customer ID {customer_id}."


# ==============================================================================
# STEP 1: Deterministic Filter (Fast Gatekeeper)
# ==============================================================================

def check_balance(balance: int) -> Event:
    """Step 1: Evaluates customer balance against business thresholds.

    This is a **Deterministic Programmatic Node**. Instead of invoking an expensive LLM
    call for simple rules, standard Python functions serve as fast, zero-cost gatekeepers.

    How ADK Automatic Parameter Injection Works:
    - Notice that `balance` is declared as an argument: `def check_balance(balance: int)`.
    - When ADK runs this node, it inspects the parameter name `balance`, finds
      `ctx.state["balance"]` (stored earlier by `fetch_customer_balance`), and automatically
      injects it!

    How Event Routing Works:
    - In ADK, nodes return an `Event` object.
    - The `route` argument (e.g., "rejected", "approved", "gray_area") tells the
      workflow engine which edge to take next in the graph definition.
    - The `state` argument updates or preserves values in the global session state.
    - The `message` argument provides status information visible in logs and the UI.

    Args:
        balance (int): The customer balance automatically injected from `ctx.state["balance"]`.

    Returns:
        Event: An ADK Event carrying the routing decision and status message.
    """
    # Threshold 1: Insufficient funds (< $5,000) -> Direct Auto-Rejection
    if balance < 5000:
        return Event(
            route="rejected",
            state={"balance": balance},
            message=f"Balance Check: ${balance:,.2f} is below the $5,000 threshold. Auto-Rejecting application."
        )
    # Threshold 2: High net worth (> $20,000) -> Instant Auto-Approval
    elif balance > 20000:
        return Event(
            route="approved",
            state={"balance": balance},
            message=f"Balance Check: ${balance:,.2f} exceeds the $20,000 threshold. Auto-Approving application."
        )
    # Threshold 3: Medium range ($5,000 - $20,000) -> Requires Credit Check & User Consent
    else:
        return Event(
            route="gray_area",
            state={"balance": balance},
            message=f"Balance Check: ${balance:,.2f} is in the Gray Area ($5k-$20k). Triggering Human-In-The-Loop Consent."
        )


# ==============================================================================
# STEP 2: Human-In-The-Loop (HITL) Consent Node
# ==============================================================================

@node(rerun_on_resume=True)
async def get_consent(ctx: Context) -> AsyncGenerator[Any, None]:
    """Step 2: Pauses execution to request user consent for a credit inquiry.

    Under FCRA and banking privacy regulations, pulling a customer's credit bureau
    report requires explicit affirmative consent.

    How the Human-In-The-Loop (HITL) Lifecycle Works in ADK v2:
    ----------------------------------------------------------
    1. `@node(rerun_on_resume=True)`:
       Normally, completed or interrupted nodes might be skipped on resume. This decorator
       explicitly instructs ADK to re-execute this generator when the workflow is resumed
       with user input.

    2. TURN 1 (Execution & Interruption):
       - The node checks `ctx.resume_inputs.get("consent_interrupt")`.
       - On the first run, no resume input exists (it is None).
       - The node yields a `RequestInput(interrupt_id="consent_interrupt", ...)`.
       - ADK intercepts this `RequestInput`, halts workflow progression, creates a state
         checkpoint in session storage, and renders the prompt in the UI for the user.
       - The function returns, and execution is completely paused.

    3. TURN 2 (Resumption & Evaluation):
       - The user types their reply in the web UI (e.g., "yes" or "no").
       - The ADK runner resumes the session and re-enters this node because
         `rerun_on_resume=True` was specified.
       - Now, `ctx.resume_inputs["consent_interrupt"]` contains the user's string answer!
       - The function parses the answer, yields an `Event` with route "consent_granted"
         or "consent_denied", and execution proceeds to the next graph node.

    Args:
        ctx (Context): The ADK execution context containing `resume_inputs` and `state`.

    Yields:
        RequestInput: On initial run, to pause execution and prompt the human.
        Event: On resume, with routing and state depending on whether consent was granted.
    """
    # Check if a response to our interrupt has been provided by the user
    resume_input = ctx.resume_inputs.get("consent_interrupt")

    # --- Turn 1: No user response yet -> Pause workflow execution ---
    if not resume_input:
        # RequestInput instructs the engine to suspend and wait for input with this interrupt_id
        yield RequestInput(
            interrupt_id="consent_interrupt",
            message="To proceed with your application, we need your consent to pull your credit history. Do you grant consent? (yes/no)",
        )
        return  # Stop execution here until resumed by user interaction

    # --- Turn 2: User response is available -> Parse reply and route ---
    consent_response = str(resume_input).strip().lower()
    # Accept standard affirmative answers
    consent_granted = consent_response in ("yes", "y", "approve", "approved", "grant")

    if consent_granted:
        # Route to fetch_credit_history
        yield Event(
            route="consent_granted",
            state={"consent": True},
            message="Consent granted! Fetching credit history..."
        )
    else:
        # Route to handle_denied_consent
        yield Event(
            route="consent_denied",
            state={"consent": False},
            message="Consent was denied. Ending application."
        )


# ==============================================================================
# STEP 3: Programmatic Data Gathering (Credit Bureau Mock)
# ==============================================================================

def fetch_credit_history(balance: int) -> Event:
    """Step 3: Simulates fetching the applicant's credit bureau profile.

    This node prepares the data required by the AI Risk Underwriter agent.

    Understanding `state` vs `output` in ADK Events:
    - `state={"credit_score": ..., "credit_history": ...}`:
      Persists these fields into the global session context (`ctx.state`). Any node
      in the session can read these at any point.
    - `output=history`:
      Supplies this exact object/string as direct input to the very next node in the
      workflow edge definition (`analyze_history`). When `analyze_history` runs, it
      receives this string as its user prompt/input to analyze.

    Args:
        balance (int): Customer balance automatically injected from `ctx.state["balance"]`.

    Returns:
        Event: An Event containing the mock credit report in both `state` and `output`.
    """
    # Deterministically construct a mock credit profile based on balance
    if balance > 15000:
        credit_score = 740
        history = (
            "Credit Score: 740 (Excellent).\n"
            "Active credit accounts: 4.\n"
            "On-time payments: 100%.\n"
            "Derogatory marks: 0.\n"
            "Recent hard inquiries: 0."
        )
    else:
        credit_score = 610
        history = (
            "Credit Score: 610 (Fair).\n"
            "Active credit accounts: 2.\n"
            "On-time payments: 88%.\n"
            "Derogatory marks: 1 (late payment 18 months ago).\n"
            "Recent hard inquiries: 3."
        )

    return Event(
        state={"credit_score": credit_score, "credit_history": history},
        output=history,  # Direct payload delivered to analyze_history LLM agent
        message=f"Credit history fetched successfully. Score: {credit_score}."
    )


# ==============================================================================
# STEP 4: AI Decision Routing Node
# ==============================================================================

def route_analysis(node_input: AnalysisResult) -> Event:
    """Step 4: Translates structured LLM output into graph routing events.

    How ADK passes agent outputs to downstream nodes:
    - The upstream agent `analyze_history` is configured with `output_schema=AnalysisResult`.
    - Gemini's JSON response is automatically deserialized by ADK into an `AnalysisResult`
      Pydantic instance.
    - ADK inspects `route_analysis`'s parameter `node_input: AnalysisResult` and injects
      that parsed object directly.
    - This function checks `node_input.approved` and returns an `Event` with the
      matching route ("approved" or "rejected"), completing the bridge between AI reasoning
      and deterministic graph branching.

    Args:
        node_input (AnalysisResult): The structured result from the underwriting agent.

    Returns:
        Event: Routing event leading either to card provisioning or rejection.
    """
    if node_input.approved:
        return Event(
            route="approved",
            message=f"AI Decision: Approved. Reason: {node_input.reason}"
        )
    else:
        return Event(
            route="rejected",
            message=f"AI Decision: Rejected. Reason: {node_input.reason}"
        )


# ==============================================================================
# STEP 5: Terminal Nodes (Workflow Outcomes)
# ==============================================================================

def process_new_card(balance: int) -> Event:
    """Terminal outcome: Approves application and provisions the new credit card.

    Args:
        balance (int): Injected from `ctx.state["balance"]` for confirmation messaging.

    Returns:
        Event: Confirmation event informing the customer of account creation.
    """
    return Event(
        message=f"Successfully minted account! Physical card is being mailed. (Reference Balance: ${balance:,.2f})"
    )


def auto_rejected() -> Event:
    """Terminal outcome: Rejects application based on credit risk or business rules.

    Returns:
        Event: Notification event informing the customer of the rejection.
    """
    return Event(
        message="Application closed: Application has been rejected based on credit requirements."
    )


def handle_denied_consent() -> Event:
    """Terminal outcome: Safely terminates workflow when the customer denies consent.

    Under compliance guidelines, if the applicant denies consent to check credit,
    the application must be cancelled without penalizing the customer.

    Returns:
        Event: Cancellation message indicating process stopped due to lack of consent.
    """
    return Event(
        message="Application closed: User did not grant consent to pull credit history."
    )
