"""Types and schemas for the Credit Card Approval Workflow.

This module defines the structured data contracts (schemas) used across the workflow.
In agentic applications built with the Google Agent Development Kit (ADK v2),
Large Language Models (LLMs) often need to output structured data rather than free-form
conversational text.

By using Pydantic models as an `output_schema` on an `Agent`:
1. Gemini is instructed to respond strictly in valid JSON adhering to this schema.
2. ADK automatically parses and validates the model's response into a Python object.
3. Downstream workflow nodes receive strongly-typed objects with autocomplete,
   type hints, and guaranteed attribute availability, preventing runtime errors.
"""

from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    """Structured response schema returned by the Credit Risk Underwriter LLM agent.

    This Pydantic model acts as the data transfer contract between the AI Underwriter
    node (`analyze_history`) and the downstream routing node (`route_analysis`).

    Instead of writing fragile regex or string searching to extract whether an LLM
    approved or rejected an application, this schema guarantees that the LLM provides:
    - A strict boolean flag (`approved`) for programmatic conditional routing.
    - A qualitative explanation (`reason`) for human auditing and user transparency.

    Attributes:
        approved (bool): The underwriting verdict.
            - True indicates the applicant meets credit risk standards.
            - False indicates the applicant is rejected due to credit risk factors.
        reason (str): A clear explanation articulating why the underwriting decision
            was made, referencing specific credit criteria (score, late payments, etc.).
    """

    # Field descriptions are converted into JSON schema descriptions in the Gemini prompt.
    # The LLM reads these descriptions to understand what values are expected.
    approved: bool = Field(
        description="True if the credit history shows strong financial responsibility, False otherwise."
    )
    reason: str = Field(
        description="A brief qualitative explanation for the underwriting decision."
    )
