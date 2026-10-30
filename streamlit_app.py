"""Football score predictor - Streamlit web app. Needs predictor_nokey.py beside it."""
import contextlib
import io

import streamlit as st

import predictor_nokey as p

st.set_page_config(page_title="Score Predictor", page_icon="⚽")


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def run_prediction(home, away):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            p.run(home, away)
    except SystemExit as e:
        return f"{buf.getvalue()}\n{e}".strip(), False
    except Exception as e:
        return f"Something went wrong: {e}", False
    lines = [l for l in buf.getvalue().splitlines() if not l.startswith("Downloading")]
    return "\n".join(lines).strip(), True


st.title("⚽ Football Score Predictor")
st.caption("Uses each team's last 6 matches. Names like: Arsenal, Chelsea, "
           "Man United, Man City, Ath Madrid, Inter, Bayern (partial names work).")

home = st.text_input("Home team", placeholder="Arsenal")
away = st.text_input("Away team", placeholder="Chelsea")

if st.button("Predict", type="primary"):
    if not home.strip() or not away.strip():
        st.warning("Type both team names.")
    else:
        with st.spinner("Fetching latest results..."):
            text, ok = run_prediction(home.strip(), away.strip())
        if ok:
            st.code(text, language=None)
        else:
            st.error(text)
