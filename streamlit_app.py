"""Football score predictor - paid access (access codes). Phone-friendly Streamlit app.
Needs predictor_nokey.py beside it.

Secrets to set in Streamlit (Manage app > Settings > Secrets):
  CODE_SECRET      = "long random text, keep private"
  ADMIN_PASSWORD   = "your owner password"
  PRICE_TEXT       = "UGX 2,000 per day"
  PAY_INSTRUCTIONS = "Send to MTN MoMo 07XXXXXXXX (Your Name)"
  WHATSAPP_NUMBER  = "2567XXXXXXXX"      (international format, no +)
"""
import contextlib
import hashlib
import hmac
import io
import time
from urllib.parse import quote

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

PASSES = {"Daily (24 hours)": 24, "Weekly (7 days)": 24 * 7, "Monthly (30 days)": 24 * 30}


# ---------- access codes ----------
def secret(name, default=""):
    try:
        return str(st.secrets.get(name, default))
    except Exception:
        return default


def _sig(key, payload):
    return hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()[:10].upper()


def make_code(key, hours, now=None):
    expiry = int((now if now is not None else time.time()) + hours * 3600)
    payload = format(expiry, "X")
    return f"FB-{payload}-{_sig(key, payload)}"


def check_code(key, code, now=None):
    """Returns (valid, seconds_left_or_reason)."""
    parts = (code or "").strip().upper().replace(" ", "").split("-")
    if len(parts) != 3 or parts[0] != "FB":
        return False, "That code is not valid."
    if not hmac.compare_digest(parts[2], _sig(key, parts[1])):
        return False, "That code is not valid."
    try:
        left = int(parts[1], 16) - (now if now is not None else time.time())
    except ValueError:
        return False, "That code is not valid."
    if left <= 0:
        return False, "That code has expired. Please buy a new one."
    return True, int(left)


