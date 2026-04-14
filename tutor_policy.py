import re
import json
 
# ---------------------------------------------------------------------------
# Final-answer detection: student explicitly wants the solution handed to them.
# ---------------------------------------------------------------------------
 
FINAL_ANSWER_PATTERNS = [
    r"final answer",
    r"just the answer",
    r"solve completely",
    r"give me the answer",
    r"just tell me",
    r"what(?:'s| is) x\b",
    r"stop hinting",
    r"tell me the solution",
    r"skip the hints",
    r"can you just solve",
]
 
 
def student_wants_final_answer(user_input: str) -> bool:
    """Return True if the student is explicitly requesting the solved answer."""
    lowered = user_input.lower()
    return any(re.search(p, lowered) for p in FINAL_ANSWER_PATTERNS)
 
 
# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
 
SYSTEM_PROMPT = """
You are a patient, encouraging high school math tutor.
 
Your goals:
- Guide the student with questions and hints — never give the answer directly.
- Show work step-by-step only when the student explicitly asks for help with a step.
- Always ask exactly one question per response to keep the student thinking.
- If they ask for the final answer, show them a similar worked example instead.
- Maintain a warm, supportive tutoring tone throughout.
 
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
- Return only valid JSON with no surrounding text, markdown, or code fences.
- The JSON object must have exactly these keys: reply, follow_up_question, math.
  - reply: a short tutoring response in plain text. Must NOT contain a question mark.
  - follow_up_question: exactly one question string.
  - math: an array of LaTeX blocks (each wrapped in $$ ... $$), or an empty array.
 
Coaching strictness:
- Do not solve the full problem in one turn.
- Give only one next step per response.
- Show at most one transformed equation per response.
- Do not reveal the final solved form (e.g. x = 3) unless the student has
  explicitly requested the final answer AND has already attempted that step.
"""
 
# ---------------------------------------------------------------------------
# Repair cap and safe fallback
# ---------------------------------------------------------------------------
 
MAX_REPAIR_ATTEMPTS = 2
 
FALLBACK_RESPONSE = {
    "reply": "I want to make sure I give you a helpful hint — could you restate the problem?",
    "follow_up_question": "What step are you currently stuck on?",
    "math": [],
}
 
# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------
 
 
def extract_json_text(raw_text: str) -> dict | None:
    """Pull valid JSON out of raw model output, even if wrapped in extra text."""
    cleaned = raw_text.strip()
 
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
 
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
 
    candidate = cleaned[start : end + 1]
 
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None
 
 
# ---------------------------------------------------------------------------
# LaTeX / equation helpers
# ---------------------------------------------------------------------------
 
# A valid LaTeX block must open and close with $$ and contain non-whitespace content.
_LATEX_BLOCK_RE = re.compile(r"^\$\$.+\$\$$", re.DOTALL)
 
# Matches inline or display LaTeX so we can count equations across all fields.
_EQUATION_RE = re.compile(r"\$\$.*?\$\$|\$[^$]+\$", re.DOTALL)
 
 
def _extract_equations(text: str) -> list[str]:
    return _EQUATION_RE.findall(text)
 
 
def _count_equations(parsed: dict) -> int:
    """Count all LaTeX equations across every field of the parsed response."""
    total = 0
    for field in ("reply", "follow_up_question"):
        total += len(_extract_equations(str(parsed.get(field, ""))))
    for block in parsed.get("math", []) if isinstance(parsed.get("math"), list) else []:
        total += len(_extract_equations(str(block)))
    return total
 
 
# ---------------------------------------------------------------------------
# Final-value reveal detection  (broadened beyond just "x")
# ---------------------------------------------------------------------------
 
