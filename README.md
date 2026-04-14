# MATH_TUTOR OVERVIEW

A lightweight AI-powered high school math tutor built in Python. It is designed to guide high-school students through problems step-by-step. The focus of this tutor is coaching rather than answer dumping.

This project includes:
- A command-line tutoring assistant (`script.py`)
- A simple web app UI (`ui.py`)
- A behavior and quality test harness (`test_agent.py`)
- A Hugging Face API client (`api_client.py`)
- Math validation helpers (`math_validation.py`)
- Tutoring policy and response formatting helpers (`tutor_policy.py`)
- Example conversations with the agent ('examples.txt')

## The goal of this project is to demonstrate

- Encouraging, student-centered tutoring tone
- Guided learning with hints and questions (instead of immediate full solutions)
- LaTeX-style math formatting in tutor responses
- Basic handling for unclear or malformed student input
- Off-topic redirection back to math
- Simple evaluation suite for behavior and formatting checks

## Project Structure

- `script.py`: Main tutor orchestrator and CLI entrypoint
- `api_client.py`: Hugging Face request handling and response parsing
- `math_validation.py`: Equation consistency and student-step validation
- `tutor_policy.py`: JSON parsing, formatting, and tutoring policy rules
- `ui.py`: Streamlit web UI for browser-based chatting
- `test_agent.py`: Automated evaluation tests for tutor behavior

## Key Design Decisions
1. System prompt as the behavioral context.
        The prompt defines the tutoring tone, persona boundaries, step-by-step guidance, formatting rules, off-topic redirection, and JSON output schema.
2. Modular structure.
        The code is split into focused modules for API access, validation, tutoring policy, and orchestration so it is easier to read, test, and maintain.
3. Conversation history.
        The agent stores messages so it can maintain continuity and avoid repetition across turns.

## What I would improve with more time
1. Create a better UI so it feels more like a polished product.
        -include lesson plans related to the student's current homework problems
2. Spend more time shaping the tutor behavior so it teaches through the problem instead of just guiding it.
3. Add evaluation metrics so students can track progress over time.
4. Add different tutoring modes for algebra, geometry, calculus, SAT prep, and similar topics.


## How to run it (Option 1)
1. Install dependencies
```bash
pip install requests python-dotenv
```
   - For local testing, ensure `HUGGING_FACE_TOKEN` is set to a valid token in your `.env.local` file. You can also set `HUGGING_FACE_MODEL` to override the default model.
2. Run the tutor
```bash
python script.py
```
   - You should see the prompt appear in the terminal and can then type questions.


## Run the Web UI (Option 2)

```bash
streamlit run ui.py
```

Then open the local URL shown in your terminal (usually `http://localhost:8501`).

## Test Script
The test harness runs entirely offline and checks the parser, formatting, and guardrail logic using fixed fixtures.

```bash
python test_agent.py
```

The test suite checks items such as:
- Asking guiding questions
- Avoiding direct final answers
- Persona consistency
- Basic math formatting
- Off-topic redirection
- Handling malformed/empty inputs

## Notes

- The test harness does not call the model API, so results are deterministic.
