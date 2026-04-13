# error_handling.py

DEBUG = False   # Set to True to enable debug logging


def debug_print(label, data):
    """Generic debug printer controlled by DEBUG flag."""
    if DEBUG:
        print(f"\n[DEBUG] {label}:")
        print(data)
        print()


def handle_api_error(data):
    """
    Handle API error responses from the Hugging Face API.
    Returns either:
    - "RETRY" for temporary errors (429, 503)
    - a friendly fallback message for all other errors
    """
    error = data.get("error", {})
    code = error.get("code")

    debug_print("Error code detected", code)

    # Temporary or rate-limit errors
    if code in [429, 503]:
        return "RETRY"

    # All other errors
    return "I'm having trouble understanding the request. Try rephrasing it."
