# =============================================================================
# FILE: file_writer_tool.py
# PURPOSE:
#   This module defines a single tool function, `write_to_file`, which saves
#   the provided HTML/CSS/JS content to a timestamped HTML file inside an
#   output directory. This is used by agents to persist generated webpage content.
# =============================================================================

# Import the `datetime` module to generate a unique timestamp for the filename.
import datetime

# Import `Path` from `pathlib` for convenient and safe file/directory handling.
from pathlib import Path

# -----------------------------------------------------------------------------
# TOOL FUNCTION: write_to_file
# -----------------------------------------------------------------------------
def write_to_file(content: str) -> dict:
    """
    Writes the given HTML/CSS/JS content to a timestamped HTML file.

    Args:
        content (str): Full HTML content as a string to be saved to disk.

    Returns:
        dict: A dictionary containing the status and generated filename.
    """

    # Get the current date and time, format it as YYMMDD_HHMMSS.
    # Example: "250611_142317"
    timestamp = datetime.datetime.now().strftime("%y%m%d_%H%M%S")

    # Construct the output filename using the timestamp.
    # Example: "output/250611_142317_generated_page.html"
    filename = f"output/{timestamp}_generated_page.html"

    # Ensure the "output" directory exists. If it doesn’t, create it.
    # `exist_ok=True` prevents an error if the directory already exists.
    Path("output").mkdir(exist_ok=True)

    # Write the HTML content to the constructed file.
    # `encoding='utf-8'` ensures proper character encoding.
    Path(filename).write_text(content, encoding="utf-8")

    # Return a dictionary indicating success, and the filename that was written.
    return {
        "status": "success",
        "file": filename
    }