"""Credit Card Approval Workflow package using Google Agent Development Kit (ADK v2).

This file marks the directory as a Python package and defines the public exports
used by the ADK framework for automatic discovery.

How ADK Package Discovery Works:
--------------------------------
When you execute the ADK CLI command:
    `adk web ./agents`

1. ADK scans the target folder (`./agents`) for Python packages (subdirectories
   containing an `__init__.py`).
2. Inside each package, ADK inspects `__init__.py` or `agent.py` looking for standard
   entry points:
   - `app`: An instance of `google.adk.apps.App`, which encapsulates the workflow,
     session management, and resumability configuration (required for HITL pause/resume).
   - `root_agent`: The primary `Workflow` or `Agent` representing the entry graph.
3. If an `app` is exported, ADK uses it to configure session storage, resumability,
   and interactive UI routing. If only `root_agent` is found, ADK wraps it in a default app.

By explicitly importing and exposing `app` and `root_agent` in `__all__`, we ensure
seamless discovery and initialization across ADK tools and servers.
"""

from .agent import app, root_agent

__all__ = ["root_agent", "app"]
