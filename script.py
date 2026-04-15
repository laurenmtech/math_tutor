"""
Math Tutor Assistant

This module orchestrates the tutoring flow:
- keeps conversation history
- tracks a structured tutor state for each turn
- routes requests to the API client
- validates and repairs structured responses
- handles student-step blocking before the model is called
"""

import json
import copy

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

#Create per-session state that is attached to every API request.
def create_tutor_state():
    
    return {
        "current_problem": None,
        "hint_history": [],
        "attempt_count": 0,
        "student_last_answer": None,
        "stage": "understand",
        "reference_equation": None,
    }

#Infer a lightweight stage label from current turn state.
def _infer_stage(state, correction_issued=False, repair_mode=False):
    
    if repair_mode:
        return "repair"
    if correction_issued:
        return "corrective_hint"

    attempts = int(state.get("attempt_count", 0) or 0)
    if attempts <= 0:
        return "understand"
    if attempts == 1:
        return "attempt"
    return "reflect"

#Update state fields based on the new student turn before API call.
def _update_state_before_call(state, user_input, conversation_history, reference_equation):
    
    if user_input:
        state["student_last_answer"] = user_input
        state["attempt_count"] = int(state.get("attempt_count", 0) or 0) + 1
        if not state.get("current_problem"):
            state["current_problem"] = user_input

    latest_eq = reference_equation or latest_reference_equation(conversation_history)
    state["reference_equation"] = latest_eq
    state["stage"] = _infer_stage(state)

#Store tutor guidance snippets so the model gets explicit hint history.
def _update_state_after_model_reply(state, tutor_reply):
    
    if tutor_reply:
        hints = state.get("hint_history") or []
        hints.append(str(tutor_reply))
        state["hint_history"] = hints[-6:]


history = create_history()
state = create_tutor_state()

#Keep the system prompt plus the most recent messages.
def trim_history(conversation_history):
    
    if len(conversation_history) <= MAX_HISTORY_MESSAGES:
        return conversation_history

    return [conversation_history[0]] + conversation_history[-(MAX_HISTORY_MESSAGES - 1):]

#Run a tutor turn and return the final display text.
def ask_model(
    user_input,
    conversation_history=None,
    tutor_state=None,
    store_turn=True,
    allow_repair_retry=True,
):
   
    active_history = conversation_history if conversation_history is not None else history
    active_state = tutor_state if tutor_state is not None else state

    reference_equation = latest_reference_equation(active_history)
    last_tutor_message = None
    if active_history:
        last_msg = active_history[-1]
        if str(last_msg.get("role", "")).lower() in ["model", "assistant"]:
            last_tutor_message = str(last_msg.get("content", ""))

    if user_input:
        _update_state_before_call(active_state, user_input, active_history, reference_equation)

        if student_step_conflicts_with_reference(user_input, reference_equation, last_tutor_message):
            correction = (
                "Nice attempt, but that transformation changes the equation. "
                "When you distribute, multiply 3 by both terms inside the parentheses. "
                "What is $3 \\cdot 2x$?"
            )
            active_state["stage"] = _infer_stage(active_state, correction_issued=True)
            _update_state_after_model_reply(active_state, correction)
            if store_turn:
                active_history.append({"role": "user", "content": user_input})
                active_history.append({"role": "model", "content": correction})
                active_history[:] = trim_history(active_history)
            return correction

        active_history.append({"role": "user", "content": user_input})
        active_history[:] = trim_history(active_history)

    raw_output = fetch_model_text(active_history, turn_state=active_state)
    if raw_output in ["RETRY", "Please set HUGGING_FACE_TOKEN before starting the tutor."]:
        return raw_output

    parsed_output = parse_json_text(raw_output)

    if allow_repair_retry and user_input and needs_repair(user_input, parsed_output, reference_equation):
        repair_state = copy.deepcopy(active_state)
        repair_state["stage"] = _infer_stage(repair_state, repair_mode=True)
        repair_history = active_history + [{"role": "user", "content": build_repair_prompt(user_input, raw_output)}]
        repaired_raw_output = fetch_model_text(repair_history, turn_state=repair_state)
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

    _update_state_after_model_reply(active_state, output)
    active_state["stage"] = _infer_stage(active_state)

    if store_turn:
        active_history.append({"role": "model", "content": output})
        active_history[:] = trim_history(active_history)

    return output


# Tutor CLI loop.
# Wrapped in main() so it does not run when imported by test_agent.py.
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
