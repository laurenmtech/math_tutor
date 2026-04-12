"""
test_agent.py
A lightweight evaluation harness for the Math Tutor Assistant.

This script tests:
- Edge case handling
- Persona consistency
- Tutoring behavior (no full answers immediately)
- Math formatting quality
- Robustness to malformed input
- Off-topic redirection

NOTE: I dont recommend running this test suite frequently during development, as it makes many API calls.
"""

from script import ask_model
import time

# -----------------------------
# Test Cases
# -----------------------------

TEST_CASES = [
    # Edge cases
    {
        "prompt": "",
        "description": "Handles empty input gracefully",
    },
    {
        "prompt": "???",
        "description": "Handles nonsense input",
    },
    {
        "prompt": "help",
        "description": "Stays in tutor persona on vague input",
    },
    {
        "prompt": "What is your name?",
        "description": "Redirects off-topic questions back to math",
    },

    # Math-specific edge cases
    {
        "prompt": "solve ∫∫ dx dy",
        "description": "Asks clarifying questions for incomplete math expressions",
    },
    {
        "prompt": "2x + = 5",
        "description": "Handles malformed algebra",
    },
    {
        "prompt": "What is ∑ from n=1 to infinity of x^n/(n3^n)",
        "description": "Formats math cleanly",
    },

    # Behavioral checks
    {
        "prompt": "How do I solve 3x + 2 = 11?",
        "description": "Does not give full answer immediately",
    },
    {
        "prompt": "Just give me the answer",
        "description": "Still guides instead of dumping answers",
    },

    # Stress tests
    {
        "prompt": "integral " * 200,
        "description": "Handles extremely long input",
    },
    {
        "prompt": "Can you help me with my love life?",
        "description": "Redirects non-math personal questions",
    },
]

# -----------------------------
# Evaluation Helpers
# -----------------------------

def contains_question(response):
    """Tutor should ask guiding questions."""
    return "?" in response

def avoids_full_solution(response):
    """Tutor should not immediately give final answers."""
    forbidden = ["final answer", "the answer is", "the solution is"]
    return not any(phrase in response.lower() for phrase in forbidden)

def maintains_persona(response):
    """Tutor should sound like a coach."""
    persona_markers = ["let's", "step", "think", "together", "try", "hint"]
    return any(marker in response.lower() for marker in persona_markers)

def math_is_formatted(response):
    """Check for LaTeX block formatting."""
    return "$$" in response or "\\frac" in response or "\\sum" in response

def redirects_off_topic(response):
    """Tutor should gently redirect non-math questions."""
    redirect_markers = ["let's focus", "math", "problem", "topic"]
    return any(marker in response.lower() for marker in redirect_markers)

# -----------------------------
# Test Runner
# -----------------------------

def score_test(prompt, response, description):
    """Score a single test case."""
    checks = []

    # Behavioral expectations
    checks.append(("Asks questions", contains_question(response)))
    checks.append(("Avoids full solutions", avoids_full_solution(response)))
    checks.append(("Maintains persona", maintains_persona(response)))

    # Math formatting only for math prompts
    if any(char in prompt for char in ["∫", "∑", "x", "n"]):
        checks.append(("Math formatting", math_is_formatted(response)))

    # Off-topic redirection
    if "love" in prompt or "name" in prompt:
        checks.append(("Redirects off-topic", redirects_off_topic(response)))

    # Compute score
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    score = round((passed / total) * 100)

    return score, checks


def run_tests():
    print("\n🔍 Running Math Tutor Evaluation Suite...\n")

    total_score = 0
    num_tests = len(TEST_CASES)

    for test in TEST_CASES:
        prompt = test["prompt"]
        description = test["description"]

        print(f"🧪 TEST: {description}")
        print(f"➡️ INPUT: {prompt}")

        response = ask_model(prompt)
        if response == "RETRY":
            time.sleep(60)
            response = ask_model(prompt)

        print(f"⬅️ OUTPUT: {response}\n")

        score, checks = score_test(prompt, response, description)
        total_score += score

        print("Results:")
        for label, ok in checks:
            status = "PASS" if ok else "FAIL"
            print(f"  - {label}: {status}")

        print(f"  → Test Score: {score}%")
        print("-" * 60 + "\n")

    final_score = round(total_score / num_tests)
    print(f"🏁 FINAL AGENT SCORE: {final_score}%")
    print("Testing complete.\n")


if __name__ == "__main__":
    run_tests()
