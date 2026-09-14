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
Unit Tests Module (`tests/unit/test_dummy.py`)
==============================================
This module serves as the starting template for writing **unit tests** in your agent project.

What is Unit Testing in Agent Development? (Novice Guide):
----------------------------------------------------------
1. **What is a Unit Test?**
   - A unit test verifies that a small, isolated piece of code ("unit") works exactly as expected.
   - Unlike integration tests or end-to-end tests, unit tests should NOT call real external APIs,
     spin up servers, or invoke expensive LLM model endpoints.

2. **What should you unit test in an AI Agent project?**
   - **Custom Tools:** Test the Python functions your agent calls (e.g., test `get_weather("sf")`
     or `get_current_time("sf")` directly to ensure return values, regexes, and edge cases work).
   - **Data Parsers & Formatters:** Test that incoming user input or tool results are formatted cleanly.
   - **Prompt Template Builders:** Test that strings, prompt variables, and instructions are assembled correctly.

3. **How does `pytest` work?**
   - When you run `pytest` in your terminal, it automatically searches your project for files
     named `test_*.py` or `*_test.py`.
   - Inside those files, it looks for functions prefixed with `test_` and executes them.
   - If any `assert` statement fails (evaluates to False), pytest records the test as a failure.
"""


def test_dummy() -> None:
    """Placeholder unit test demonstration.

    In Python, the `assert` keyword tests if a condition is True.
    If `1 == 1` is True, nothing happens and the test passes.
    If the expression were False, Python raises an `AssertionError` and the test fails.

    How to expand this for real agent development:
    ----------------------------------------------
    You can import tools from `app.agent` and test them directly:
        from app.agent import get_weather, get_current_time

        def test_weather_tool():
            result = get_weather("San Francisco")
            assert "foggy" in result

        def test_time_tool_unknown_city():
            result = get_current_time("Atlantis")
            assert "Sorry" in result
    """
    # Simple assertion that always evaluates to True to verify the pytest runner is functional
    assert 1 == 1
