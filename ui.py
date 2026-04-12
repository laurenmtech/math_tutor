import streamlit as st
import time

from script import ask_model, create_history


st.set_page_config(page_title="Math Tutor", page_icon="📘", layout="centered")

st.markdown(
    """
    <style>
    .stApp {
        background: radial-gradient(circle at 20% 10%, #fff6dc 0%, #f9f4ea 38%, #e8edf6 100%);
    }
    .title-wrap {
        background: linear-gradient(120deg, #1f3c88 0%, #3059c9 55%, #6d8de3 100%);
        color: #ffffff;
        border-radius: 14px;
        padding: 16px 18px;
        margin-bottom: 12px;
        box-shadow: 0 8px 24px rgba(22, 43, 98, 0.22);
    }
    .subtitle {
        color: #f4f7ff;
        opacity: 0.94;
        margin-top: 4px;
        font-size: 0.95rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

controls_slot = st.empty()

st.markdown(
    """
    <div class="title-wrap">
      <h2 style="margin:0;">Math Tutor</h2>
      <div class="subtitle">Ask algebra, calculus, or geometry questions and get guided hints.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

if "model_history" not in st.session_state:
    st.session_state.model_history = create_history()

if "display_messages" not in st.session_state:
    st.session_state.display_messages = []

for msg in st.session_state.display_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

user_prompt = st.chat_input("Try: How do I solve 3x + 2 = 11?")

if user_prompt:
    st.session_state.display_messages.append({"role": "user", "content": user_prompt})
    with st.chat_message("user"):
        st.markdown(user_prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            reply = ask_model(user_prompt, st.session_state.model_history)
            if reply == "RETRY":
                time.sleep(1)
                reply = ask_model(user_prompt, st.session_state.model_history)
                if reply == "RETRY":
                    reply = "I hit a temporary API rate limit. Please try again in about a minute."
            st.markdown(reply)

    st.session_state.display_messages.append({"role": "assistant", "content": reply})

has_student_message = any(msg["role"] == "user" for msg in st.session_state.display_messages)
if has_student_message:
    with controls_slot.container():
        _, controls_col = st.columns([0.78, 0.22])
        with controls_col:
            if st.button("Start New Session", type="secondary", use_container_width=True):
                st.session_state.model_history = create_history()
                st.session_state.display_messages = []
                st.rerun()
else:
    controls_slot.empty()
