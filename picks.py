"""Top picks: finds upcoming fixtures where the model gives a high chance of a
home/away win, over 1.5 or 2.5 goals, or both-teams-score yes/no.
Needs predictor_nokey.py beside it."""
import csv
import io
import math
import urllib.request
from datetime import datetime, timedelta, timezone

import predictor_nokey as p

FIXTURES_URL = "https://www.football-data.co.uk/fixtures.csv"

# A match is a "top pick" when the model gives at least this chance.
PICK_MIN = {"win": 0.70, "over15": 0.85, "over25": 0.72, "btts_yes": 0.70, "btts_no": 0.72}


def load_fixtures():
    """Upcoming fixtures as a list of dicts. Raises RuntimeError if unavailable."""
    try:
        req = urllib.request.Request(FIXTURES_URL, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=25).read()
    except Exception:
        raise RuntimeError("Could not download the fixtures list right now. Please try again.")
    out = []
    for r in csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace"))):
        d = p._parse_date(r.get("Date") or "")
        home, away = (r.get("HomeTeam") or "").strip(), (r.get("AwayTeam") or "").strip()
        if d and home and away:
            out.append({"div": (r.get("Div") or "").strip(), "date": d.date(),
                        "time": (r.get("Time") or "").strip(), "home": home, "away": away})
    if not out:
        raise RuntimeError("The fixtures list is empty right now.")
    return out


def picks_for(pr):
    picks = []
    if pr["home"] >= PICK_MIN["win"]:
        picks.append(("Home win", pr["home"]))
    if pr["away"] >= PICK_MIN["win"]:
        picks.append(("Away win", pr["away"]))
    # Chance of 2+ total goals, from the two expected-goal values (total goals is Poisson).
    total = pr["xg_home"] + pr["xg_away"]
    over15 = 1 - math.exp(-total) * (1 + total)
    if over15 >= PICK_MIN["over15"]:
        picks.append(("Over 1.5 goals", over15))
    if pr["over25"] >= PICK_MIN["over25"]:
        picks.append(("Over 2.5 goals", pr["over25"]))
    if pr["btts"] >= PICK_MIN["btts_yes"]:
        picks.append(("Both teams score: Yes", pr["btts"]))
    if 1 - pr["btts"] >= PICK_MIN["btts_no"]:
        picks.append(("Both teams score: No", 1 - pr["btts"]))
    return sorted(picks, key=lambda x: -x[1])


def compute_picks(league_cache, days=3, today=None):
    """Returns {'matches': [...], 'analysed': n, 'days': days}.
    league_cache is the dict filled by predictor_nokey.load_all()."""
    fixtures = load_fixtures()
    today = today or datetime.now(timezone.utc).date()
    end = today + timedelta(days=days)
    upcoming = [f for f in fixtures if today <= f["date"] < end]

    per_div = {}   # div -> (rows, names, ratings, avg)

    def league(div):
        if div not in per_div:
            rows = league_cache.get(div) or []
            names = {r["home"] for r in rows} | {r["away"] for r in rows}
            ratings, avg = p.ratings_from(rows) if rows else ({}, p.DEFAULT_AVG_GOALS)
            per_div[div] = (rows, names, ratings, avg)
        return per_div[div]

    matches, analysed = [], 0
    for f in upcoming:
        rows, names, ratings, avg = league(f["div"])
        if not rows:
            continue

        def resolve(q):
            if q in names:
                return q
            hits = p.find_team_names(q, rows)
            return hits[0] if hits else None

        home, away = resolve(f["home"]), resolve(f["away"])
        if not home or not away or home == away:
            continue
        hm, am = p.last_matches(home, rows), p.last_matches(away, rows)
        if len(hm) < 3 or len(am) < 3:
            continue
        analysed += 1
        pr = p.predict(p.summarise(hm, ratings, True), p.summarise(am, ratings, False), avg)
        picks = picks_for(pr)
        if picks:
            matches.append({"date": f["date"], "time": f["time"],
                            "league": p.LEAGUES.get(f["div"], f["div"]),
                            "home": home, "away": away, "picks": picks})
    matches.sort(key=lambda m: (m["date"], -m["picks"][0][1]))
    return {"matches": matches, "analysed": analysed, "days": days}
