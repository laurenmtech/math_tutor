"""
test_agent.py
A lightweight offline evaluation harness for the Math Tutor Assistant.

This script tests:
- JSON parsing and formatting contracts
- Student-step validation rules
- Response repair gating
- Off-topic and tutoring behavior through deterministic fixtures
"""

from math_validation import (
    latest_reference_equation,
    student_step_conflicts_with_reference,
)
from tutor_policy import (
    parse_json_text,
    format_response,
    needs_repair,
)

# -----------------------------
# Test Cases
# -----------------------------

CONTRACT_TEST_CASES = [
    {
        "name": "Parses plain JSON",
        "prompt": "How do I solve 3x + 2 = 11?",
        "raw": '{"reply": "Start by isolating x.", "follow_up_question": "What happens if you subtract 2?", "math": ["$$3x = 9$$"]}',
        "expected": "Start by isolating x.\n\n$$3x = 9$$\n\nWhat happens if you subtract 2?",
        "needs_repair": False,
    },
    {
        "name": "Parses fenced JSON",
        "prompt": "Can you help me think this through?",
        "raw": '```json\n{"reply": "Try a similar problem.", "follow_up_question": "Can you solve this one?", "math": []}\n```',
        "expected": "Try a similar problem.\n\nCan you solve this one?",
        "needs_repair": False,
    },
]

UNIT_TEST_CASES = [
    {
        "name": "Blocks wrong distribution step",
        "actual": lambda: student_step_conflicts_with_reference(
            "so 3x-15",
            latest_reference_equation([
                {"role": "system", "content": ""},
                {"role": "user", "content": "3(2x-5)+4=2x+18"},
            ]),
            "Can you distribute the 3 to the terms inside the parentheses, and show me the result?",
        ),
        "expected": True,
    },
    {
        "name": "Allows scalar combine step",
        "actual": lambda: student_step_conflicts_with_reference(
            "-11",
            "6x-15+4=2x+18",
            "Now we have 6x-15+4=2x+18. What happens when we combine the constants -15 and +4 on the left side?",
        ),
        "expected": False,
    },
    {
        "name": "Flags multi-question reply",
        "actual": lambda: needs_repair(
            "How do I solve 3x + 2 = 11?",
            {
                "reply": "Start by subtracting 2. What do you think happens next?",
                "follow_up_question": "Can you subtract 2?",
                "math": ["$$3x = 9$$"],
            },
        ),
        "expected": True,
    },
    {
        "name": "Accepts valid structured response",
        "actual": lambda: needs_repair(
            "How do I solve 3x + 2 = 11?",
            {
                "reply": "Start by subtracting 2 from both sides.",
                "follow_up_question": "What do you get after subtracting 2?",
                "math": ["$$3x = 9$$"],
            },
        ),
        "expected": False,
    },
]

# -----------------------------
# Evaluation Helpers
# -----------------------------

def run_contract_tests():
    """Validate parser/formatter contract behavior using fixed JSON samples."""
    print("\n🔍 Running JSON Contract Tests...\n")

    failed = 0

    for test in CONTRACT_TEST_CASES:
        parsed = parse_json_text(test["raw"])
        formatted = format_response(parsed or {})
        repair_required = needs_repair(test["prompt"], parsed)

        passed = formatted == test["expected"] and repair_required is test["needs_repair"]
        status = "PASS" if passed else "FAIL"

        print(f"🧪 TEST: {test['name']}")
        print(f"  - Parsed: {parsed}")
        print(f"  - Formatted: {formatted}")
        print(f"  - Needs repair: {repair_required}")
        print(f"  - Status: {status}\n")

        if not passed:
            failed += 1

    if failed:
        print(f"Contract tests failed: {failed}")
        raise SystemExit(1)

    print("Contract tests passed.\n")


def run_unit_tests():
    """Run deterministic offline tests for guardrails and validation logic."""
    print("\n🔍 Running Offline Unit Tests...\n")

    failed = 0

    for test in UNIT_TEST_CASES:
        actual = test["actual"]()
        passed = actual == test["expected"]
        status = "PASS" if passed else "FAIL"

        print(f"🧪 TEST: {test['name']}")
        print(f"  - Actual: {actual}")
        print(f"  - Expected: {test['expected']}")
        print(f"  - Status: {status}\n")

        if not passed:
            failed += 1

    if failed:
        print(f"Offline unit tests failed: {failed}")
        raise SystemExit(1)

    print("Offline unit tests passed.\n")


if __name__ == "__main__":
    run_contract_tests()
    run_unit_tests()
