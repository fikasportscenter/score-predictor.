"""Football score predictor - phone-friendly Streamlit app.
Needs predictor_nokey.py beside it."""
import contextlib
import io

import streamlit as st

import predictor_nokey as p

st.set_page_config(page_title="Score Predictor", page_icon="⚽")

st.markdown("""
<style>
.big-score {text-align:center; font-size:3.2rem; font-weight:800; line-height:1.1; margin:0.2rem 0;}
.teams {text-align:center; font-size:1.1rem; opacity:0.85;}
.sub {text-align:center; opacity:0.7; margin-bottom:0.8rem;}
.form {font-size:1.3rem; letter-spacing:2px;}
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def compute(home_q, away_q):
    """Returns (data, error). Cached for 6 hours per team pair."""
    cache = {}
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            hn, hrows = p.locate(home_q, cache)
            an, arows = p.locate(away_q, cache)
        pool = hrows if hrows is arows else hrows + arows
        ratings, avg = p.ratings_from(pool)
        hm, am = p.last_matches(hn, pool), p.last_matches(an, pool)
        if len(hm) < 3 or len(am) < 3:
            return None, "Not enough recent matches found for one of the teams."
        hs, as_ = p.summarise(hm, ratings, True), p.summarise(am, ratings, False)
        return {"home": hn, "away": an, "hm": hm, "am": am,
                "hs": hs, "as": as_, "pred": p.predict(hs, as_, avg)}, None
    except SystemExit as e:
        return None, str(e)
    except Exception as e:
        return None, f"Something went wrong: {e}"


def form_badges(form):
    return "".join({"W": "🟩", "D": "🟨", "L": "🟥"}[c] for c in form)


def team_card(name, matches, s, playing_home):
    st.markdown(f"**{name}**")
    st.markdown(f"<div class='form'>{form_badges(s['form'])}</div>",
                unsafe_allow_html=True)
    st.caption(f"W{s['w']} D{s['d']} L{s['l']} · scores {s['gf']:.2f} / "
               f"concedes {s['ga']:.2f} per game · {s['clean']} clean sheets")
    rows = ["| Date | | Opponent | Score |", "|---|---|---|---|"]
    for m in matches:
        v = "H" if m["home"] else "A"
        mark = "**" if m["home"] == playing_home else ""
        rows.append(f"| {m['date'][5:]} | {v} | {mark}{m['opp']}{mark} | "
                    f"{m['gf']}-{m['ga']} |")
    st.markdown("\n".join(rows))
    where = "home" if playing_home else "away"
    if s["venue_n"]:
        st.caption(f"Bold = {where} games (counted double). At {where}: "
                   f"{s['venue_gf']:.2f} scored / {s['venue_ga']:.2f} conceded.")


st.title("⚽ Score Predictor")
st.caption("Based on each team's last 6 matches. Try: Arsenal, Man United, "
           "Man City, Ath Madrid, Inter, Bayern (partial names work).")

home = st.text_input("Home team", placeholder="Arsenal")
away = st.text_input("Away team", placeholder="Chelsea")

if st.button("Predict", type="primary", use_container_width=True):
    if not home.strip() or not away.strip():
        st.warning("Type both team names.")
    else:
        with st.spinner("Fetching latest results (first time takes ~20s)..."):
            data, err = compute(home.strip(), away.strip())
        if err:
            st.error(err)
        else:
            pr = data["pred"]
            (i, j), prob = pr["top"][0]
            st.divider()
            st.markdown(f"<div class='teams'>{data['home']} vs {data['away']}</div>",
                        unsafe_allow_html=True)
            st.markdown(f"<div class='big-score'>{i} - {j}</div>",
                        unsafe_allow_html=True)
            alt = ", ".join(f"{a}-{b} ({q:.0%})" for (a, b), q in pr["top"][1:])
            st.markdown(f"<div class='sub'>Most likely score ({prob:.0%}) · "
                        f"also: {alt}<br>Expected goals "
                        f"{pr['xg_home']:.2f} - {pr['xg_away']:.2f}</div>",
                        unsafe_allow_html=True)

            for label, val in ((f"{data['home']} win", pr["home"]),
                               ("Draw", pr["draw"]),
                               (f"{data['away']} win", pr["away"])):
                st.progress(min(max(val, 0.0), 1.0), text=f"{label}: {val:.0%}")

            c1, c2 = st.columns(2)
            c1.metric("Over 2.5 goals", f"{pr['over25']:.0%}")
            c2.metric("Both teams score", f"{pr['btts']:.0%}")

            with st.expander(f"{data['home']} - last 6 matches", expanded=True):
                team_card(data["home"], data["hm"], data["hs"], True)
            with st.expander(f"{data['away']} - last 6 matches", expanded=True):
                team_card(data["away"], data["am"], data["as"], False)
            st.caption("Statistical estimate from recent form only. "
                       "Not betting advice.")
