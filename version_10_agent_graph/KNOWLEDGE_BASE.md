# 🎓 Graph-Based Workflows with ADK v2: Core Concepts Reference

Welcome to graph-based workflow development in **Google Agent Development Kit (ADK) v2**! Modeling workflows as directed graphs allows you to compose complex logic, AI reasoning, and Human-in-the-Loop (HITL) checkpoints into robust, resilient, and stateful applications.

This educational guide is designed to explain the key theoretical concepts and Python syntax of ADK v2 by directly referencing patterns and structures from the credit card approval workflow in this repository.

---

## 🗺️ 1. What is a Node?

### Theory
In graph theory, a workflow is represented as a directed graph. The individual processing steps in this graph are called **Nodes**. 
* A node is a single unit of execution. It receives inputs (either from the previous node or from the context), performs some computation or business logic, and returns or yields an output.
* In ADK v2, any of the following can act as a node:
  1. **Standard Python Functions**: Best for deterministic logic, programmatic calculations, or fast filters.
  2. **Decorated Generators / Coroutines**: Using `@node(rerun_on_resume=...)` for asynchronous steps, yield-based streaming, or pausing for human interaction.
  3. **AI Agents (`Agent` instances)**: Powered by Gemini language models (`gemini-2.5-flash`), with specialized system instructions, tools, and output schemas.

### 💻 Syntax & Code Examples
Below are the three primary styles of nodes used in ADK v2, illustrated using our credit card approval workspace:

#### A. Standard Python Function Node
A simple Python function can be mapped directly to a node in a graph. It can accept parameters (which ADK injects from state or node input) and return an `Event` to propagate data.
```python
# Defined in agents/credit_card_workflow/tools.py
def check_balance(balance: int) -> Event:
    """A deterministic programmatic node acting as a quick gatekeeper."""
    if balance < 5000:
        return Event(
            route="rejected",
            state={"balance": balance},
            message="Balance check failed: Auto-rejecting application."
        )
    # ...
```

#### B. Decorated Generator Node (`@node`)
For advanced behaviors like async operations or Human-in-the-Loop interruptions, use the `@node` decorator. This turns your generator into a recognized, controllable workflow step.
```python
from google.adk.workflow import node
from typing import AsyncGenerator, Any

@node(rerun_on_resume=True)
async def get_consent(ctx: Context) -> AsyncGenerator[Any, None]:
    """A node that asks for human consent and waits to resume."""
    resume_input = ctx.resume_inputs.get("consent_interrupt")
    if not resume_input:
        # Pause the engine and request input
        yield RequestInput(
            interrupt_id="consent_interrupt",
            message="We need consent to pull credit history. Grant consent? (yes/no)",
        )
        return
    # ...
```

#### C. AI Agent Node (`Agent`)
You can treat full LLM agents as standard nodes in your graph. They ingest context, process instruction text, and yield structured schemas or plain responses.
```python
# Defined in agents/credit_card_workflow/agent.py
analyze_history = Agent(
    name="analyze_history",
    model="gemini-2.5-flash",
    instruction=instruction_text,
    output_schema=AnalysisResult, # Structured schema output
)
```

---

## ✉️ 2. What is an Event? (`google.adk.Event`)

### Theory
An **Event** is the core communication block in ADK. It represents a state transition, an output emission, or a user-facing dialogue turn. 
When a node runs, it communicates with the workflow engine by yielding or returning an `Event`. 

An `Event` packages four crucial attributes:
1. **`message` (or `content`)**: The user-facing markdown text that describes the action being taken or displays output to the user.
2. **`state`**: A dictionary containing variables that should be updated in the global session context.
3. **`route`**: A branch identifier (such as a string, integer, or boolean) instructing the graph scheduler on which edge/path to traverse next.
4. **`output`**: Plain Python datatypes (strings, integers, dicts, or Pydantic schemas) passed as the direct payload to the immediate next node.

### 💻 Syntax & Code Examples
Here is how you initialize and return an `Event` with different payload options:

```python
from google.adk import Event

# Example A: Updating shared state variables & outputting data to the next node
Event(
    state={"credit_score": 740, "credit_history": "Excellent payment history"},
    output="Raw credit history report text...",
    message="Fetched credit history successfully. Score: 740."
)

# Example B: Setting a branch route to control conditional execution
Event(
    route="consent_granted",
    state={"consent": True},
    message="Consent was granted. Proceeding to fetch credit records..."
)
```

---

## 🧠 3. What is Context? (`google.adk.Context`)

### Theory
The **Context** object (`google.adk.Context`) provides nodes access to the live execution environment of the session. It acts as the shared, persistent memory card of the active transaction. 

As a workflow developer, you will interact with two vital properties on the `Context`:
1. **`ctx.state`**: A mutable dictionary representing the global session state. State deltas emitted by previous `Event`s are merged into `ctx.state`. This dictionary is serialized, persisted, and hydrated across restarts and interruptions.
2. **`ctx.resume_inputs`**: A dictionary holding the resolved payloads when a workflow is resumed from an interrupt.

### 💻 Syntax & Code Examples

#### A. Reading and Writing Shared State
You can request the `Context` to be passed to standard tool functions simply by adding a `ctx: Context` parameter to the signature:
```python
from google.adk import Context

def fetch_customer_balance(customer_id: str, ctx: Context) -> str:
    """Reads input customer_id and mutates session state directly."""
    # Write to session memory
    ctx.state["customer_id"] = customer_id
    ctx.state["balance"] = 12500
    
    # Read from session memory
    current_user = ctx.state.get("user_id", "anonymous")
    return f"Retrieved balance for customer {customer_id} requested by {current_user}."
```

