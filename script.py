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
import requests
from error_handling import debug_print, handle_api_error


# name of the model used for tutoring. Gemini-2.0-flash-001 is optimized for dialogue and has strong reasoning capabilities, making it a good fit for this application.
MODEL_NAME = "gemini-2.0-flash-001"

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

URL = build_url()

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


"""

# Conversation history
# Gemini models expect the system prompt to appear as the first "user" message.
def create_history():
    return [{"role": "user", "content": SYSTEM_PROMPT}]


history = create_history()

def ask_model(user_input):
    history.append({"role": "user", "content": user_input})

    payload = {
        "contents": [
            {
                "role": msg["role"].upper(),
                "parts": [{"text": msg["content"]}]
            }
            for msg in history
        ]
    }

    #debug_print(payload)

    response = requests.post(URL, json=payload)
    #debug_print(response)

    data = response.json()

    # Handle API errors
    if "error" in data:
        return handle_api_error(data)

    # Normal model output
    output = data["candidates"][0]["content"]["parts"][0]["text"]
    #debug_print(output)

    history.append({"role": "model", "content": output})
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
