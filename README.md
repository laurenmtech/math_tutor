# MATH_TUTOR OVERVIEW

A lightweight AI-powered high school math tutor built in Python. It is designed to guide high-school students through problems step-by-step. The focus of this tutor is coaching, rather than answer dumping. 

This project includes:
- A command-line tutoring assistant (`script.py`)
- A simple web app UI (`ui.py`)
- A behavior and quality test harness (`test_agent.py`)

## The goal of this project is to demonstrate:

- Encouraging, student-centered tutoring tone
- Guided learning with hints and questions (instead of immediate full solutions)
- LaTeX-style math formatting in tutor responses
- Basic handling for unclear or malformed student input
- Off-topic redirection back to math
- Simple evaluation suite for behavior and formatting checks

## Project Structure

- `script.py`: Main tutor app and model request logic
- `ui.py`: Streamlit web UI for browser-based chatting
- `test_agent.py`: Automated evaluation tests for tutor behavior

## Key Design Decisions
1. System prompt as the behavioral context
The system prompt defines: 
    - tutoring tone and persona boundaries
    - step by step guidance
    - formatting rules
    - off topic redirection
        - the structured JSON output schema that the app validates before display
2. Conversation History
The agent stores messages so that it can remember what the student asked, maintain continuity, and avoid repetition
3. Error Handling
The API occasionally returns rate-limit errors so instead of exposing that to the user I added friendly error handling so the user sees a friendly message instead

## What I would improve with more time
1. Create a better UI to feel more like a real product
2. Implement memory controls -- currently the conversation grows indefinitely
3. Add evaluation metrics -- It would be amazing for added ability for students to track progress over time with scoring options
5. Different tutoring modes: having different prompting for algebra, geometry, calculus, SAT prep, etc. 


## How to run it
1. Install dependencies
        '''bash
        pip install requests
        '''
        - For local testing, ensure `GOOGLE_API_KEY` is set to a valid key. If it is missing or invalid, API calls will fail.
2. Set your API key as an environment variable
        export GOOGLE_API_KEY="your_key_here"
3. (Optional) Store your key in a local `.env` file based on `.env.example`.
        - `.env` is ignored by git and will not be pushed.
2. run the tutor
        python script.py
        - youll see the question pop up and then you can type questions


## (optional) Run the Web UI

```bash
streamlit run ui.py
```

Then open the local URL shown in your terminal (usually `http://localhost:8501`).

## Test Script
##“Due to free-tier API limits, the full evaluation suite is included for demonstration purposes but not intended to be run end-to-end.”

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

- The test harness may pause and retry on rate-limit responses (`429` or `503`).
- Responses depend on external API behavior, so scores can vary between runs.
