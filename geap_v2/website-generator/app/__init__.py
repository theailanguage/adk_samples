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
Package Initialization File (`app/__init__.py`)
===============================================
In Python, any directory containing a file named `__init__.py` is treated as a 
package. This allows other files to import modules from this folder (for example, 
`import app` or `from app import agent`).

In the Google Agent Development Kit (ADK) ecosystem:
----------------------------------------------------
When the ADK CLI or deployment tools look at your project directory, they look
for an initialized ADK application inside the `app` package. By exposing the `app` 
object here, we make the package self-contained and easily discoverable.
"""

# Relative import: The dot ('.') means "from the current package directory".
# We are importing the `app` variable (which is an instance of `google.adk.apps.App`)
# defined inside `app/agent.py`.
#
# What is `app`?
# In ADK, an `App` is the top-level container that bundles your root agent,
# its tools, and application configuration together into a runnable unit.
from .agent import app

# `__all__` is a special Python list of strings.
# It defines the public interface of this module.
# If someone writes: `from app import *`, Python will ONLY import the names listed in `__all__`.
# Here, it explicitly states that the primary export of this package is `app`.
__all__ = ["app"]
