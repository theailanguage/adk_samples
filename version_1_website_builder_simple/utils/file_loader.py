# =============================================================================
# FILE: file_loader.py
# PURPOSE:
#   Provides a utility function `load_instructions_file` that reads plain text
#   from a file — typically used to load prompt instructions or descriptions
#   for LLM agents. If the file is not found or unreadable, a default string is returned.
# =============================================================================

# Import the `os` module for working with file paths and environment context (not used here but common in loaders).
import os

# -----------------------------------------------------------------------------
# FUNCTION: load_instructions_file
# -----------------------------------------------------------------------------
def load_instructions_file(filename: str, default: str = "") -> str:
    """
    Loads instruction or description text from a given file path.

    Args:
        filename (str): Path to the file to read (relative or absolute).
        default (str): Default string to return if the file is not found or fails to load.

    Returns:
        str: The file contents if successful, or the fallback default string.
    """

    try:
        # Attempt to open the file in read mode with UTF-8 encoding.
        # This ensures support for non-ASCII characters in prompt files.
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()  # Read and return the entire contents of the file.

    except FileNotFoundError:
        # If the file doesn't exist, log a warning and fall back to the default value.
        print(f"[WARNING] File not found: {filename}. Using default.")

    except Exception as e:
        # Catch any other exception (e.g. permission issues, IO errors) and log it.
        print(f"[ERROR] Failed to load {filename}: {e}")

    # Return the fallback default string if anything goes wrong.
    return default