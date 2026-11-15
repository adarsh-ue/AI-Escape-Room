"""Streamlit pieces shared by app_v1.py and app_v2.py."""
import streamlit as st

from escape_room.settings import ConfigError, load_config
from escape_room.gemini import Gemini
from escape_room.room import load_room  # noqa: F401  (re-exported for the apps)


def get_llm(version_label: str) -> Gemini:
    """Load .env and build the Gemini client, or stop the app with a fix-it message."""
    try:
        api_key, model = load_config()
    except ConfigError as e:
        st.title(f"🗝️ AI Escape Room ({version_label})")
        st.error(str(e))
        st.stop()
    return Gemini(api_key, model)


def header(room: dict, version_label: str, show_help: bool):
    st.title(f"🗝️ {room['title']}")
    st.caption(f"AI Escape Room · {version_label}")
    with st.expander("How to play", expanded=show_help):
        for line in room["instructions"]:
            st.markdown(f"- {line}")


def render_chat(display: list[dict]):
    for msg in display:
        avatar = "🧙" if msg["role"] == "assistant" else "🧑"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["text"])
