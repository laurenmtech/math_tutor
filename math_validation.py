import re


# Find equation-like snippets so we can validate algebraic consistency.
def _extract_equations(text):
    candidates = re.findall(r"([0-9xX+\-*/().\s^]+=[0-9xX+\-*/().\s^]+)", text)
    return [candidate.replace("X", "x").strip() for candidate in candidates]


# Pull the newest equation in chat history as the consistency anchor.
def _latest_reference_equation(conversation_history):
    for msg in reversed(conversation_history):
        content = str(msg.get("content", ""))
        equations = _extract_equations(content)
        if equations:
            return equations[-1]
    return None


# Normalize math text into a Python-evaluable linear expression form.
def _normalize_expr(expr):
    expr = expr.replace("^", "**")
    expr = expr.replace("−", "-")
    expr = expr.replace(" ", "")
    expr = re.sub(r"(\d)(x)", r"\1*\2", expr)
    expr = re.sub(r"(x)(\d)", r"\1*\2", expr)
    expr = re.sub(r"(\))(x|\d)", r"\1*\2", expr)
    expr = re.sub(r"(x|\d)(\()", r"\1*\2", expr)
    return expr


# Evaluate with x bound and builtins disabled for safer numeric checks.
def _safe_eval(expr, x_value):
    return eval(expr, {"__builtins__": {}}, {"x": x_value})


# Estimate ax + b by sampling at x=0,1,2 and reject non-linear forms.
def _linear_coeffs(expr):
    if not re.fullmatch(r"[0-9x+\-*/().]*", expr):
        return None

    try:
        f0 = float(_safe_eval(expr, 0.0))
        f1 = float(_safe_eval(expr, 1.0))
        f2 = float(_safe_eval(expr, 2.0))
    except Exception:
        return None

    a = f1 - f0
    b = f0
    if abs((f2 - f1) - a) > 1e-6:
        return None
    return a, b


# Solve a single linear equation in x by comparing left and right coefficients.
def _solve_linear_equation(equation_text):
    if equation_text.count("=") != 1:
        return None

    left, right = equation_text.split("=", 1)
    left = _normalize_expr(left)
    right = _normalize_expr(right)

    left_coeffs = _linear_coeffs(left)
    right_coeffs = _linear_coeffs(right)
    if left_coeffs is None or right_coeffs is None:
        return None

    a1, b1 = left_coeffs
    a2, b2 = right_coeffs
    denom = a1 - a2
    if abs(denom) < 1e-9:
        return None

    return (b2 - b1) / denom


# Extract the most useful math-like expression from a mixed natural-language input.
def _extract_expression_candidate(user_input):
    cleaned = user_input.replace("−", "-")
    # Prefer longest math-like segment so inputs like "so 3x-15" map to "3x-15".
    segments = re.findall(r"[0-9xX+\-*/().\s^]+", cleaned)
    segments = [segment.strip() for segment in segments if segment.strip()]
    if not segments:
        return None
    candidate = max(segments, key=len)
    if not re.search(r"[xX0-9]", candidate):
        return None
    return candidate


# Compare two expressions by their linear coefficients.
def _expressions_equivalent(expr_a, expr_b):
    norm_a = _normalize_expr(expr_a)
    norm_b = _normalize_expr(expr_b)

    coeffs_a = _linear_coeffs(norm_a)
    coeffs_b = _linear_coeffs(norm_b)
    if coeffs_a is not None and coeffs_b is not None:
        return abs(coeffs_a[0] - coeffs_b[0]) <= 1e-6 and abs(coeffs_a[1] - coeffs_b[1]) <= 1e-6

    return False


# Return only the x coefficient from a linear expression.
def _linear_x_coeff(expr):
    coeffs = _linear_coeffs(_normalize_expr(expr))
    if coeffs is None:
        return None
    return coeffs[0]


# Read prompts like 3(2x-5) and compute expected distributed x coefficient.
def _distribution_target_from_text(text):
    cleaned = text.replace("−", "-")
    match = re.search(r"(\d+)\s*\(\s*([^)]+)\s*\)", cleaned)
    if not match:
        return None

    outer = float(match.group(1))
    inner = match.group(2)
    inner_x_coeff = _linear_x_coeff(inner)
    if inner_x_coeff is None:
        return None

    return outer * inner_x_coeff


