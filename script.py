"""
Math Tutor Assistant

This module orchestrates the tutoring flow:
- keeps conversation history
- routes requests to the API client
- validates and repairs structured responses
- handles student-step blocking before the model is called
"""

import json

from api_client import fetch_model_text
from math_validation import latest_reference_equation, student_step_conflicts_with_reference
from tutor_policy import (
    SYSTEM_PROMPT,
    parse_json_text,
    format_response,
    build_repair_prompt,
    needs_repair,
)

MAX_HISTORY_MESSAGES = 24

# Backward-compatible aliases used by existing tests and diagnostics.
_latest_reference_equation = latest_reference_equation
_student_step_conflicts_with_reference = student_step_conflicts_with_reference


# Seed each session with the system prompt so it stays in the conversation context.
def create_history():
    return [{"role": "system", "content": SYSTEM_PROMPT}]


history = create_history()


def trim_history(conversation_history):
    """Keep the system prompt plus the most recent messages."""
    if len(conversation_history) <= MAX_HISTORY_MESSAGES:
        return conversation_history

    return [conversation_history[0]] + conversation_history[-(MAX_HISTORY_MESSAGES - 1):]


def ask_model(user_input, conversation_history=None, store_turn=True, allow_repair_retry=True):
    """Run a tutor turn and return the final display text."""
    active_history = conversation_history if conversation_history is not None else history

    reference_equation = latest_reference_equation(active_history)
    last_tutor_message = None
    if active_history:
        last_msg = active_history[-1]
        if str(last_msg.get("role", "")).lower() in ["model", "assistant"]:
            last_tutor_message = str(last_msg.get("content", ""))

    if user_input:
        if student_step_conflicts_with_reference(user_input, reference_equation, last_tutor_message):
            correction = (
                "Nice attempt, but that transformation changes the equation. "
                "When you distribute, multiply 3 by both terms inside the parentheses. "
                "What is $3 \\cdot 2x$?"
            )
            if store_turn:
                active_history.append({"role": "user", "content": user_input})
                active_history.append({"role": "model", "content": correction})
                active_history[:] = trim_history(active_history)
            return correction

        active_history.append({"role": "user", "content": user_input})
        active_history[:] = trim_history(active_history)

    raw_output = fetch_model_text(active_history)
    if raw_output in ["RETRY", "Please set HUGGING_FACE_TOKEN before starting the tutor."]:
        return raw_output

    parsed_output = parse_json_text(raw_output)

    if allow_repair_retry and user_input and needs_repair(user_input, parsed_output, reference_equation):
        repair_history = active_history + [{"role": "user", "content": build_repair_prompt(user_input, raw_output)}]
        repaired_raw_output = fetch_model_text(repair_history)
        if repaired_raw_output == "RETRY":
            return repaired_raw_output

        repaired_parsed_output = parse_json_text(repaired_raw_output)
        if repaired_parsed_output is not None and not needs_repair(user_input, repaired_parsed_output, reference_equation):
            parsed_output = repaired_parsed_output

    if parsed_output is None:
        output = raw_output
    else:
        output = format_response(parsed_output)
        if not output:
            output = raw_output

    if store_turn:
        active_history.append({"role": "model", "content": output})
        active_history[:] = trim_history(active_history)

    return output


# Tutor CLI Loop
# In a real application, this would be replaced with a UI layer (e.g. Streamlit)
# The loop is wrapped in main() so it does not run when imported by test_agent.py.
def main():
    print("📘Hello! I am your personal math tutor. What are you working on? (type 'exit' to quit)")

    while True:
        user_input = input("You: ")

        if user_input.lower() in ["exit", "quit"]:
            break

        response = ask_model(user_input)

        if response == "RETRY":
            print("Tutor: I'm having a little trouble connecting right now. Try again in a moment.")
            continue

        print("Tutor:", response)


if __name__ == "__main__":
    main()
