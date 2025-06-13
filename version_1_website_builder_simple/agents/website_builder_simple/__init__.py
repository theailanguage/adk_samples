# Import the `website_builder_simple` submodule from the current `agents` package.
# This triggers the execution of `agents/website_builder_simple/__init__.py`,
# which in turn typically loads or exposes the agent defined in `agent.py`.
from . import agent