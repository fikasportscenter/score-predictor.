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
import html
import io
import time
from urllib.parse import quote

import streamlit as st

import picks as pk
import predictor_nokey as p

st.set_page_config(page_title="Score Predictor", page_icon="⚽")

st.markdown("""
<style>
.big-score {text-align:center; font-size:3.2rem; font-weight:800; line-height:1.1; margin:0.2rem 0;}
.teams {text-align:center; font-size:1.1rem; opacity:0.85;}
.sub {text-align:center; opacity:0.7; margin-bottom:0.8rem;}
.form {font-size:1.3rem; letter-spacing:2px;}
.pick {border:1px solid rgba(128,128,128,.35); border-radius:14px; padding:10px 14px; margin:0 0 10px 0;}
.pick .meta {opacity:.65; font-size:.82rem;}
.pick .vs {font-weight:700; font-size:1.05rem; margin:2px 0 8px 0;}
.pill {display:inline-block; border-radius:999px; padding:4px 11px; margin:0 6px 6px 0; font-size:.88rem; font-weight:600; background:#dce9ff; color:#164a9a;}
.pill.hot {background:#d6f5df; color:#14532d;}
.pill.lock {background:#e5e7eb; color:#555;}
.day {margin:18px 0 6px 0; font-weight:700; opacity:.65; text-transform:uppercase; font-size:.8rem; letter-spacing:.06em;}
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
@st.cache_resource(ttl=6 * 3600, show_spinner=False)
def league_data():
    """All leagues downloaded once and shared by every visitor (6 hours)."""
    cache = {}
    p.load_all(cache)
    if not any(cache.values()):
        # Raising means Streamlit does NOT cache this failure.
        raise RuntimeError("Could not download match data right now. Please try again.")
    return cache


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def get_picks(days):
    """Returns (result, error). Cached for 3 hours."""
    try:
        return pk.compute_picks(league_data(), days), None
    except RuntimeError as e:
        return None, str(e)
    except Exception as e:
        return None, f"Something went wrong: {e}"


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def compute(home_q, away_q):
    """Returns (data, error). Cached for 6 hours per team pair."""
    try:
        cache = league_data()
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
    except (SystemExit, RuntimeError) as e:
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
    payment_box(key, "predict")


def predictor_ui(has_access, key):
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
def picks_tab(has_access, key):
    with st.spinner("Loading today's picks (first time can take ~30 seconds)..."):
        res, err = get_picks(1)
    if err:
        st.error(err)
        return
    ms = res["matches"]
    st.caption(f"Next {res['days']} days · {len(ms)} high-confidence pick"
               f"{'' if len(ms) == 1 else 's'} from {res['analysed']} matches analysed. "
               "Times are UK time.")
    if not has_access:
        st.markdown(f"**🔒 {len(ms)} pick{'' if len(ms) == 1 else 's'} found. "
                    "Unlock to see which bets and the percentages.**")
        payment_box(key, "picks")
    if not ms:
        st.info("No high-confidence picks in the next few days. Check again later.")
        return
    day = None
    for m in ms:
        if m["date"] != day:
            day = m["date"]
            st.markdown(f"<div class='day'>{day.strftime('%A, %d %B')}</div>",
                        unsafe_allow_html=True)
        if has_access:
            pills = "".join(
                f"<span class='pill{' hot' if pr >= 0.75 else ''}'>{html.escape(mk)} · {pr:.0%}</span>"
                for mk, pr in m["picks"])
        else:
            n = len(m["picks"])
            pills = f"<span class='pill lock'>🔒 {n} pick{'' if n == 1 else 's'} locked</span>"
        st.markdown(
            f"<div class='pick'><div class='meta'>{html.escape(m['league'])} · "
            f"{html.escape(m['time'])}</div><div class='vs'>{html.escape(m['home'])} vs "
            f"{html.escape(m['away'])}</div>{pills}</div>", unsafe_allow_html=True)
    st.caption("Model estimates from recent form. Not guarantees and not betting advice.")


def payment_box(key, where):
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
    code = st.text_input("Have a code? Enter it here", placeholder="FB-XXXXXXXX-XXXXXXXXXX",
                         key=f"code_{where}")
    if st.button("Unlock", use_container_width=True, key=f"unlock_{where}"):
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

st.title("⚽ Score Predictor")
tab_picks, tab_pred = st.tabs(["🔥 Top picks", "🔍 Predict a match"])
with tab_picks:
    picks_tab(has_access, key)
with tab_pred:
    predictor_ui(has_access, key)
owner_panel(key, admin_pw)