# If tutor asked for distribution, verify the student's x coefficient matches the target.
def _student_invalid_distribution_for_prompt(user_input, last_tutor_message):
    if not last_tutor_message:
        return False

    if "distribut" not in last_tutor_message.lower():
        return False

    target_x_coeff = _distribution_target_from_text(last_tutor_message)
    if target_x_coeff is None:
        return False

    candidate_expr = _extract_expression_candidate(user_input)
    if not candidate_expr:
        return False

    candidate_x_coeff = _linear_x_coeff(candidate_expr)
    if candidate_x_coeff is None:
        return False

    return abs(candidate_x_coeff - target_x_coeff) > 1e-6


# Catch wrong expansions such as 3(2x-5)=3x-15.
def _equation_has_invalid_distribution(equation_text):
    cleaned = equation_text.replace("−", "-").replace(" ", "")
    if "=" not in cleaned:
        return False

    left, right = cleaned.split("=", 1)
    left_match = re.fullmatch(r"(\d+)\(([^)]+)\)", left)
    if not left_match:
        return False

    outer = float(left_match.group(1))
    inner = left_match.group(2)
    target_x_coeff = _linear_x_coeff(inner)
    right_x_coeff = _linear_x_coeff(right)
    if target_x_coeff is None or right_x_coeff is None:
        return False

    expected = outer * target_x_coeff
    return abs(expected - right_x_coeff) > 1e-6


# Capture prompts like "What is 3·2x?" or "What is 3 * 2x?"
def _extract_targeted_prompt_expression(text):
    match = re.search(r"what\s+is\s+(.+?)\?", text, flags=re.IGNORECASE)
    if not match:
        return None
    return _extract_expression_candidate(match.group(1))


# Decide whether a student step changes the underlying equation incorrectly.
def _student_step_conflicts_with_reference(user_input, reference_equation, last_tutor_message=None):
    if not reference_equation or "=" not in reference_equation:
        return False

    # Only attempt this check when the student likely submitted a bare algebra expression.
    if "=" in user_input:
        return False

    candidate_expr = _extract_expression_candidate(user_input)
    if not candidate_expr:
        return False

    # Scalar-only sub-answers (for example "-11" when combining constants)
    # are not full equation rewrites and should not be blocked here.
    if "x" not in candidate_expr.lower():
        return False

    if _student_invalid_distribution_for_prompt(user_input, last_tutor_message):
        return True

    if last_tutor_message:
        targeted_expr = _extract_targeted_prompt_expression(last_tutor_message)
        if targeted_expr and _expressions_equivalent(candidate_expr, targeted_expr):
            return False

    # Only enforce full-transform consistency when the student's text looks like a multi-term rewrite.
    if not re.search(r"[+\-]", candidate_expr):
        return False

    try:
        _, reference_right = reference_equation.split("=", 1)
    except ValueError:
        return False

    student_equation = f"{candidate_expr}={reference_right.strip()}"

    reference_solution = _solve_linear_equation(reference_equation)
    student_solution = _solve_linear_equation(student_equation)
    if reference_solution is None or student_solution is None:
        return False

    return abs(reference_solution - student_solution) > 1e-6


# Ensure all model-shown equations stay equivalent to the reference equation.
def _math_is_consistent_for_linear_input(reference_equation, parsed_response):
    if not reference_equation:
        return True

    reference_solution = _solve_linear_equation(reference_equation)
    if reference_solution is None:
        return True

    reply_text = str(parsed_response.get("reply", ""))
    follow_up_question = str(parsed_response.get("follow_up_question", ""))
    math_blocks = parsed_response.get("math", [])

    sources = [reply_text, follow_up_question]
    if isinstance(math_blocks, list):
        sources.extend(str(block) for block in math_blocks)

    for source in sources:
        for equation in _extract_equations(source):
            if _equation_has_invalid_distribution(equation):
                return False
            step_solution = _solve_linear_equation(equation)
            if step_solution is None:
                continue
            if abs(step_solution - reference_solution) > 1e-6:
                return False

    return True


# Public aliases used by orchestration code; underscore versions remain for compatibility.
extract_equations = _extract_equations
latest_reference_equation = _latest_reference_equation
normalize_expr = _normalize_expr
safe_eval = _safe_eval
linear_coeffs = _linear_coeffs
solve_linear_equation = _solve_linear_equation
extract_expression_candidate = _extract_expression_candidate
expressions_equivalent = _expressions_equivalent
linear_x_coeff = _linear_x_coeff
distribution_target_from_text = _distribution_target_from_text
student_invalid_distribution_for_prompt = _student_invalid_distribution_for_prompt
equation_has_invalid_distribution = _equation_has_invalid_distribution
extract_targeted_prompt_expression = _extract_targeted_prompt_expression
student_step_conflicts_with_reference = _student_step_conflicts_with_reference
math_is_consistent_for_linear_input = _math_is_consistent_for_linear_input