# Matches any single-letter variable assigned a numeric value, e.g. x = 3, y = -2.5
_FINAL_VALUE_RE = re.compile(
    r"\b[a-z]\s*=\s*[-+]?\d+(?:\.\d+)?\b",
    flags=re.IGNORECASE,
)
 
 
def _has_final_value_reveal(parsed: dict) -> bool:
    """Return True if any field reveals a solved variable value."""
    segments = [
        str(parsed.get("reply", "")),
        str(parsed.get("follow_up_question", "")),
    ]
    math_blocks = parsed.get("math", [])
    if isinstance(math_blocks, list):
        segments.extend(str(b) for b in math_blocks)
    combined = "\n".join(segments)
    return bool(_FINAL_VALUE_RE.search(combined))
 
 
# ---------------------------------------------------------------------------
# Math-prompt detection  (covers word problems, not just symbols)
# ---------------------------------------------------------------------------
 
_MATH_SYMBOL_MARKERS = ["=", "+", "-", "*", "/", "∫", "∑", "^"]
 
_MATH_WORD_PATTERNS = [
    r"\b(solve|simplify|factor|evaluate|expand|find|calculate|integrate|differentiate)\b",
    r"\b(equation|expression|polynomial|function|variable|coefficient|exponent)\b",
    r"\b(percent|ratio|rate|distance|speed|area|perimeter|volume|slope|intercept)\b",
    r"\b(sqrt|sin|cos|tan|log|ln)\b",
    r"\b(?:x|y|z|n)\b",  # lone variable references
]
 
_MATH_WORD_RE = [re.compile(p, re.IGNORECASE) for p in _MATH_WORD_PATTERNS]
 
 
def looks_like_math_prompt(user_input: str) -> bool:
    """Heuristic: does this input call for math-specific tutoring constraints?"""
    lowered = user_input.lower()
    if any(marker in lowered for marker in _MATH_SYMBOL_MARKERS):
        return True
    return any(pattern.search(lowered) for pattern in _MATH_WORD_RE)
 
 
# ---------------------------------------------------------------------------
# Algebraic consistency check
# ---------------------------------------------------------------------------
 
 
def _math_is_consistent_for_linear_input(reference_eq: str | None, parsed: dict) -> bool:
    """
    Lightweight check: if the reference equation is a simple linear equation
    (ax + b = c), verify that any numeric equation in the response is plausibly
    derived from it.  Returns True when the check is inconclusive or passes.
    """
    if reference_eq is None:
        return True
 
    # Only attempt validation for simple linear equations
    linear_match = re.match(
        r"(-?\d*)\s*\*?\s*x\s*([+-]\s*\d+)?\s*=\s*(-?\d+)",
        reference_eq.replace(" ", ""),
        re.IGNORECASE,
    )
    if not linear_match:
        return True  # can't validate — assume fine
 
    try:
        a_str = linear_match.group(1) or "1"
        b_str = (linear_match.group(2) or "0").replace(" ", "")
        c_str = linear_match.group(3)
        a, b, c = float(a_str), float(b_str), float(c_str)
    except ValueError:
        return True
 
    if a == 0:
        return True
 
    expected_x = (c - b) / a
 
    # Look for any x = <number> in the response
    math_blocks = parsed.get("math", [])
    all_text = "\n".join(
        [str(parsed.get("reply", "")), str(parsed.get("follow_up_question", ""))]
        + ([str(b) for b in math_blocks] if isinstance(math_blocks, list) else [])
    )
 
    for m in _FINAL_VALUE_RE.finditer(all_text):
        if m.group(0).lower().startswith("x"):
            try:
                stated_x = float(re.search(r"[-+]?\d+(?:\.\d+)?", m.group(0).split("=")[1]).group())
                if abs(stated_x - expected_x) > 1e-6:
                    return False
            except (AttributeError, ValueError, IndexError):
                pass
 
    return True
 
 
# ---------------------------------------------------------------------------
# Single-question enforcement helpers
# ---------------------------------------------------------------------------
 
 
def _reply_contains_question(text: str) -> bool:
    """Return True if the reply field contains a question mark (policy violation)."""
    return "?" in text
 
 
