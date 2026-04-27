import streamlit as st
import requests
import uuid

import os
API_URL = os.environ.get("API_URL", "http://localhost:8000")

st.set_page_config(page_title="RCA Agent", page_icon="🔍", layout="wide")

st.title("🔍 Delivery Operations RCA Agent")
st.caption("Amazon Quick-Commerce · OR2A SLA Analysis · 2026-04-22")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    st.session_state.messages = []
    st.session_state.turn = 0

with st.sidebar:
    st.header("Session")
    st.code(st.session_state.session_id[:8] + "...", language=None)
    st.metric("Turns", st.session_state.turn)

    if st.button("New Session", use_container_width=True):
        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.messages = []
        st.session_state.turn = 0
        st.rerun()

    st.markdown("---")
    st.markdown("**Try asking:**")
    examples = [
        "Which cities had the most SLA breaches?",
        "List all stores in Bangalore",
        "Run RCA for Koramangala store",
        "What caused the supply issue in Mumbai?",
        "Were there any sustained pileups today?",
        "Show me the city summary for Delhi",
    ]
    for ex in examples:
        if st.button(ex, use_container_width=True, key=ex):
            st.session_state["prefill"] = ex
            st.rerun()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

prefill = st.session_state.pop("prefill", None)
prompt = st.chat_input("Ask about delivery operations RCA...") or prefill

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Analysing..."):
            try:
                resp = requests.post(
                    f"{API_URL}/chat",
                    json={"session_id": st.session_state.session_id, "message": prompt},
                    timeout=300,
                )
                resp.raise_for_status()
                data = resp.json()
                reply = data["response"]
                st.session_state.turn = data.get("turn", st.session_state.turn)
            except requests.exceptions.ConnectionError:
                reply = "⚠️ Cannot reach backend. Run `python run.py` first."
            except Exception as e:
                reply = f"⚠️ Error: {str(e)}"

        st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()
