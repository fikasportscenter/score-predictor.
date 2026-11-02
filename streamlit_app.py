"""Football score predictor - paid access (access codes). Phone-friendly Streamlit app.
Needs predictor_nokey.py beside it.

Secrets to set in Streamlit (Manage app > Settings > Secrets):
  CODE_SECRET      = "long random text, keep private"
  ADMIN_PASSWORD   = "your owner password"
  PRICE_TEXT       = "UGX 2,000 per day"
  PAY_INSTRUCTIONS = "Send to MTN MoMo 07XXXXXXXX (Your Name)"
  WHATSAPP_NUMBER  = "2567XXXXXXXX"      (international format, no +)
  FOOTBALL_DATA_ORG_KEY = "your football-data.org key"   (adds same-day results)
"""
import contextlib
import hashlib
import hmac
import html
import io
import json
import math
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
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
.pill.miss {background:#fde2e2; color:#7f1d1d;}
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


# ---------- live results from football-data.org (optional, free key) ----------
FD_ORG = {"PL": "E0", "ELC": "E1", "PD": "SP1", "SA": "I1", "BL1": "D1",
          "FL1": "F1", "DED": "N1", "PPL": "P1"}      # football-data.org code -> our league code
FD_ALIASES = {   # their spelling -> spelling used in our data
    "manchester united": "Man United", "manchester city": "Man City",
    "nottingham forest": "Nott'm Forest", "wolverhampton wanderers": "Wolves",
    "wolverhampton": "Wolves", "tottenham hotspur": "Tottenham", "newcastle united": "Newcastle",
    "brighton hove albion": "Brighton", "brighton": "Brighton", "west ham united": "West Ham",
    "leeds united": "Leeds", "leicester city": "Leicester", "ipswich town": "Ipswich",
    "luton town": "Luton", "sheffield united": "Sheffield United", "norwich city": "Norwich",
    "cardiff city": "Cardiff", "swansea city": "Swansea", "stoke city": "Stoke",
    "hull city": "Hull", "coventry city": "Coventry", "birmingham city": "Birmingham",
    "queens park rangers": "QPR", "west bromwich albion": "West Brom",
    "sheffield wednesday": "Sheffield Weds", "preston north end": "Preston",
    "oxford united": "Oxford", "derby county": "Derby", "bristol city": "Bristol City",
    "atletico madrid": "Ath Madrid", "club atletico de madrid": "Ath Madrid",
    "athletic club": "Ath Bilbao", "real sociedad": "Sociedad", "real betis": "Betis",
    "rayo vallecano": "Vallecano", "celta vigo": "Celta", "rc celta": "Celta",
    "deportivo alaves": "Alaves", "rcd espanyol": "Espanol", "espanyol": "Espanol",
    "real valladolid": "Valladolid", "ud las palmas": "Las Palmas", "cd leganes": "Leganes",
    "internazionale": "Inter", "internazionale milano": "Inter", "fc internazionale milano": "Inter",
    "ac milan": "Milan", "as roma": "Roma", "ssc napoli": "Napoli", "ss lazio": "Lazio",
    "hellas verona": "Verona", "bayern munchen": "Bayern Munich", "fc bayern munchen": "Bayern Munich",
    "borussia monchengladbach": "M'gladbach", "borussia dortmund": "Dortmund",
    "bayer 04 leverkusen": "Leverkusen", "bayer leverkusen": "Leverkusen",
    "eintracht frankfurt": "Ein Frankfurt", "rb leipzig": "RB Leipzig", "vfb stuttgart": "Stuttgart",
    "1 fc union berlin": "Union Berlin", "fc augsburg": "Augsburg", "sc freiburg": "Freiburg",
    "tsg 1899 hoffenheim": "Hoffenheim", "vfl wolfsburg": "Wolfsburg", "vfl bochum 1848": "Bochum",
    "werder bremen": "Werder Bremen", "1 fsv mainz 05": "Mainz", "fc st pauli 1910": "St Pauli",
    "1 fc heidenheim 1846": "Heidenheim", "holstein kiel": "Holstein Kiel",
    "paris saint germain": "Paris SG", "olympique de marseille": "Marseille",
    "olympique lyonnais": "Lyon", "as monaco": "Monaco", "losc lille": "Lille",
    "stade rennais": "Rennes", "stade brestois 29": "Brest", "ogc nice": "Nice",
    "rc strasbourg alsace": "Strasbourg", "stade de reims": "Reims", "as saint etienne": "St Etienne",
    "psv": "PSV Eindhoven", "sc heerenveen": "Heerenveen", "fc utrecht": "Utrecht",
    "az": "AZ Alkmaar", "go ahead eagles": "Go Ahead Eagles", "fc twente": "Twente",
    "fc groningen": "Groningen", "sparta rotterdam": "Sparta Rotterdam", "nec": "Nijmegen",
    "sporting clube de portugal": "Sporting", "sporting cp": "Sporting", "sl benfica": "Benfica",
    "fc porto": "Porto", "sporting clube de braga": "Sp Braga", "sc braga": "Sp Braga",
    "vitoria sc": "Guimaraes", "vitoria guimaraes": "Guimaraes",
}
_FD_STOP = {"fc", "afc", "cf", "ac", "as", "ssc", "sc", "rc", "rcd", "ud", "cd", "ca", "us", "fk",
            "sv", "vfb", "vfl", "tsg", "fsv", "1", "04", "05", "96", "1899", "1846", "de", "calcio"}


def _fold(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return " ".join("".join(c if c.isalnum() else " " for c in s).split())


def _toks(s):
    return {t for t in _fold(s).split() if t not in _FD_STOP}


def match_team(api_names, csv_names):
    """Find our spelling of a team from football-data.org's name(s), or None if unsure."""
    for n in api_names:
        f = _fold(n)
        short = " ".join(w for w in f.split() if w not in ("fc", "afc", "cf"))
        for key in (f, short):
            a = FD_ALIASES.get(key)
            if a and a in csv_names:
                return a
    best, score, ties = None, 0, 0
    for n in api_names:
        at = _toks(n)
        for c in csv_names:
            ct = _toks(c)
            if not at or not ct or not (ct <= at or at <= ct):
                continue
            sc = len(ct & at)
            if sc > score:
                best, score, ties = c, sc, 1
            elif sc == score and c != best:
                ties += 1
    return best if score and ties == 1 else None


def merge_live_results(cache):
    """Adds finished matches of the last 9 days from football-data.org to the league
    data. Needs FOOTBALL_DATA_ORG_KEY in Secrets. Never raises: on any problem the
    normal data is used unchanged. Returns the number of matches added."""
    token = secret("FOOTBALL_DATA_ORG_KEY")
    if not token:
        return 0
    try:
        today = datetime.now(timezone.utc).date()
        q = urllib.parse.urlencode({"dateFrom": (today - timedelta(days=9)).isoformat(),
                                    "dateTo": (today + timedelta(days=1)).isoformat(),
                                    "status": "FINISHED"})
        req = urllib.request.Request("https://api.football-data.org/v4/matches?" + q,
                                     headers={"X-Auth-Token": token})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8"))
        added = 0
        names = {}
        for m in data.get("matches") or []:
            div = FD_ORG.get((m.get("competition") or {}).get("code"))
            ft = ((m.get("score") or {}).get("fullTime")) or {}
            if not div or ft.get("home") is None or ft.get("away") is None:
                continue
            rows = cache.get(div)
            if not rows:
                continue
            if div not in names:
                names[div] = {r["home"] for r in rows} | {r["away"] for r in rows}
            h, a = m.get("homeTeam") or {}, m.get("awayTeam") or {}
            home = match_team([h.get("name"), h.get("shortName")], names[div])
            away = match_team([a.get("name"), a.get("shortName")], names[div])
            if not home or not away or home == away:
                continue
            d = datetime.strptime(m["utcDate"][:10], "%Y-%m-%d")
            if any(r["home"] == home and r["away"] == away and abs((r["date"] - d).days) <= 2
                   for r in rows):
                continue
            row = {"date": d, "home": home, "away": away,
                   "hg": int(ft["home"]), "ag": int(ft["away"])}
            for k in p.STAT_COLS:
                row[k] = None
            rows.append(row)
            added += 1
        return added
    except Exception:
        return 0


# ---------- prediction ----------
@st.cache_resource(ttl=6 * 3600, show_spinner=False)
def league_data():
    """All leagues downloaded once and shared by every visitor (6 hours)."""
    cache = {}
    p.load_all(cache)
    if not any(cache.values()):
        # Raising means Streamlit does NOT cache this failure.
        raise RuntimeError("Could not download match data right now. Please try again.")
    merge_live_results(cache)
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


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def get_results():
    """Returns (result, error). Back-test of the last 7 days. Cached for 3 hours."""
    try:
        return pk.compute_results(league_data(), 7), None
    except Exception as e:
        return None, f"Something went wrong: {e}"


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def get_all_matches():
    """Every upcoming fixture (next 7 days) in every league we have data for, with the
    model's prediction. Returns (result, error). Cached for 3 hours."""
    try:
        fixtures = pk.load_fixtures()
        cache = league_data()
        today = datetime.now(timezone.utc).date()
        end = today + timedelta(days=7)
        per_div, out, skipped = {}, [], 0
        for f in fixtures:
            if not (today <= f["date"] < end):
                continue
            div = f["div"]
            if div not in per_div:
                rows = cache.get(div) or []
                names = {r["home"] for r in rows} | {r["away"] for r in rows}
                ratings, avg = p.ratings_from(rows) if rows else ({}, p.DEFAULT_AVG_GOALS)
                per_div[div] = (rows, names, ratings, avg, p.shot_ratings_from(rows))
            rows, names, ratings, avg, shot = per_div[div]
            if not rows:
                skipped += 1
                continue

            def resolve(q):
                if q in names:
                    return q
                hits = p.find_team_names(q, rows)
                return hits[0] if hits else None

            home, away = resolve(f["home"]), resolve(f["away"])
            if not home or not away or home == away:
                skipped += 1
                continue
            hm, am = p.last_matches(home, rows), p.last_matches(away, rows)
            if len(hm) < 3 or len(am) < 3:
                skipped += 1
                continue
            pr = p.predict(p.summarise(hm, ratings, True, shot),
                           p.summarise(am, ratings, False, shot), avg)
            total = pr["xg_home"] + pr["xg_away"]
            out.append({"date": f["date"], "time": f["time"], "div": div,
                        "league": p.LEAGUES.get(div, div), "home": home, "away": away,
                        "pr": pr, "over15": 1 - math.exp(-total) * (1 + total)})
        out.sort(key=lambda m: (m["date"], m["time"] or "99:99", m["league"]))
        return {"matches": out, "skipped": skipped}, None
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
        shot = p.shot_ratings_from(pool)
        hs, as_ = p.summarise(hm, ratings, True, shot), p.summarise(am, ratings, False, shot)
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


STAT_ROWS = [  # (label, key, kind)
    ("Goals scored per match", "goals_for", "2"),
    ("Goals conceded per match", "goals_against", "2"),
    ("Average goals (both teams, per match)", "avg_goals", "2"),
    ("Failed to score (of last 6)", "failed_to_score", "int"),
    ("Shots taken per match", "shots", "1"),
    ("Shots faced per match", "shots_against", "1"),
    ("Avg. shots on target", "sot", "1"),
    ("Avg. shots on target against", "sot_against", "1"),
    ("Avg. shots off target", "off_target", "1"),
    ("Shots off/on-target ratio", "off_on_ratio", "2"),
    ("Avg. shots per goal", "shots_per_goal", "1"),
    ("Shooting conversion rate", "conversion", "pct"),
    ("Scoring efficiency (goals per shot on target)", "scoring_eff", "pct"),
    ("Conceding efficiency (goals per shot on target faced)", "conceding_eff", "pct"),
    ("Avg. corners", "corners", "1"),
    ("Avg. corners against", "corners_against", "1"),
    ("Avg. fouls", "fouls", "1"),
    ("Avg. yellow cards", "yellows", "2"),
    ("Avg. red cards", "reds", "2"),
]


def _fmt_stat(v, kind):
    if v is None:
        return "n/a"
    if kind == "int":
        return str(int(v))
    if kind == "pct":
        return f"{v:.0%}"
    return f"{v:.{kind}f}"


def stats_table(data):
    hs, as_ = data["hs"]["stats"], data["as"]["stats"]
    rows = [f"| Last 6 matches | {data['home']} | {data['away']} |", "|---|---|---|"]
    for label, key, kind in STAT_ROWS:
        rows.append(f"| {label} | {_fmt_stat(hs.get(key), kind)} | {_fmt_stat(as_.get(key), kind)} |")
    st.markdown("\n".join(rows))
    short = [n for n in (hs["n_shots"], as_["n_shots"]) if n < hs["n"]]
    if short:
        st.caption("Shot figures use only the matches where the data has them "
                   f"({data['home']}: {hs['n_shots']} of {hs['n']}, "
                   f"{data['away']}: {as_['n_shots']} of {as_['n']}). 'n/a' = not in the data.")
    st.caption("Not available in the free data: possession, attacks, dangerous attacks, "
               "shots inside/outside the box, goal kicks, penalties, offsides.")


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
    with st.expander("📊 Team stats (last 6 matches)", expanded=True):
        stats_table(data)
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
FREE_PICKS = 1   # how many matches free visitors see in full on the Top picks tab


def picks_tab(has_access, key):
    with st.spinner("Loading today's picks (first time can take ~30 seconds)..."):
        res, err = get_picks(1)
    if err:
        st.error(err)
        return
    ms = res["matches"]
    st.caption(f"Today · {len(ms)} high-confidence pick"
               f"{'' if len(ms) == 1 else 's'} from {res['analysed']} matches analysed. "
               "Times are UK time.")
    # Free visitors get the FREE_PICKS strongest matches in full; the rest stay locked.
    best = sorted(range(len(ms)), key=lambda i: -ms[i]["picks"][0][1])
    free_ids = set() if has_access else set(best[:FREE_PICKS])
    if not has_access:
        locked_n = len(ms) - len(free_ids)
        if locked_n > 0:
            st.markdown(f"**🎁 Here are {len(free_ids)} free picks. "
                        f"🔒 {locked_n} more are locked. Unlock to see them, "
                        "the percentages and the full analysis.**")
        payment_box(key, "picks")
    if not ms:
        st.info("No high-confidence picks today. Check again later.")
    else:
        st.markdown("### 📋 All top picks")
    day = None
    for i, m in enumerate(ms):
        if m["date"] != day:
            day = m["date"]
            st.markdown(f"<div class='day'>{day.strftime('%A, %d %B')}</div>",
                        unsafe_allow_html=True)
        if has_access or i in free_ids:
            free_tag = "" if has_access else "<span class='pill hot'>🎁 FREE</span>"
            pills = free_tag + "".join(
                f"<span class='pill{' hot' if pr >= 0.75 else ''}'>{html.escape(mk)} · {pr:.0%}</span>"
                for mk, pr in m["picks"])
        else:
            n = len(m["picks"])
            pills = f"<span class='pill lock'>🔒 {n} pick{'' if n == 1 else 's'} locked</span>"
        st.markdown(
            f"<div class='pick'><div class='meta'>{html.escape(m['league'])} · "
            f"{html.escape(m['time'])}</div><div class='vs'>{html.escape(m['home'])} vs "
            f"{html.escape(m['away'])}</div>{pills}</div>", unsafe_allow_html=True)
        if has_access or i in free_ids:
            pid = f"{m['home']}|{m['away']}"
            opened = st.session_state.get("open_pick") == pid
            if st.button("✖ Close analysis" if opened else "📈 See analysis",
                         key=f"an_{pid}", use_container_width=True):
                st.session_state["open_pick"] = None if opened else pid
                st.rerun()
            if opened:
                with st.spinner("Loading analysis..."):
                    data, aerr = compute(m["home"], m["away"])
                if aerr:
                    st.error(aerr)
                else:
                    show_result(data)
    st.caption("Model estimates from recent form. Not guarantees and not betting advice.")


def all_tab(has_access, key):
    """Every league: all upcoming fixtures. Full predictions for paid clients only."""
    with st.spinner("Loading all leagues (first time can take ~30 seconds)..."):
        res, err = get_all_matches()
    if err:
        st.error(err)
        return
    ms = res["matches"]
    if not ms:
        st.info("No upcoming fixtures found in the data right now. Check again later.")
        return
    today = datetime.now(timezone.utc).date()
    span = st.radio("Show matches", ["Today", "Tomorrow", "Next 3 days", "Next 7 days"],
                    horizontal=True, key="all_span")
    first, last = {"Today": (0, 1), "Tomorrow": (1, 2), "Next 3 days": (0, 3),
                   "Next 7 days": (0, 7)}[span]
    ms = [m for m in ms if today + timedelta(days=first) <= m["date"] < today + timedelta(days=last)]
    leagues = sorted({m["league"] for m in ms})
    pick = st.selectbox("League", ["All leagues"] + leagues, key="all_league")
    if pick != "All leagues":
        ms = [m for m in ms if m["league"] == pick]
    st.caption(f"{len(ms)} match{'' if len(ms) == 1 else 'es'} · "
               f"{len({m['league'] for m in ms})} league(s). Times are UK time.")
    if not has_access:
        st.markdown("**🔒 Predictions for every league are for paying clients. "
                    "Unlock to see the predicted score, win chances, goals and "
                    "full analysis for each match below.**")
        payment_box(key, "all")
    if not ms:
        st.info("No matches for this choice.")
        return
    day = None
    for m in ms:
        if m["date"] != day:
            day = m["date"]
            st.markdown(f"<div class='day'>{day.strftime('%A, %d %B')}</div>",
                        unsafe_allow_html=True)
        head = (f"<div class='meta'>{html.escape(m['league'])} · {html.escape(m['time'])}</div>"
                f"<div class='vs'>{html.escape(m['home'])} vs {html.escape(m['away'])}</div>")
        if has_access:
            pr = m["pr"]
            (i, j), _ = pr["top"][0]
            pills = (f"<span class='pill hot'>Score {i}-{j}</span>"
                     f"<span class='pill'>1 {pr['home']:.0%}</span>"
                     f"<span class='pill'>X {pr['draw']:.0%}</span>"
                     f"<span class='pill'>2 {pr['away']:.0%}</span>"
                     f"<span class='pill'>xG {pr['xg_home']:.1f}-{pr['xg_away']:.1f}</span>"
                     f"<span class='pill'>Over 1.5 {m['over15']:.0%}</span>"
                     f"<span class='pill'>Over 2.5 {pr['over25']:.0%}</span>"
                     f"<span class='pill'>BTTS {pr['btts']:.0%}</span>")
        else:
            pills = "<span class='pill lock'>🔒 Prediction locked</span>"
        st.markdown(f"<div class='pick'>{head}{pills}</div>", unsafe_allow_html=True)
        if has_access:
            pid = f"{m['home']}|{m['away']}"
            opened = st.session_state.get("open_all") == pid
            if st.button("✖ Close analysis" if opened else "📈 See analysis",
                         key=f"all_{pid}", use_container_width=True):
                st.session_state["open_all"] = None if opened else pid
                st.rerun()
            if opened:
                with st.spinner("Loading analysis..."):
                    data, aerr = compute(m["home"], m["away"])
                if aerr:
                    st.error(aerr)
                else:
                    show_result(data)
    if res["skipped"]:
        st.caption(f"{res['skipped']} fixture(s) left out because there is not enough "
                   "recent data for one of the teams.")
    st.caption("1 = home win, X = draw, 2 = away win. Model estimates from recent form. "
               "Not guarantees and not betting advice.")


def results_tab():
    """Past results. Visible to everyone: old picks have no betting value."""
    with st.spinner("Loading results (first time can take ~30 seconds)..."):
        res, err = get_results()
    if err:
        st.error(f"Results could not load: {err}")
        return
    days = [d for d in res["days"] if d["total"]]
    if not days:
        st.info("No finished picks to show yet. Check again later.")
        return
    st.caption("Tap a date to see every pick for that day, marked ✅ hit or ❌ miss. "
               "Back-tested: the same model and rules re-run on the data that was "
               "available before each match. Wins and losses are all shown.")
    try:
        latest = max(r["date"].date() for rows in league_data().values() for r in rows)
        if latest < datetime.now(timezone.utc).date() - timedelta(days=1):
            st.info(f"📅 Our results data is up to {latest.strftime('%a %d %b')}. "
                    "Newer days appear here automatically when the data provider "
                    "updates it, usually within a few days.")
    except Exception:
        pass
    labels = {d["date"].strftime("%a %d %b"): d for d in days}
    choice = st.radio("Choose a date", list(labels), horizontal=True)
    d = labels[choice]
    st.markdown(f"**{d['hits']} of {d['total']} picks hit ({d['hits'] / d['total']:.0%})**")
    for m in d["matches"]:
        pills = "".join(
            f"<span class='pill {'hot' if x['hit'] else 'miss'}'>"
            f"{'✅' if x['hit'] else '❌'} {html.escape(x['market'])} · {x['prob']:.0%}</span>"
            for x in m["picks"])
        st.markdown(
            f"<div class='pick'><div class='meta'>{html.escape(m['league'])} · "
            f"Final score {html.escape(m['score'])}</div><div class='vs'>"
            f"{html.escape(m['home'])} vs {html.escape(m['away'])}</div>{pills}</div>",
            unsafe_allow_html=True)


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
tab_picks, tab_all, tab_results, tab_pred = st.tabs(
    ["🔥 Top picks", "🌍 All leagues", "📊 Results", "🔍 Predict a match"])
with tab_picks:
    picks_tab(has_access, key)
with tab_all:
    all_tab(has_access, key)
with tab_results:
    results_tab()
with tab_pred:
    predictor_ui(has_access, key)
owner_panel(key, admin_pw)