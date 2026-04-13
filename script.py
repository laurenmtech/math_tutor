"""
Math Tutor Assistant

This script implements a conversational math tutor that:
- provides step-by-step guidance
- uses a system prompt to enforce tutoring behaviors and math formatting rules
- handles API errors with retry logic
- maintains conversation history for contextual responses

The goal is to demonstrate prompt engineering, error handling, and conversational state management in a simple CLI environment.
"""


import os
import json
import re
import requests
from error_handling import debug_print, handle_api_error


# name of the model used for tutoring. Gemini-2.0-flash-001 is optimized for dialogue and has strong reasoning capabilities, making it a good fit for this application.
MODEL_NAME = "gemini-2.0-flash-001"
MAX_HISTORY_MESSAGES = 24

# retrieves the API key from environment variable.
# This prevents the key from being hardcoded in the repo
def get_api_key():
    return os.getenv("GOOGLE_API_KEY")

# builds the API URL for the Gemini model, including the API key for authentication.
def build_url():
    api_key = get_api_key()
    if not api_key:
        return None
    return f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent?key={api_key}"

# System prompt defines the tutor's behavior, tone, and formatting rules
# This is the core behavioral contract that ensures consistent tutoring style. 
SYSTEM_PROMPT = """
You are a patient, encouraging high school math tutor.

Your goals:
- Guide the student with questions and hints.
- Show them work step-by-step when they ask for help.
- Always ask at least one question to keep the student thinking.
- If they ask for the answer, show them a similar problem with a step-by-step solution instead. 
- Maintain a warm, supportive tutoring tone.

Math formatting rules:
- Always format math expressions using LaTeX.
- Put each formula on its own line using $$ ... $$.
- Do not escape backslashes.
- Do not use code fences.
- Keep formulas simple and readable.

Persona rules:
- Never give yourself a name.
- Never claim to have personal identity or preferences.
- If the student asks off-topic questions, gently redirect back to math.

Error handling:
- If the student input is unclear, ask a clarifying question.
- If the expression is malformed, explain what is missing and ask them to restate it.

Output format:
- Return only valid JSON.
- The JSON object must have these keys: reply, follow_up_question, math.
- reply must be a short tutoring response in plain text.
- follow_up_question must be exactly one question string.
- math must be an array of LaTeX blocks, or an empty array if no math is needed.
- Do not include markdown, code fences, or any text outside the JSON object.


"""

# Conversation history
# seeds the conversation with the prompt so it stays at the front of the context
def create_history():
    return [{"role": "user", "content": SYSTEM_PROMPT}]


history = create_history()


def trim_history(conversation_history):
    """Keep the system prompt plus the most recent messages."""
    if len(conversation_history) <= MAX_HISTORY_MESSAGES:
        return conversation_history

    return [conversation_history[0]] + conversation_history[-(MAX_HISTORY_MESSAGES - 1):]

# covnverts the conversation into the Gemini request body
def build_payload(conversation_history):
    return {
        "contents": [
            {
                "role": msg["role"].upper(),
                "parts": [{"text": msg["content"]}]
            }
            for msg in conversation_history
        ]
    }

# tries to pull valid JSON out of the raw response, even if the model wrapped it in extra text. 
def extract_json_text(raw_text):
    cleaned = raw_text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = cleaned[start:end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def format_structured_response(parsed_response):
    reply = str(parsed_response.get("reply", "")).strip()
    follow_up_question = str(parsed_response.get("follow_up_question", "")).strip()
    math_blocks = parsed_response.get("math", [])

    parts = []
    if reply:
        parts.append(reply)

    if isinstance(math_blocks, list):
        for block in math_blocks:
            block_text = str(block).strip()
            if block_text:
                parts.append(block_text)

    if follow_up_question:
        parts.append(follow_up_question)

    return "\n\n".join(parts).strip()

# checks whether the parsed JSON voilates the rules, such as missing a question or math behavior
def response_needs_repair(user_input, parsed_response):
    if not isinstance(parsed_response, dict):
        return True

    reply = str(parsed_response.get("reply", "")).strip()
    follow_up_question = str(parsed_response.get("follow_up_question", "")).strip()
    math_blocks = parsed_response.get("math", [])

    if not reply or not follow_up_question.endswith("?"):
        return True

    if "final answer" in reply.lower() or "the answer is" in reply.lower():
        return True

    if not isinstance(math_blocks, list):
        return True

    if looks_like_math_prompt(user_input) and math_blocks == []:
        return True

    for block in math_blocks:
        if not isinstance(block, str) or "$$" not in block:
            return True

    return False

# sends the request, handles API errors, and returns the raw model text
def fetch_model_text(conversation_history):
    api_url = build_url()
    if not api_url:
        return "Please set GOOGLE_API_KEY before starting the tutor."

    try:
        response = requests.post(api_url, json=build_payload(conversation_history), timeout=30)
        if response.status_code in (429, 503):
            return "RETRY"

        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return "I'm having trouble reaching the model right now. Please try again in a moment."
    except ValueError:
        return "I received an invalid response from the model. Please try again."

    if "error" in data:
        return handle_api_error(data)

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        return "I couldn't parse the model response. Please try asking again."


def make_repair_prompt(user_input, raw_response):
    return (
        "Convert the draft tutor response into valid JSON that matches the required schema exactly. "
        "Return only JSON. Do not include code fences or extra text. "
        "Use this exact shape: {\"reply\": string, \"follow_up_question\": string, \"math\": [string, ...]}. "
        "The reply should be warm and concise. The follow_up_question must be one question. "
        "Use math blocks only for LaTeX formulas, and keep them in the math array. "
        f"Student input: {user_input}\n"
        f"Draft response: {raw_response}"
    )


def looks_like_math_prompt(user_input):
    lowered = user_input.lower()
    symbol_markers = ["=", "+", "-", "*", "/", "∫", "∑", "^"]
    word_patterns = [r"\bsolve\b", r"\bsqrt\b", r"\b(?:x|y|z)\b"]

    if any(marker in lowered for marker in symbol_markers):
        return True

    return any(re.search(pattern, lowered) for pattern in word_patterns)

#putting everything together:
# 1. adds the user input to the conversation history
# 2. fetches the model response
# 3. parse JSON 
# 4. optionally run a repair pass
# 5. format the structured response back into text
# 6. add the agent response to the conversation history
def ask_model(user_input, conversation_history=None, store_turn=True, allow_repair_retry=True):
    active_history = conversation_history if conversation_history is not None else history

    if user_input:
        active_history.append({"role": "user", "content": user_input})
        active_history[:] = trim_history(active_history)

    raw_output = fetch_model_text(active_history)
    if raw_output in ["RETRY", "Please set GOOGLE_API_KEY before starting the tutor."]:
        return raw_output

    parsed_output = extract_json_text(raw_output)

    if allow_repair_retry and user_input and response_needs_repair(user_input, parsed_output):
        repair_history = active_history + [{"role": "user", "content": make_repair_prompt(user_input, raw_output)}]
        repaired_raw_output = fetch_model_text(repair_history)
        if repaired_raw_output == "RETRY":
            return repaired_raw_output

        repaired_parsed_output = extract_json_text(repaired_raw_output)
        if repaired_parsed_output is not None:
            parsed_output = repaired_parsed_output

    if parsed_output is None:
        output = raw_output
    else:
        output = format_structured_response(parsed_output)
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

        # Handle retry logic here (Option A)
        if response == "RETRY":
            print("Tutor: I'm having a little trouble connecting right now. Try again in a moment.")
            continue

        print("Tutor:", response)

if __name__ == "__main__":
    main()
