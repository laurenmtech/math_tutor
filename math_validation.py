import re


_EQUATION_RE = re.compile(r"([0-9xX+\-*/().\s^]+=[0-9xX+\-*/().\s^]+)")
_CANDIDATE_RE = re.compile(r"[0-9xX+\-*/().\s^]+")


"""Extract equation-like snippets from free text for later validation checks."""
def _extract_equations(text):
    candidates = _EQUATION_RE.findall(str(text))
    return [candidate.replace("X", "x").strip() for candidate in candidates]


"""Return the most recent equation found in conversation history."""
def _latest_reference_equation(conversation_history):
    for msg in reversed(conversation_history):
        content = str(msg.get("content", ""))
        equations = _extract_equations(content)
        if equations:
            return equations[-1]
    return None


"""Pick the most likely algebra expression segment from a mixed user message."""
def _extract_expression_candidate(user_input):
    cleaned = str(user_input).replace("−", "-")
    segments = _CANDIDATE_RE.findall(cleaned)
    segments = [segment.strip() for segment in segments if segment.strip()]
    if not segments:
        return None
    candidate = max(segments, key=len)
    if not re.search(r"[xX0-9]", candidate):
        return None
    return candidate


"""Extract the expression from tutor prompts like 'What is ... ?'."""
def _extract_targeted_prompt_expression(text):
    match = re.search(r"what\s+is\s+(.+?)\?", str(text), flags=re.IGNORECASE)
    if not match:
        return None
    return _extract_expression_candidate(match.group(1))


"""Parse simple linear text into (x coefficient, constant) or return None."""
def _parse_linear_coeffs(expr):
    """Return (x_coeff, constant) for simple linear forms like 6x-11."""
    cleaned = str(expr).replace("−", "-").replace(" ", "")
    cleaned = cleaned.replace("X", "x")
    if not cleaned:
        return None
    if not re.fullmatch(r"[0-9x+\-.]+", cleaned):
        return None

    terms = re.findall(r"[+-]?[^+-]+", cleaned)
    if not terms:
        return None

    x_coeff = 0.0
    constant = 0.0
    for term in terms:
        if "x" in term:
            if term.count("x") != 1 or term[-1] != "x":
                return None
            coeff_text = term[:-1]
            if coeff_text in ["", "+"]:
                coeff = 1.0
            elif coeff_text == "-":
                coeff = -1.0
            else:
                try:
                    coeff = float(coeff_text)
                except ValueError:
                    return None
            x_coeff += coeff
        else:
            try:
                constant += float(term)
            except ValueError:
                return None

    return x_coeff, constant


"""Return only the x coefficient from a simple linear expression."""
def _linear_x_coeff(expr):
    coeffs = _parse_linear_coeffs(expr)
    if coeffs is None:
        return None
    return coeffs[0]


"""Compute expected distributed x coefficient from text like 3(2x-5)."""
def _distribution_target_from_text(text):
    cleaned = str(text).replace("−", "-")
    match = re.search(r"(\d+)\s*\(\s*([^)]+)\s*\)", cleaned)
    if not match:
        return None

    outer = float(match.group(1))
    inner = match.group(2)
    inner_x_coeff = _linear_x_coeff(inner)
    if inner_x_coeff is None:
        return None

    return outer * inner_x_coeff


"""Derive distribution target from the left side of a reference equation."""
def _distribution_target_from_reference_equation(reference_equation):
    if not reference_equation or "=" not in str(reference_equation):
        return None
    left = str(reference_equation).split("=", 1)[0]
    return _distribution_target_from_text(left)


"""Detect whether a student's distribution result conflicts with tutor intent."""
def _student_invalid_distribution_for_prompt(user_input, last_tutor_message, reference_equation=None):
    if not last_tutor_message:
        return False
    if "distribut" not in str(last_tutor_message).lower():
        return False

    target_x_coeff = _distribution_target_from_text(last_tutor_message)
    if target_x_coeff is None:
        target_x_coeff = _distribution_target_from_reference_equation(reference_equation)
    if target_x_coeff is None:
        return False

    candidate_expr = _extract_expression_candidate(user_input)
    if not candidate_expr:
        return False

    candidate_x_coeff = _linear_x_coeff(candidate_expr)
    if candidate_x_coeff is None:
        return False

    return abs(candidate_x_coeff - target_x_coeff) > 1e-6


"""Decide whether a student's algebra step should be blocked as inconsistent."""
def _student_step_conflicts_with_reference(user_input, reference_equation, last_tutor_message=None):
    if not reference_equation or "=" not in str(reference_equation):
        return False
    if "=" in str(user_input):
        return False

    candidate_expr = _extract_expression_candidate(user_input)
    if not candidate_expr:
        return False

    # Scalar-only answers like "-11" are intermediate arithmetic, not rewrites.
    if "x" not in candidate_expr.lower():
        return False

    if _student_invalid_distribution_for_prompt(user_input, last_tutor_message, reference_equation):
        return True

    # If tutor asked a targeted scalar multiplication prompt, accept equivalent form.
    targeted_expr = _extract_targeted_prompt_expression(last_tutor_message)
    if targeted_expr and _linear_x_coeff(targeted_expr) == _linear_x_coeff(candidate_expr):
        return False

    return False


# Public aliases used by orchestration code.
latest_reference_equation = _latest_reference_equation
student_step_conflicts_with_reference = _student_step_conflicts_with_reference
