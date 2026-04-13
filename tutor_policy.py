import json
import re

from math_validation import (
    _extract_equations,
    _math_is_consistent_for_linear_input,
)


FINAL_ANSWER_MARKERS = ["final answer", "just the answer", "solve completely", "give me the answer"]

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

Coaching strictness:
- Do not solve the full problem in one turn.
- Give only one next step per response.
- Show at most one transformed equation per response.
- Do not give final solved form (for example x = number) unless the student explicitly asks for the final answer.


"""


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


# a check to make sure theres no question dumping in the reply.
def remove_question_sentences(text):
    # Drop sentence-like chunks that contain a question mark so only one final question is shown.
    chunks = re.split(r"(?<=[.!?])\s+", text)
    kept = [chunk for chunk in chunks if "?" not in chunk]
    return " ".join(kept).strip()


# another check to make sure the follow up response contains exactly one question.
def normalize_single_question(text):
    # Keep only the first question and ensure it ends with a single question mark.
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return ""

    first_question = cleaned.split("?", 1)[0].strip()
    if not first_question:
        return ""
    return f"{first_question}?"


# Count equations across reply fields to enforce one-step tutoring responses.
def _count_equations(parsed_response):
    total = 0
    reply_text = str(parsed_response.get("reply", ""))
    follow_up_question = str(parsed_response.get("follow_up_question", ""))
    total += len(_extract_equations(reply_text))
    total += len(_extract_equations(follow_up_question))

    math_blocks = parsed_response.get("math", [])
    if isinstance(math_blocks, list):
        for block in math_blocks:
            total += len(_extract_equations(str(block)))

    return total


# Detect direct final-value reveals like x = 3.
def _has_final_x_value(parsed_response):
    segments = [
        str(parsed_response.get("reply", "")),
        str(parsed_response.get("follow_up_question", "")),
    ]

    math_blocks = parsed_response.get("math", [])
    if isinstance(math_blocks, list):
        segments.extend(str(block) for block in math_blocks)

    combined = "\n".join(segments)
    return re.search(r"\bx\s*=\s*[-+]?\d+(?:\.\d+)?\b", combined, flags=re.IGNORECASE) is not None


# Assemble validated JSON fields into a display string for the UI.
def format_structured_response(parsed_response):
    reply = remove_question_sentences(str(parsed_response.get("reply", "")).strip())
    follow_up_question = normalize_single_question(str(parsed_response.get("follow_up_question", "")).strip())
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
def response_needs_repair(user_input, parsed_response, reference_equation=None):
    if not isinstance(parsed_response, dict):
        return True

    reply = str(parsed_response.get("reply", "")).strip()
    follow_up_question = str(parsed_response.get("follow_up_question", "")).strip()
    math_blocks = parsed_response.get("math", [])

    if not reply:
        return True

    normalized_follow_up = normalize_single_question(follow_up_question)
    if not normalized_follow_up:
        return True

    # Enforce exactly one question total in rendered output.
    if "?" in reply:
        return True

    if "final answer" in reply.lower() or "the answer is" in reply.lower():
        return True

    if not isinstance(math_blocks, list):
        return True

    for block in math_blocks:
        if not isinstance(block, str) or "$$" not in block:
            return True

    is_math_prompt = looks_like_math_prompt(user_input)
    if is_math_prompt:
        if math_blocks == []:
            return True

        # Keep tutor behavior to one guided step at a time.
        if _count_equations(parsed_response) > 1:
            return True

        explicitly_requested_final = any(marker in user_input.lower() for marker in FINAL_ANSWER_MARKERS)
        if _has_final_x_value(parsed_response) and not explicitly_requested_final:
            return True

        # Validate algebraic equivalence for generated equations when relevant.
        reference = reference_equation
        if reference is None:
            inline_equations = _extract_equations(user_input)
            reference = inline_equations[-1] if inline_equations else None

        if not _math_is_consistent_for_linear_input(reference, parsed_response):
            return True

    return False


# Build a strict rewrite instruction used when output fails validation.
def make_repair_prompt(user_input, raw_response):
    return (
        "Convert the draft tutor response into valid JSON that matches the required schema exactly. "
        "Return only JSON. Do not include code fences or extra text. "
        "Use this exact shape: {\"reply\": string, \"follow_up_question\": string, \"math\": [string, ...]}. "
        "The reply should be warm and concise. The follow_up_question must be one question. "
        "Use math blocks only for LaTeX formulas, and keep them in the math array. "
        "Provide only one next step and at most one transformed equation. "
        "Any transformed equation must stay algebraically equivalent to the current equation in context. "
        "Do not solve the full problem unless the student explicitly requests the final answer. "
        f"Student input: {user_input}\n"
        f"Draft response: {raw_response}"
    )


# Heuristic: detect when input likely expects math-specific constraints.
def looks_like_math_prompt(user_input):
    lowered = user_input.lower()
    symbol_markers = ["=", "+", "-", "*", "/", "∫", "∑", "^"]
    word_patterns = [r"\bsolve\b", r"\bsqrt\b", r"\b(?:x|y|z)\b"]

    if any(marker in lowered for marker in symbol_markers):
        return True

    return any(re.search(pattern, lowered) for pattern in word_patterns)


# Public aliases used by orchestration code; underscore versions remain for compatibility.
parse_json_text = extract_json_text
format_response = format_structured_response
needs_repair = response_needs_repair
build_repair_prompt = make_repair_prompt