def normalize_single_question(text: str) -> str:
    """Keep only the first question from a string and ensure it ends with '?'."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return ""
    first_question = cleaned.split("?", 1)[0].strip()
    if not first_question:
        return ""
    return f"{first_question}?"
 
 
# ---------------------------------------------------------------------------
# Response assembly
# ---------------------------------------------------------------------------
 
 
def format_structured_response(parsed: dict) -> str:
    """Assemble validated JSON fields into a display string for the UI."""
    reply = str(parsed.get("reply", "")).strip()
    follow_up_question = normalize_single_question(
        str(parsed.get("follow_up_question", "")).strip()
    )
    math_blocks = parsed.get("math", [])
 
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
 
 
# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
 
 
def response_needs_repair(
    user_input: str,
    parsed: dict,
    reference_equation: str | None = None,
) -> bool:
    """
    Return True if the parsed response violates any tutoring policy rule.
    Checks are ordered from cheapest to most expensive.
    """
    if not isinstance(parsed, dict):
        return True
 
    reply = str(parsed.get("reply", "")).strip()
    follow_up_question = str(parsed.get("follow_up_question", "")).strip()
    math_blocks = parsed.get("math", [])
 
    # Required fields must be non-empty
    if not reply:
        return True
    if not normalize_single_question(follow_up_question):
        return True
 
    # reply must not contain a question (questions belong in follow_up_question only)
    if _reply_contains_question(reply):
        return True
 
    # Banned phrases in reply
    banned = ("final answer", "the answer is", "therefore x =", "so x =")
    if any(phrase in reply.lower() for phrase in banned):
        return True
 
    # math must be a list of properly-formed LaTeX blocks
    if not isinstance(math_blocks, list):
        return True
    for block in math_blocks:
        if not isinstance(block, str) or not _LATEX_BLOCK_RE.match(block.strip()):
            return True
 
    # Math-specific constraints
    if looks_like_math_prompt(user_input):
        # At least one math block required for math prompts
        if not math_blocks:
            return True
 
        # One guided step at a time
        if _count_equations(parsed) > 1:
            return True
 
        # No final value reveal unless student explicitly asked for it
        if _has_final_value_reveal(parsed) and not student_wants_final_answer(user_input):
            return True
 
        # Algebraic consistency
        reference = reference_equation
        if reference is None:
            inline_eqs = _extract_equations(user_input)
            reference = inline_eqs[-1] if inline_eqs else None
 
        if not _math_is_consistent_for_linear_input(reference, parsed):
            return True
 
    return False
 
 
# ---------------------------------------------------------------------------
# Repair prompt
# ---------------------------------------------------------------------------
 
 
def make_repair_prompt(user_input: str, raw_response: str) -> str:
    """
    Build a strict rewrite instruction used when output fails validation.
    Includes the full system prompt so the repair call honours all tutoring rules.
    """
    return (
        f"{SYSTEM_PROMPT}\n\n"
        "The draft response below failed policy validation. Rewrite it as valid JSON "
        "that matches the required schema exactly. Return only JSON — no code fences, "
        "no preamble, no trailing text.\n\n"
        "Required shape:\n"
        '{"reply": string, "follow_up_question": string, "math": [string, ...]}\n\n'
        "Rules to enforce:\n"
        "- reply must be warm and concise with NO question marks.\n"
        "- follow_up_question must be exactly one question.\n"
        "- math must contain only $$ ... $$ LaTeX blocks.\n"
        "- Provide only one next step and at most one transformed equation.\n"
        "- Any equation must be algebraically equivalent to the current problem state.\n"
        "- Do not reveal the solved value of any variable unless the student explicitly "
        "asked for the final answer.\n\n"
        f"Student input: {user_input}\n"
        f"Draft response: {raw_response}"
    )
 
 
# ---------------------------------------------------------------------------
# Public aliases  (backwards-compatible with existing orchestration code)
# ---------------------------------------------------------------------------
 
parse_json_text = extract_json_text
format_response = format_structured_response
needs_repair = response_needs_repair
build_repair_prompt = make_repair_prompt