#### B. Reading Human-in-the-Loop Resumption Inputs
```python
async def get_consent(ctx: Context):
    # Check if a response to our interrupt is available in the context
    user_response = ctx.resume_inputs.get("consent_interrupt")
    if user_response:
        print(f"Resumed with input: {user_response}")
```

---

## ⏸️ 4. What is Resume on Re-run? (`rerun_on_resume=True`)

### Theory
When executing workflows that require Human-in-the-Loop (HITL) manual intervention (e.g., getting credit check consent), the system must **pause**, **checkpoint**, and later **resume** precisely where it left off.

To optimize performance, ADK v2 caches completed node results during a session. When you resume a workflow, the engine will skip nodes that have already finished. However, **the node that initiated the pause must be run again** to process the incoming human answer.

We configure this behavior using the `@node(rerun_on_resume=True)` decorator:
1. **Turn 1 (Pause Phase)**: The node executes. Since `ctx.resume_inputs` does not contain the answer yet, the node yields a `RequestInput` object. This immediately stops execution, checkpoints the state, and emits an interrupt to the runner.
2. **Turn 2 (Resume Phase)**: The user provides their response. The runner feeds this response back to the session using the same `interrupt_id`. Because `rerun_on_resume=True` is enabled, the workflow scheduler knows *not* to skip this node on re-run. Instead, it re-executes the node. The node detects the input under `ctx.resume_inputs`, processes the response, and continues down the graph!

### 💻 Syntax & Code Examples
Below is the classic workflow pause-and-resume implementation:

```python
from google.adk import Context, Event
from google.adk.events import RequestInput
from google.adk.workflow import node

@node(rerun_on_resume=True) # 🌟 Essential: Re-run this node when session resumes!
async def get_consent(ctx: Context) -> AsyncGenerator[Any, None]:
    # 1. Look for human feedback in the resumption dictionary
    resume_input = ctx.resume_inputs.get("consent_interrupt")

    # --- Turn 1: No reply yet -> Pause and Intercept ---
    if not resume_input:
        yield RequestInput(
            interrupt_id="consent_interrupt", # Must match the resumption block ID
            message="To proceed, please grant consent to pull your credit file. (yes/no)",
        )
        return # Execution halts here, session is checkpointed

    # --- Turn 2: User response is present -> Process & Branch ---
    consent_response = str(resume_input).strip().lower()
    if consent_response in ("yes", "y", "approve"):
        yield Event(route="consent_granted", state={"consent": True})
    else:
        yield Event(route="consent_denied", state={"consent": False})
```

---

## 🔀 5. How to Specify Routes (Branch Identifiers)

### Theory
A major advantage of graph-based workflows is the separation of **application logic** (the nodes) from **routing topology** (how nodes connect). Rather than calling a function directly inside another function, nodes simply output "route keys" and let the workflow container route the execution.

In ADK v2, you specify routing topology inside the `Workflow`'s `edges` parameter. 

### 💻 Syntax & Code Examples

#### A. Preferred Method: Dictionary Routing Maps
The most readable and idiomatic way to express routing in ADK v2 is by utilizing **dict syntax** as part of your edge list. This maps a node's returned route key to the target downstream node:

```python
from google.adk import Workflow

root_agent = Workflow(
    name="credit_card_approval_workflow",
    edges=[
        # 1. Standard Sequence (unconditional transitions)
        ("START", intake_agent),
        (intake_agent, check_balance),
        
        # 2. 🌟 Conditional Routing Dictionary 🌟
        (
            check_balance,
            {
                "rejected": auto_rejected,     # Run auto_rejected if route is "rejected"
                "approved": process_new_card,  # Run process_new_card if route is "approved"
                "gray_area": get_consent,      # Run get_consent if route is "gray_area"
            },
        ),
        
        # 3. Dynamic HITL branching
        (
            get_consent,
            {
                "consent_granted": fetch_credit_history,
                "consent_denied": handle_denied_consent,
            },
        ),
    ],
)
```

#### B. Fallback Routing (`__DEFAULT__`)
If you want to catch all unhandled or unmatched route strings from a node, you can use the special route string fallback `__DEFAULT__`:
```python
(
    check_balance,
    {
        "approved": process_new_card,
        "rejected": auto_rejected,
        "__DEFAULT__": fallback_review_node # Handles any route that doesn't match above keys
    }
)
```

#### C. Boolean Routing Maps
If your routing logic evaluates to truthy or falsy checks, you can route directly on boolean values:
```python
# Node returns: return Event(route=True) or Event(route=False)
(
    is_credit_approved,
    {
        True: process_new_card,
        False: auto_rejected,
    }
)
```

#### D. Integer Routing Maps
Great for menu lists or numeric state routers:
```python
# Node returns: return Event(route=2)
(
    menu_selection,
    {
        1: standard_support_flow,
        2: premium_support_flow,
        3: callback_request_flow,
    }
)
```

#### E. List of Routes (Match Any)
An edge can fire if it matches *any* route key in a given list. In this format, we use the 3-tuple syntax:
```python
# Underwriter fires on either the 'approved' or 'pre_approved' route
(analyze_history, process_new_card, ["approved", "pre_approved"])
```

---

## 🎯 Wrap-Up Checklist for Building Your Workflow
- [ ] **Define Nodes**: Make sure your programmatic logic functions return `Event`, and interactive logic uses async generators with `@node(rerun_on_resume=True)`.
- [ ] **State updates**: Let your nodes update shared data safely by returning `Event(state={"my_key": value})`.
- [ ] **Route Cleanly**: Map string, boolean, or integer routes inside your `edges` parameter to cleanly divide execution logic from network layout.
- [ ] **Verify Routing Coverage**: If a node has conditional routes, make sure all routes are mapped in your routing dictionary to prevent accidental or unhandled fallthroughs!
