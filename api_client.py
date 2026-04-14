import os

import requests
from dotenv import load_dotenv

from error_handling import debug_print, handle_api_error


load_dotenv(".env.local")


MODEL_NAME = os.getenv("HUGGING_FACE_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
API_URL = "https://router.huggingface.co/v1/chat/completions"

 # Read the Hugging Face token from the environment.
def get_api_key():
   
    return os.getenv("HUGGING_FACE_TOKEN")

# Map internal chat roles to the Hugging Face chat-completions schema.
def build_payload(conversation_history):
    
    messages = []
    for msg in conversation_history:
        role = msg["role"].lower()
        if role == "model":
            mapped_role = "assistant"
        elif role in ["user", "assistant", "system"]:
            mapped_role = role
        else:
            mapped_role = "user"

        messages.append({"role": mapped_role, "content": msg["content"]})

    return {
        "model": MODEL_NAME,
        "messages": messages,
        "max_tokens": 500,
        "temperature": 0.4,
    }

# Call the Hugging Face router and normalize common error responses.
def fetch_model_text(conversation_history):
    
    api_token = get_api_key()
    if not api_token:
        return "Please set HUGGING_FACE_TOKEN before starting the tutor."

    headers = {"Authorization": f"Bearer {api_token}"}

    try:
        response = requests.post(API_URL, json=build_payload(conversation_history), headers=headers, timeout=60)
    except requests.RequestException as exc:
        debug_print("Request error", str(exc))
        return "I'm having trouble reaching the model right now. Please try again in a moment."

    try:
        data = response.json()
    except ValueError:
        data = {"error": response.text}

    debug_print("API response", data)

    if response.status_code in (429, 503):
        return "RETRY"

    if response.status_code >= 400:
        message = data.get("error") if isinstance(data, dict) else None
        if response.status_code in (401, 403):
            return "Your Hugging Face token is invalid or lacks access to this model. Check token permissions or try a different model."
        if response.status_code == 404:
            return "The selected Hugging Face model was not found. Set HUGGING_FACE_MODEL to a valid chat model."
        if message:
            return f"Model API error: {message}"
        return f"Model API error (HTTP {response.status_code})."

    if isinstance(data, dict) and "error" in data:
        return handle_api_error(data)

    try:
        if isinstance(data, dict):
            choices = data.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                content = str(message.get("content", "")).strip()
                if content:
                    return content
        return "I couldn't parse the model response. Please try asking again."
    except (KeyError, IndexError, TypeError) as exc:
        debug_print("Response parsing error", str(exc))
        return "I couldn't parse the model response. Please try asking again."
