"""AI Escape Room - Version 2 (Python engine decides, LLM narrates).

Run:  streamlit run app_v2.py
"""
import streamlit as st

from escape_room.gemini import LLMError
from escape_room.ui_common import get_llm, header, load_room, render_chat
from escape_room.v2.game import GameV2

LABEL = "Version 2 - Reliable engine"
st.set_page_config(page_title="AI Escape Room V2", page_icon="🗝️")

room = load_room()
llm = get_llm(LABEL)


def reset_game():
    st.session_state.game = GameV2(room, llm)
    st.session_state.display = [{"role": "assistant", "text": room["intro"]}]


if "game" not in st.session_state:
    reset_game()
game: GameV2 = st.session_state.game
state = game.state

# ---------- Sidebar (state held by Python) ----------
with st.sidebar:
    st.header("🎒 Inventory")
    st.markdown("\n".join(f"- {i}" for i in state["inventory"]) or "_Empty_")

    st.header("🧩 Puzzles solved")
    for pid, title in room["puzzles"].items():
        st.markdown(f"{'✅' if pid in state['solved'] else '⬜'} {title}")

    st.header("🔐 Locks")
    for name, spec in room["objects"].items():
        if "lock" in spec:
            st.markdown(f"{'🔓' if name in state['unlocked'] else '🔒'} {name}")

    st.caption(f"Turns: {state['turns']} · Model: {llm.model} · API calls: {llm.calls}")
    st.divider()
    if st.button("🔄 Restart game", use_container_width=True):
        reset_game()
        st.rerun()
    show_debug = st.toggle("Show engine debug", value=False)

# ---------- Main ----------
header(room, LABEL, show_help=state["turns"] == 0)
render_chat(st.session_state.display)

if show_debug:
    with st.expander("🛠️ Last turn (parsed action → engine result)", expanded=True):
        st.json(game.last_debug or {})
    with st.expander("🛠️ Full game state"):
        st.json(state)

if game.escaped:
    st.success(f"🎉 You escaped in {state['turns']} turns! Press Restart to play again.")
    st.stop()

player_input = st.chat_input("What do you do?")
if player_input:
    with st.chat_message("user", avatar="🧑"):
        st.markdown(player_input)
    with st.chat_message("assistant", avatar="🧙"):
        with st.spinner("The Game Master is thinking..."):
            try:
                narration = game.turn(player_input)
            except LLMError as e:
                st.error(str(e))
                st.stop()
    st.session_state.display += [
        {"role": "user", "text": player_input},
        {"role": "assistant", "text": narration},
    ]
    if game.escaped:
        st.balloons()
    st.rerun()
