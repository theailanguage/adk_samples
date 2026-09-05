# Credit Card Approval Workflow (ADK v2)

A production-grade, graph-based credit card approval workflow built using the **Google Agent Development Kit (ADK) v2** (`google-adk==2.1.0`). 

This project integrates deterministic programmatic validation rules, Human-in-the-Loop (HITL) manual consent gathering, database mocks, and AI-powered reasoning using Gemini models (`gemini-2.5-flash`) into a single resilient graph topology.

---

## 🚀 Environment Setup & Run Instructions

Follow these steps to set up your environment and launch the workflow in the interactive ADK Web interface:

### 1. Configure Your Gemini API Key
Configure your Gemini API key in your terminal session before launching the application:

* **Linux / macOS:**
  ```bash
  export GEMINI_API_KEY="your-gemini-api-key"
  ```
* **Windows (Command Prompt):**
  ```cmd
  set GEMINI_API_KEY="your-gemini-api-key"
  ```
* **Windows (PowerShell):**
  ```powershell
  $env:GEMINI_API_KEY="your-gemini-api-key"
  ```

### 2. Initialize and Activate Virtual Environment
We recommend using [`uv`](https://docs.astral.sh/uv/) for high-performance dependency management:

```bash
# Create an isolated virtual environment
uv venv

# Activate the virtual environment:
# Linux / macOS:
source .venv/bin/activate

# Windows (Command Prompt):
.venv\Scripts\activate.bat

# Windows (PowerShell):
.venv\Scripts\Activate.ps1
```

### 3. Install Dependencies
Install the required pinned dependencies:
```bash
uv add -r requirements.txt
```
*(Alternatively, with virtual environment activated: `pip install -r requirements.txt`)*

### 4. Run the Workflow with `adk web ./agents`
Run the ADK Web UI development server pointing to the `./agents` directory:

```bash
uv run adk web ./agents
```
*(Or if your virtual environment is activated: `adk web ./agents`)*

#### Understanding the Path Syntax (`./agents`):
- `adk web` accepts an `AGENTS_DIR` argument, which points to the parent folder containing your agent packages.
- Supplying `./agents` tells ADK to scan the `./agents` folder for agent packages.
- ADK automatically discovers the `credit_card_workflow` package, loads the exported `root_agent` and `app` from `agents/credit_card_workflow/__init__.py` (or `agent.py`), and serves the application.

> **Note for Windows Users:** If you experience any asyncio subprocess issues during hot reloading, you can run with `--no-reload`:
> ```bash
> uv run adk web --no-reload ./agents
> ```

### 5. Access and Test via Browser
1. Open your browser and navigate to:
   ```
   http://127.0.0.1:8000
   ```
2. In the top-left dropdown menu, select **`credit_card_workflow`**.
3. Start the workflow by sending a message such as:
   ```text
   I want to apply for a credit card and my customer ID is 12345
   ```
4. **Human-in-the-Loop (HITL) Interaction:**
   - If the retrieved customer balance falls in the **gray area ($5,000 – $20,000)**, the workflow triggers an interrupt asking for your consent to pull your credit report.
   - Reply directly in the chat textbox with `yes` or `no`.
   - The engine resumes execution automatically, evaluates the underwriting risk with Gemini, and outputs the final approval or rejection decision.

---

## 📂 Project Structure & Code Organization

The workspace is organized into modular packages:

```text
.
├── agents/
│   ├── __init__.py
│   └── credit_card_workflow/
│       ├── __init__.py     # Exports root_agent and app for ADK discovery
│       ├── agent.py        # Core graph definition, Workflow topology, and App container
│       ├── instruction.txt # System prompt guiding the LLM Underwriter Agent
│       ├── tools.py        # Programmatic nodes, routing steps, and HITL interrupt functions
│       └── types.py        # Structured Pydantic schemas (AnalysisResult definition)
├── requirements.txt        # Pinned dependencies (google-adk==2.1.0, pydantic>=2.0.0)
├── ATTRIBUTION.md          # Open-source framework attributions (Google ADK & MCP)
├── KNOWLEDGE_BASE.md       # Theoretical reference for core graph-based workflow concepts
└── LICENSE                 # Project licensing terms
```

### Architectural Breakdown:
* **`types.py`**: Defines structured output schemas using Pydantic (`AnalysisResult` defining `approved` and `reason`). This enforces deterministic types when processing unstructured inputs through LLM nodes.
* **`instruction.txt`**: Separates prompts from application code, defining the underwriting rubric for the AI Underwriter.
* **`tools.py`**: Houses the graph nodes. Includes programmatic tools (`fetch_customer_balance`, `check_balance`, `fetch_credit_history`), the HITL generator node (`get_consent`), and terminal routing handlers.
* **`agent.py`**: Declares `intake_agent` and `analyze_history`, constructs the graph using `Workflow(edges=[...])`, and wraps the topology inside an `App` configured with `ResumabilityConfig(is_resumable=True)` to support session resumption across pauses.

---

## 🔄 How the Workflow Executes Under the Hood

ADK v2 provides a graph-scheduling system:

```text
                  [START]
                     │
                     ▼
               [intake_agent] (Retrieves balance via customer ID)
                     │
                     ▼
              [check_balance]
             /       │       \
     (Reject)        │        (Approve)
       /             │             \
      ▼              ▼              ▼
[auto_rejected]  [get_consent]   [process_new_card]
                     │
                     ▼ (HITL Interruption & Resume)
              [fetch_credit_history]
                     │
                     ▼
              [analyze_history] (LLM Underwriter)
                     │
                     ▼
              [route_analysis]
                /          \
        (Approve)          (Reject)
              /              \
             ▼                ▼
      [process_new_card]  [auto_rejected]
```

### 1. State-Driven Graph Traversal
Nodes are connected by edges. The ADK scheduler starts at `START` and executes the initial agent (`intake_agent`), which calls `fetch_customer_balance` to retrieve the balance into session state. It then transitions to `check_balance`.

Nodes emit routing strings (such as `approved`, `rejected`, or `gray_area`). ADK matches these strings with **routing dictionaries** defined in the edges:
```python
(check_balance, {
    "rejected": auto_rejected,
    "approved": process_new_card,
    "gray_area": get_consent,
})
```
This triggers conditional routing without hardcoding routing logic inside the functions themselves.

### 2. State Mutation & Checkpoints
Every node receives context variables and can emit events updating the session's shared state (e.g., `state={"balance": balance}`). When wrapped inside `App(resumability_config=ResumabilityConfig(is_resumable=True))`, ADK persists every transaction state change to the session store.

### 3. Human-in-the-Loop (HITL) and Resumption
When the workflow hits the `get_consent` node (because the balance is in the "gray area" of $5,000–$20,000), it executes a pause and resume lifecycle:
* **The Yield (Interrupt)**: If no resume input is found in `ctx.resume_inputs`, the node yields a `RequestInput` object detailing a unique `interrupt_id` (`consent_interrupt`) and a prompt. This stops the workflow runner immediately and creates a session checkpoint.
* **The Interception**: The ADK Web UI displays the consent prompt to the user.
* **The Resume**: When the user types `yes` or `no`, the UI packages the response.
* **The Re-Run**: Because `@node(rerun_on_resume=True)` is enabled, ADK re-executes `get_consent`. The node reads `ctx.resume_inputs["consent_interrupt"]`, inspects the consent choice, yields `route="consent_granted"` or `route="consent_denied"`, and proceeds down the graph.

---

## 📄 Open Source Attributions & License

* For framework and trademark licensing disclosures regarding Google ADK and MCP, please review [ATTRIBUTION.md](ATTRIBUTION.md).
* For terms of use and repository access rules, please review [LICENSE](LICENSE).