def time_left_text(seconds):
    h, m = divmod(int(seconds) // 60, 60)
    d, h = divmod(h, 24)
    return (f"{d}d {h}h" if d else f"{h}h {m}m")


# ---------- prediction ----------
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


def show_result(data):
    pr = data["pred"]
    (i, j), prob = pr["top"][0]
    st.divider()
    st.markdown(f"<div class='teams'>{data['home']} vs {data['away']}</div>",
                unsafe_allow_html=True)
    st.markdown(f"<div class='big-score'>{i} - {j}</div>", unsafe_allow_html=True)
    alt = ", ".join(f"{a}-{b} ({q:.0%})" for (a, b), q in pr["top"][1:])
    st.markdown(f"<div class='sub'>Most likely score ({prob:.0%}) · "
                f"also: {alt}<br>Expected goals "
                f"{pr['xg_home']:.2f} - {pr['xg_away']:.2f}</div>",
                unsafe_allow_html=True)
    for label, val in ((f"{data['home']} win", pr["home"]), ("Draw", pr["draw"]),
                       (f"{data['away']} win", pr["away"])):
        st.progress(min(max(val, 0.0), 1.0), text=f"{label}: {val:.0%}")
    c1, c2 = st.columns(2)
    c1.metric("Over 2.5 goals", f"{pr['over25']:.0%}")
    c2.metric("Both teams score", f"{pr['btts']:.0%}")
    with st.expander(f"{data['home']} - last 6 matches", expanded=True):
        team_card(data["home"], data["hm"], data["hs"], True)
    with st.expander(f"{data['away']} - last 6 matches", expanded=True):
        team_card(data["away"], data["am"], data["as"], False)
    st.caption("Statistical estimate from recent form only. Not a guarantee "
               "and not betting advice.")


def show_locked(data, key):
    """Only team names are shown. No prediction data is sent to the viewer."""
    st.divider()
    st.markdown(f"<div class='teams'>{data['home']} vs {data['away']}</div>",
                unsafe_allow_html=True)
    st.markdown("<div class='big-score'>? - ?</div>", unsafe_allow_html=True)
    st.markdown("<div class='sub'>🔒 Prediction locked. Pay to unlock it.</div>",
                unsafe_allow_html=True)
    payment_box(key)


def predictor_ui(has_access, key):
    st.title("⚽ Score Predictor")
    st.caption("Based on each team's last 6 matches. Try: Arsenal, Man United, "
               "Man City, Ath Madrid, Inter, Bayern (partial names work).")
    home = st.text_input("Home team", placeholder="Arsenal")
    away = st.text_input("Away team", placeholder="Chelsea")
    if st.button("Predict", type="primary", use_container_width=True):
        if not home.strip() or not away.strip():
            st.session_state.pop("pending", None)
            st.warning("Type both team names.")
        else:
            st.session_state["pending"] = (home.strip(), away.strip())
    pending = st.session_state.get("pending")
    if not pending:
        return
    with st.spinner("Fetching latest results (first time takes ~20s)..."):
        data, err = compute(*pending)
    if err:
        st.error(err)
    elif has_access:
        show_result(data)
    else:
        show_locked(data, key)


# ---------- paywall screens ----------
def payment_box(key):
    price = secret("PRICE_TEXT", "Ask the owner for the price")
    how = secret("PAY_INSTRUCTIONS", "Contact the owner to pay.")
    st.markdown(f"**Price:** {price}")
    st.markdown(f"**How to pay:** {how}")
    wa = secret("WHATSAPP_NUMBER")
    if wa:
        msg = quote("Hello, I have paid for Score Predictor access. Please send my code.")
        st.markdown(f"After paying, [send us the payment message on WhatsApp]"
                    f"(https://wa.me/{wa}?text={msg}) and we'll send your access code.")
    else:
        st.markdown("After paying, send the payment message to the owner to get your code.")
    code = st.text_input("Have a code? Enter it here", placeholder="FB-XXXXXXXX-XXXXXXXXXX")
    if st.button("Unlock", use_container_width=True):
        ok, info = check_code(key, code)
        if ok:
            st.session_state["code"] = code.strip()
            st.query_params["code"] = code.strip()
            st.rerun()
        else:
            st.error(info)


def owner_panel(key, admin_pw):
    with st.expander("Owner login"):
        if not st.session_state.get("admin_ok"):
            pw = st.text_input("Owner password", type="password", key="pw")
            if st.button("Log in"):
                if hmac.compare_digest(pw, admin_pw):
                    st.session_state["admin_ok"] = True
                    st.rerun()
                else:
                    st.error("Wrong password.")
            return
        st.success("Logged in as owner.")
        label = st.selectbox("Pass length", list(PASSES))
        if st.button("Generate access code"):
            code = make_code(key, PASSES[label])
            st.code(code, language=None)
            st.text_area("Message to send the customer",
                         f"Thank you! Your Score Predictor access code is:\n{code}\n"
                         f"Valid for {label.split(' (')[0].lower()} from now. "
                         "Enter it on the site and tap Unlock.")
        if st.button("Log out"):
            st.session_state["admin_ok"] = False
            st.rerun()


# ---------- main ----------
key, admin_pw = secret("CODE_SECRET"), secret("ADMIN_PASSWORD")
if not key or not admin_pw:
    st.error("This site is not set up yet. The owner must add CODE_SECRET and "
             "ADMIN_PASSWORD in the app's Secrets settings.")
    st.stop()

has_access = bool(st.session_state.get("admin_ok"))
if not has_access:
    code = st.session_state.get("code") or st.query_params.get("code", "")
    ok, info = check_code(key, code)
    if ok:
        has_access = True
        st.caption(f"✅ Access active - {time_left_text(info)} left")
    elif code:
        st.warning(info)
        st.session_state.pop("code", None)

predictor_ui(has_access, key)
owner_panel(key, admin_pw)
