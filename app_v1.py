"""AI Escape Room - Version 1 (LLM is the Game Master and the game engine).

Run:  streamlit run app_v1.py
"""
import streamlit as st

from escape_room.gemini import LLMError
from escape_room.ui_common import get_llm, header, load_room, render_chat
from escape_room.v1.game import GameV1

LABEL = "Version 1 - LLM Game Master"
st.set_page_config(page_title="AI Escape Room V1", page_icon="🗝️")

room = load_room()
llm = get_llm(LABEL)


def reset_game():
    st.session_state.game = GameV1(room, llm)
    st.session_state.display = [{"role": "assistant", "text": room["intro"]}]


if "game" not in st.session_state:
    reset_game()
game: GameV1 = st.session_state.game

# ---------- Sidebar (state as reported by the LLM) ----------
with st.sidebar:
    st.header("🎒 Inventory")
    st.markdown("\n".join(f"- {i}" for i in game.inventory) or "_Empty_")
    st.header("🧩 Puzzles solved")
    st.write(f"{len(game.solved)} / {len(room['puzzles'])}")
    st.caption(f"Turns: {game.turns} · Model: {llm.model}")
    st.caption("ℹ️ In V1 this state is whatever the LLM reports.")
    st.divider()
    if st.button("🔄 Restart game", use_container_width=True):
        reset_game()
        st.rerun()

# ---------- Main ----------
header(room, LABEL, show_help=game.turns == 0)
render_chat(st.session_state.display)

if game.escaped:
    st.success(f"🎉 You escaped in {game.turns} turns! Press Restart to play again.")
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
